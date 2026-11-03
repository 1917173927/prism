"""User-owned preference memory and personalized rebalancing endpoints."""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, model_validator

from app.contracts.evidence import ContractModel
from app.portfolio import AssetType, PortfolioImportBundle
from app.service.investment_memory import (
    InvestmentMemoryService, InvestmentMemoryState, InvestmentPolicyConfirmation, InvestmentPolicyStale,
    Percent, PersonalizedRebalancingComparison, PreferenceMemoryWrite,
)
from app.store.sqlite import StoreConflictError


class PersonalRebalancingPreview(ContractModel):
    expected_policy_revision: int = Field(ge=1)
    target_weights: dict[str, Percent] = Field(min_length=1, max_length=100)
    bundle: PortfolioImportBundle | None = None
    deadband_pct: Percent = Decimal("0.50")
    max_turnover_pct: Percent = Decimal("50")
    minimum_cash_pct: Percent = Decimal("0")
    prices_cny: dict[str, Decimal] = Field(default_factory=dict)
    asset_types: dict[str, AssetType] = Field(default_factory=dict)
    round_to_lot: bool = True

    @model_validator(mode="after")
    def validate_financial_inputs(self):
        if abs(sum(self.target_weights.values(), Decimal("0")) - 100) > Decimal("0.05"):
            raise ValueError("target weights must total 100 percent")
        if any(not price.is_finite() or price <= 0 for price in self.prices_cny.values()):
            raise ValueError("prices must be finite and positive")
        return self


class PersonalRebalancingInputPosition(ContractModel):
    asset_id: str
    asset_name: str
    current_weight_pct: Percent


class PersonalRebalancingInput(ContractModel):
    schema_version: str = "personal-rebalancing-input.v1"
    bundle: PortfolioImportBundle
    target_weights: dict[str, Percent]
    positions: tuple[PersonalRebalancingInputPosition, ...]
    data_mode: str
    is_synthetic: bool
    profile_ready: bool
    quote_ready: bool


def create_investment_memory_router(*, service: InvestmentMemoryService,
                                    owner_dependency, rebalance_request_builder):
    """The builder(owner_id, PersonalRebalancingPreview) binds current facts.

    It returns PortfolioRebalancingRequest after applying the application's
    current portfolio, LIVE provenance and confirmed risk-profile checks.
    """
    router = APIRouter(prefix="/api/v1/advisor/investment-memory")

    def invoke(operation):
        try:
            return operation()
        except StoreConflictError:
            raise HTTPException(409, detail="INVESTMENT_MEMORY_REVISION_CONFLICT") from None
        except InvestmentPolicyStale:
            raise HTTPException(409, detail="INVESTMENT_POLICY_STALE") from None

    @router.get("", response_model=InvestmentMemoryState)
    def read_memory(owner_id=Depends(owner_dependency)):
        return invoke(lambda: service.state(owner_id))

    @router.put("", response_model=InvestmentMemoryState)
    def save_memory(body: PreferenceMemoryWrite, owner_id=Depends(owner_dependency)):
        return invoke(lambda: service.save_preferences(owner_id, body))

    @router.post("/policy/confirm", response_model=InvestmentMemoryState)
    def confirm_policy(body: InvestmentPolicyConfirmation, owner_id=Depends(owner_dependency)):
        return invoke(lambda: service.confirm_policy(owner_id, body))

    @router.post("/rebalancing-preview", response_model=PersonalizedRebalancingComparison)
    def preview(body: PersonalRebalancingPreview, owner_id=Depends(owner_dependency)):
        return invoke(lambda: service.compare(rebalance_request_builder(owner_id, body),
                                               body.expected_policy_revision))

    return router
