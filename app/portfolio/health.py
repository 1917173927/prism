"""Deterministic portfolio look-through health calculation for the web client."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal, Self

from pydantic import Field, model_validator

from app.contracts.evidence import ContractModel, NonEmptyStr
from app.portfolio.contracts import AssetType, PortfolioImportBundle
from app.portfolio.exposure import ExposureContribution, calculate_exposure
from app.profile import RiskProfile
from app.risk import assess_risk_budget, calculate_concentration


SECTOR_ORDER = (
    "TECHNOLOGY",
    "INDUSTRIALS",
    "CONSUMER_HEALTHCARE",
    "FINANCE_CYCLICAL",
    "CASH",
)
SECTOR_NAMES = {
    "TECHNOLOGY": "科技半导体",
    "INDUSTRIALS": "先进制造",
    "CONSUMER_HEALTHCARE": "消费医药",
    "FINANCE_CYCLICAL": "金融周期",
    "CASH": "可用现金",
    "UNCLASSIFIED": "未分类资产",
}
MIN_CASH_WEIGHT_PCT = Decimal("5.00")
HHI_LIMIT = Decimal("2500.00")


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _canonical_sector(contribution: ExposureContribution) -> str:
    if contribution.asset_type == AssetType.CASH:
        return "CASH"
    normalized = (contribution.sector or "").strip().casefold()
    if normalized in {"technology", "information technology", "tech"}:
        return "TECHNOLOGY"
    if normalized in {"industrials", "industrial", "manufacturing"}:
        return "INDUSTRIALS"
    if normalized in {"consumer", "healthcare", "consumer healthcare"}:
        return "CONSUMER_HEALTHCARE"
    if normalized in {"finance", "financials", "cyclical", "financial", "utilities", "utility"}:
        return "FINANCE_CYCLICAL"
    return "UNCLASSIFIED"


def _sector_values(portfolio: PortfolioImportBundle, calculated_at: datetime) -> tuple[
    dict[str, Decimal], dict[str, tuple[str, ...]], str, tuple[str, ...]
]:
    exposure = calculate_exposure(portfolio, calculated_at=calculated_at)
    if exposure.report is None:
        return {}, {}, exposure.status.value, tuple(issue.code.value for issue in exposure.issues)
    values = {key: Decimal("0") for key in SECTOR_ORDER}
    names: dict[str, set[str]] = {key: set() for key in SECTOR_ORDER}
    values["UNCLASSIFIED"] = Decimal("0")
    names["UNCLASSIFIED"] = set()
    for contribution in exposure.report.contributions:
        key = _canonical_sector(contribution)
        values[key] += contribution.market_value
        names[key].add(contribution.asset_name)
    top_names = {key: tuple(sorted(items)[:3]) for key, items in names.items()}
    return values, top_names, exposure.status.value, tuple(issue.code.value for issue in exposure.issues)


def sector_weights_from_portfolio(
    portfolio: PortfolioImportBundle, calculated_at: datetime
) -> dict[str, Decimal]:
    values, _, status, issues = _sector_values(portfolio, calculated_at)
    if not values:
        raise ValueError("portfolio exposure is unavailable")
    if values["UNCLASSIFIED"] > Decimal("0"):
        raise ValueError("portfolio contains unclassified exposure; five-sector stress was refused")
    total = sum(values.values(), Decimal("0"))
    if total <= 0:
        raise ValueError("portfolio market value must be positive")
    weights = {key: _q(values[key] / total * Decimal("100")) for key in SECTOR_ORDER}
    rounding_delta = Decimal("100.00") - sum(weights.values(), Decimal("0"))
    largest = max(SECTOR_ORDER, key=lambda key: values[key])
    weights[largest] += rounding_delta
    if status != "COMPLETE" or issues:
        raise ValueError("portfolio exposure is incomplete; five-sector stress was refused")
    return weights


class PortfolioHealthRequest(ContractModel):
    schema_version: Literal["portfolio-health-request.v1"] = "portfolio-health-request.v1"
    request_id: NonEmptyStr
    owner_id: NonEmptyStr
    calculated_at: datetime
    portfolio: PortfolioImportBundle
    profile: RiskProfile

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        if self.calculated_at.tzinfo is None or self.calculated_at.utcoffset() is None:
            raise ValueError("calculated_at must be timezone-aware")
        if self.portfolio.owner_id != self.owner_id or self.profile.owner_id != self.owner_id:
            raise ValueError("portfolio health inputs must share owner scope")
        return self


class SectorHealth(ContractModel):
    sector_key: NonEmptyStr
    name: NonEmptyStr
    weight_pct: Decimal = Field(ge=0, le=100)
    limit_pct: Decimal = Field(ge=0, le=100)
    limit_operator: Literal["MAX", "MIN"]
    difference_pct_points: Decimal
    margin_pct_points: Decimal = Field(ge=0)
    verdict: Literal["PASS", "OVERBOUND"]
    top_holdings: tuple[str, ...] = ()


class PortfolioHealthResponse(ContractModel):
    schema_version: Literal["portfolio-health-response.v1"] = "portfolio-health-response.v1"
    request_id: NonEmptyStr
    owner_id: NonEmptyStr
    calculated_at: datetime
    status: Literal["PASS", "REVIEW_REQUIRED", "BLOCKED"]
    source_exposure_status: NonEmptyStr
    total_market_value_cny: Decimal = Field(gt=0)
    sector_hhi: Decimal = Field(ge=0, le=10000)
    hhi_limit: Decimal = HHI_LIMIT
    hhi_verdict: Literal["PASS", "OVERBOUND"]
    technology_weight_pct: Decimal = Field(ge=0, le=100)
    technology_limit_pct: Decimal = Field(ge=0, le=100)
    cash_weight_pct: Decimal = Field(ge=0, le=100)
    cash_minimum_pct: Decimal = MIN_CASH_WEIGHT_PCT
    has_breaches: bool
    evidence_count: int = Field(ge=1)
    top_sector_key: NonEmptyStr
    top_sector_name: NonEmptyStr
    top_sector_weight_pct: Decimal = Field(ge=0, le=100)
    sectors: tuple[SectorHealth, ...] = Field(min_length=5)
    issues: tuple[NonEmptyStr, ...] = ()
    calculation_steps: tuple[NonEmptyStr, ...] = Field(min_length=1)


def calculate_portfolio_health(request: PortfolioHealthRequest) -> PortfolioHealthResponse:
    exposure = calculate_exposure(request.portfolio, calculated_at=request.calculated_at)
    concentration = calculate_concentration(exposure)
    assessment = assess_risk_budget(request.profile, concentration)
    if exposure.report is None or concentration.report is None:
        raise ValueError("portfolio exposure or concentration is unavailable")

    values, holdings, source_status, exposure_issues = _sector_values(
        request.portfolio, request.calculated_at
    )
    total = exposure.report.total_market_value
    weights = {key: _q(value / total * Decimal("100")) for key, value in values.items()}
    budget = assessment.budget
    sectors: list[SectorHealth] = []
    for key in (*SECTOR_ORDER, "UNCLASSIFIED"):
        if key == "UNCLASSIFIED" and weights[key] == 0:
            continue
        is_cash = key == "CASH"
        if is_cash:
            limit = MIN_CASH_WEIGHT_PCT
        elif key == "TECHNOLOGY":
            limit = budget.max_technology_weight_pct
        elif key == "UNCLASSIFIED":
            limit = budget.max_unclassified_weight_pct
        else:
            limit = budget.max_sector_weight_pct
        difference = _q(weights[key] - limit)
        overbound = weights[key] < limit if is_cash else weights[key] > limit
        sectors.append(SectorHealth(
            sector_key=key,
            name=SECTOR_NAMES[key],
            weight_pct=weights[key],
            limit_pct=limit,
            limit_operator="MIN" if is_cash else "MAX",
            difference_pct_points=difference,
            margin_pct_points=_q(abs(difference)),
            verdict="OVERBOUND" if overbound else "PASS",
            top_holdings=holdings[key],
        ))

    sector_hhi = _q(sum((weight * weight for weight in weights.values()), Decimal("0")))
    hhi_overbound = sector_hhi > HHI_LIMIT
    has_breaches = hhi_overbound or any(row.verdict == "OVERBOUND" for row in sectors)
    top = max(sectors, key=lambda row: (row.weight_pct, row.sector_key))
    issues = tuple(dict.fromkeys((*exposure_issues, *(issue.code.value for issue in assessment.issues))))
    status = "REVIEW_REQUIRED" if has_breaches or source_status != "COMPLETE" or issues else "PASS"
    return PortfolioHealthResponse(
        request_id=request.request_id,
        owner_id=request.owner_id,
        calculated_at=request.calculated_at,
        status=status,
        source_exposure_status=source_status,
        total_market_value_cny=total,
        sector_hhi=sector_hhi,
        hhi_verdict="OVERBOUND" if hhi_overbound else "PASS",
        technology_weight_pct=weights["TECHNOLOGY"],
        technology_limit_pct=budget.max_technology_weight_pct,
        cash_weight_pct=weights["CASH"],
        has_breaches=has_breaches,
        evidence_count=len(exposure.report.contributions),
        top_sector_key=top.sector_key,
        top_sector_name=top.name,
        top_sector_weight_pct=top.weight_pct,
        sectors=tuple(sectors),
        issues=issues,
        calculation_steps=(
            "calculate_exposure(portfolio)",
            "aggregate canonical sector market values",
            "calculate sector HHI from closed weights",
            "apply profile risk-budget and cash hard gates",
        ),
    )
