"""Deterministic five-sector stress calculation without LLM arithmetic."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, localcontext
from typing import Literal, Self

from pydantic import Field, model_validator

from app.contracts.evidence import ContractModel, NonEmptyStr


SECTORS = ("TECHNOLOGY", "INDUSTRIALS", "CONSUMER_HEALTHCARE", "FINANCE_CYCLICAL", "CASH")
_VOL = {
    "TECHNOLOGY": Decimal("0.28"), "INDUSTRIALS": Decimal("0.22"),
    "CONSUMER_HEALTHCARE": Decimal("0.18"), "FINANCE_CYCLICAL": Decimal("0.20"),
    "CASH": Decimal("0.01"),
}
_CORRELATION = Decimal("0.30")
_TRADING_DAYS = Decimal("252")
_VAR_Z_95 = Decimal("1.644854")


def _q(value: Decimal, places: str = "0.01") -> Decimal:
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)


class CustomStressScenarioRequest(ContractModel):
    schema_version: Literal["custom-stress-scenario-request.v1"] = "custom-stress-scenario-request.v1"
    request_id: NonEmptyStr
    owner_id: NonEmptyStr
    portfolio_value_cny: Decimal = Field(gt=0)
    sector_weights_pct: dict[str, Decimal]
    sector_shocks_pct: dict[str, Decimal]

    @model_validator(mode="after")
    def validate_inputs(self) -> Self:
        if set(self.sector_weights_pct) != set(SECTORS) or set(self.sector_shocks_pct) != set(SECTORS):
            raise ValueError("sector weights and shocks must contain the five supported sectors")
        if any(not value.is_finite() or value < 0 or value > 100 for value in self.sector_weights_pct.values()):
            raise ValueError("sector weights must be finite and between 0 and 100")
        if abs(sum(self.sector_weights_pct.values()) - Decimal("100")) > Decimal("0.01"):
            raise ValueError("sector weights must sum to 100% within 0.01%")
        if any(not value.is_finite() or value < -30 or value > 30 for value in self.sector_shocks_pct.values()):
            raise ValueError("sector shocks must be finite and between -30% and 30%")
        return self


class CustomStressScenarioResponse(ContractModel):
    schema_version: Literal["custom-stress-scenario-response.v1"] = "custom-stress-scenario-response.v1"
    request_id: NonEmptyStr
    owner_id: NonEmptyStr
    scenario_return_pct: Decimal
    scenario_pnl_cny: Decimal
    baseline_volatility_pct: Decimal
    stressed_volatility_pct: Decimal
    volatility_change_pct_points: Decimal
    baseline_var_95_1d_cny: Decimal
    stressed_var_95_1d_cny: Decimal
    var_change_cny: Decimal
    stressed_sector_weights_pct: dict[str, Decimal]
    methodology: NonEmptyStr


def _volatility(weights: dict[str, Decimal]) -> Decimal:
    variance = Decimal(0)
    for left in SECTORS:
        for right in SECTORS:
            correlation = Decimal(1) if left == right else _CORRELATION
            variance += weights[left] * weights[right] * _VOL[left] * _VOL[right] * correlation
    with localcontext() as context:
        context.prec = 28
        return variance.sqrt()


def calculate_custom_stress(request: CustomStressScenarioRequest) -> CustomStressScenarioResponse:
    weights = {key: value / 100 for key, value in request.sector_weights_pct.items()}
    shocks = {key: value / 100 for key, value in request.sector_shocks_pct.items()}
    scenario_return = sum(weights[key] * shocks[key] for key in SECTORS)
    denominator = Decimal(1) + scenario_return
    if denominator <= 0:
        raise ValueError("stress scenario leaves no positive portfolio value")
    stressed_weights = {key: weights[key] * (Decimal(1) + shocks[key]) / denominator for key in SECTORS}
    base_vol = _volatility(weights)
    stressed_vol = _volatility(stressed_weights)
    with localcontext() as context:
        context.prec = 28
        daily_scale = _TRADING_DAYS.sqrt()
    base_var = request.portfolio_value_cny * _VAR_Z_95 * base_vol / daily_scale
    stressed_value = request.portfolio_value_cny * denominator
    stressed_var = stressed_value * _VAR_Z_95 * stressed_vol / daily_scale
    return CustomStressScenarioResponse(
        request_id=request.request_id, owner_id=request.owner_id,
        scenario_return_pct=_q(scenario_return * 100),
        scenario_pnl_cny=_q(request.portfolio_value_cny * scenario_return),
        baseline_volatility_pct=_q(base_vol * 100), stressed_volatility_pct=_q(stressed_vol * 100),
        volatility_change_pct_points=_q((stressed_vol - base_vol) * 100),
        baseline_var_95_1d_cny=_q(base_var), stressed_var_95_1d_cny=_q(stressed_var),
        var_change_cny=_q(stressed_var - base_var),
        stressed_sector_weights_pct={key: _q(value * 100) for key, value in stressed_weights.items()},
        methodology="固定年化波动率与0.30等相关系数协方差矩阵；冲击后权重重估；95%单日参数VaR，252交易日。",
    )
