"""Contracts for portfolio rebalancing planning and execution steps."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, model_validator

from app.contracts.evidence import ContractModel, NonEmptyStr
from app.gates import GateStatus
from app.portfolio.contracts import AssetType, PortfolioImportBundle
from app.profile import RiskProfile
from app.portfolio.health import PortfolioHealthResponse


class RebalancingActionType(StrEnum):
    """Action recommendation for an asset in rebalancing."""

    BUY = "BUY"
    SELL = "SELL"
    REDUCE = "REDUCE"
    HOLD = "HOLD"


class RebalancingAction(ContractModel):
    """Specific rebalancing action for a single portfolio asset."""

    asset_id: NonEmptyStr
    asset_name: NonEmptyStr
    asset_type: AssetType
    current_weight_pct: Decimal
    target_weight_pct: Decimal
    delta_weight_pct: Decimal
    current_value_cny: Decimal
    target_value_cny: Decimal
    cash_delta_cny: Decimal
    action_type: RebalancingActionType
    rationale: NonEmptyStr
    shares: Decimal | None = Field(default=None, ge=0)
    current_price_cny: Decimal | None = Field(default=None, gt=0)
    stamp_duty: Decimal = Field(default=Decimal("0.00"), ge=0)
    transfer_fee: Decimal = Field(default=Decimal("0.00"), ge=0)
    commission: Decimal = Field(default=Decimal("0.00"), ge=0)
    total_fees_cny: Decimal = Field(default=Decimal("0.00"), ge=0)
    executable: bool = True

    @model_validator(mode="after")
    def validate_action(self) -> Self:
        if self.current_weight_pct < Decimal("0"):
            raise ValueError("current_weight_pct cannot be negative")
        if self.target_weight_pct < Decimal("0"):
            raise ValueError("target_weight_pct cannot be negative")
        return self


class RebalancingStep(ContractModel):
    """Ordered step for executing rebalancing with liquidity awareness."""

    step_number: int = Field(ge=1)
    action_type: RebalancingActionType
    asset_id: NonEmptyStr
    asset_name: NonEmptyStr
    amount_cny: Decimal = Field(ge=Decimal("0"))
    liquidity_priority: int = Field(ge=1)
    description: NonEmptyStr
    shares: Decimal | None = None
    total_fees_cny: Decimal = Decimal("0.00")


class RebalancingMetrics(ContractModel):
    """Summary metrics of the rebalancing plan."""

    total_portfolio_value_cny: Decimal
    total_turnover_pct: Decimal
    total_buy_cny: Decimal
    total_sell_cny: Decimal
    net_cash_flow_cny: Decimal
    turnover_cap_breached: bool = False
    net_turnover_cost: Decimal = Decimal("0.00")
    net_turnover_cost_pct: Decimal = Decimal("0.00")
    cash_after_cny: Decimal = Decimal("0.00")
    cash_shortfall_cny: Decimal = Decimal("0.00")


class PortfolioRebalancingRequest(ContractModel):
    """Request to generate an actionable rebalancing plan."""

    schema_version: Literal["portfolio-rebalancing-request.v1"] = "portfolio-rebalancing-request.v1"
    request_id: NonEmptyStr
    owner_id: NonEmptyStr
    generated_at: datetime
    bundle: PortfolioImportBundle
    target_weights: dict[str, Decimal]
    deadband_pct: Decimal = Field(default=Decimal("0.50"), ge=0, le=100)
    max_turnover_pct: Decimal = Field(default=Decimal("50.00"), ge=0, le=100)
    minimum_cash_pct: Decimal = Field(default=Decimal("0.00"), ge=0, le=100)
    confirmed_profile: RiskProfile | None = None
    round_to_lot: bool = True
    prices_cny: dict[str, Decimal] = Field(default_factory=dict)
    asset_types: dict[str, AssetType] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        if self.owner_id != self.bundle.position_snapshot.owner_id:
            raise ValueError("request owner_id does not match bundle owner_id")
        if self.confirmed_profile is not None and self.confirmed_profile.owner_id != self.owner_id:
            raise ValueError("confirmed profile owner does not match request owner")
        total_target = sum(self.target_weights.values())
        if any(not v.is_finite() or v < 0 or v > 100 for v in self.target_weights.values()):
            raise ValueError("target weights must be finite and between 0 and 100")
        if any(not v.is_finite() or v <= 0 for v in self.prices_cny.values()):
            raise ValueError("prices must be finite and positive")
        if abs(total_target - Decimal("100.00")) > Decimal("0.05"):
            raise ValueError(f"target_weights must sum to 100.00% (got {total_target}%)")
        return self


class PortfolioRebalancingResponse(ContractModel):
    """Deterministic rebalancing plan response."""

    schema_version: Literal["portfolio-rebalancing-response.v1"] = "portfolio-rebalancing-response.v1"
    request_id: NonEmptyStr
    owner_id: NonEmptyStr
    status: GateStatus
    metrics: RebalancingMetrics
    actions: tuple[RebalancingAction, ...]
    execution_steps: tuple[RebalancingStep, ...]
    issues: tuple[str, ...] = ()
    post_trade_health: PortfolioHealthResponse | None = None
    invalidation_conditions: tuple[str, ...] = ()
    disclaimer: str = "调仓方案仅供决策参考（ADVISORY_ONLY），不构成自动交易或委托指令。"
