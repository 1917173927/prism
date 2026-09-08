from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.profile import (
    BehaviorEvent,
    BehaviorEventType,
    BehaviorEvidenceStatus,
    DisplayMode,
    ExperienceLevel,
    InvestmentHorizon,
    LiquidityNeed,
    ReturnExpectation,
    RiskLevel,
    RiskQuestionnaire,
    SuitabilityLevel,
    TradeSide,
    build_display_policy,
    build_profile_draft,
    calculate_behavior_profile,
    effective_risk_profile,
    finalize_profile,
    suitability_for_score,
)


NOW = datetime(2026, 9, 8, 8, 0, tzinfo=UTC)
OWNER = "behavior-owner-001"


def questionnaire_profile():
    questionnaire = RiskQuestionnaire(
        questionnaire_id="behavior-questionnaire-001",
        owner_id=OWNER,
        answered_at=NOW,
        loss_tolerance_score=5,
        investment_horizon=InvestmentHorizon.LONG,
        liquidity_need=LiquidityNeed.LOW,
        experience_level=ExperienceLevel.EXPERIENCED,
        return_expectation=ReturnExpectation.HIGH,
        max_drawdown_tolerance_pct=Decimal("35"),
    )
    return finalize_profile(
        build_profile_draft(questionnaire),
        profile_id="questionnaire-profile-001",
        created_at=NOW,
    )


def behavior_events(owner_id: str = OWNER) -> tuple[BehaviorEvent, ...]:
    trades = tuple(
        BehaviorEvent(
            event_id=f"trade-{index}",
            owner_id=owner_id,
            event_type=BehaviorEventType.TRADE,
            occurred_at=NOW - timedelta(days=20 - index),
            source="fixture ledger",
            asset_id="300750.SZ",
            asset_type="STOCK",
            side=TradeSide.BUY,
            quantity=Decimal("100"),
            price_cny=Decimal("100"),
            portfolio_value_cny=Decimal("100000"),
        )
        for index in range(3)
    )
    snapshots = tuple(
        BehaviorEvent(
            event_id=f"snapshot-{index}",
            owner_id=owner_id,
            event_type=BehaviorEventType.POSITION_SNAPSHOT,
            occurred_at=NOW - timedelta(days=10 - index),
            source="fixture ledger",
            portfolio_value_cny=Decimal("100000"),
            equity_weight_pct=Decimal("30"),
            max_position_weight_pct=Decimal("10"),
            max_sector_weight_pct=Decimal("20"),
            drawdown_pct=Decimal("3"),
        )
        for index in range(2)
    )
    return trades + snapshots


def test_behavior_profile_is_deterministic_and_only_tightens_risk() -> None:
    questionnaire = questionnaire_profile()
    first = calculate_behavior_profile(questionnaire, behavior_events(), calculated_at=NOW)
    second = calculate_behavior_profile(questionnaire, behavior_events(), calculated_at=NOW)
    assert first == second
    assert first.evidence_status == BehaviorEvidenceStatus.CALCULATED
    assert first.behavior_risk_score == Decimal("18.96")
    assert first.effective_risk_score < questionnaire.risk_score
    assert first.suitability_level == SuitabilityLevel.C1
    assert first.effective_risk_level == RiskLevel.CONSERVATIVE
    assert next(item for item in first.dimensions if item.key == "exp").source.value == "CALCULATED"
    assert next(item for item in first.dimensions if item.key == "ai").score is None
    effective = effective_risk_profile(questionnaire, first)
    assert effective.risk_score == first.effective_risk_score


def test_insufficient_data_preserves_questionnaire_and_does_not_invent_evidence() -> None:
    profile = questionnaire_profile()
    result = calculate_behavior_profile(profile, (), calculated_at=NOW)
    assert result.evidence_status == BehaviorEvidenceStatus.INSUFFICIENT_DATA
    assert result.behavior_risk_score is None
    assert result.effective_risk_score == profile.risk_score
    assert result.evidence == ()
    assert next(item for item in result.dimensions if item.key == "act").score is None


def test_historical_drawdown_is_derived_from_snapshot_values() -> None:
    events = list(behavior_events())
    events[-2] = events[-2].model_copy(update={"portfolio_value_cny": Decimal("100000"), "drawdown_pct": None})
    events[-1] = events[-1].model_copy(update={"portfolio_value_cny": Decimal("80000"), "drawdown_pct": None})
    result = calculate_behavior_profile(questionnaire_profile(), tuple(events), calculated_at=NOW)
    assert result.metrics.max_drawdown_pct == Decimal("20.00")


@pytest.mark.parametrize(
    ("score", "level"),
    [("0", "C1"), ("24", "C1"), ("25", "C2"), ("44", "C2"), ("45", "C3"),
     ("64", "C3"), ("65", "C4"), ("81", "C4"), ("82", "C5"), ("100", "C5")],
)
def test_suitability_boundaries(score: str, level: str) -> None:
    assert suitability_for_score(Decimal(score)).value == level


def test_display_policy_thresholds_and_owner_scope() -> None:
    assert build_display_policy(OWNER, 34, updated_at=NOW).mode == DisplayMode.AUDIT_EXPANDED
    assert build_display_policy(OWNER, 35, updated_at=NOW).mode == DisplayMode.STANDARD
    assert build_display_policy(OWNER, 65, updated_at=NOW).mode == DisplayMode.CONCLUSION_FIRST
    with pytest.raises(ValueError, match="owner scope"):
        calculate_behavior_profile(questionnaire_profile(), behavior_events("other-owner"), calculated_at=NOW)
