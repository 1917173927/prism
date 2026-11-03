from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.gates import GateStatus
from app.llm.ocr_portfolio_parser import recalculate_portfolio_values
from app.portfolio import PortfolioImportBundle
from app.profile import calculate_behavior_profile
from app.profile.questionnaire import QUESTIONNAIRE_TEMPLATE, QuestionnaireAnswer, build_questionnaire_snapshot
from app.rebalancing.contracts import PortfolioRebalancingRequest
from app.service import FixtureAdvisorQueryService, confirm_questionnaire
from app.service.investment_memory import (
    InvestmentMemoryService, InvestmentPolicyConfirmation, InvestmentPolicyStale,
    InvestmentPreferences, PreferenceMemoryWrite,
)
from app.store import SQLiteDecisionEventStore
from app.store.sqlite import StoreConflictError
from app.trading_history import HistoricalTradeRecord, TradeImportBatch, calculate_trading_style
from app.trading_history.contracts import TradeRecordStatus


NOW = datetime(2026, 10, 6, 8, tzinfo=UTC)
OWNER = "investment-memory-owner"


def setup_memory(**preferences):
    store = SQLiteDecisionEventStore()
    service = InvestmentMemoryService(store, clock=lambda: NOW)
    service.save_preferences(OWNER, PreferenceMemoryWrite(
        expected_revision=0, preferences=InvestmentPreferences(**preferences)))
    return store, service


def confirm(service):
    candidate = service.state(OWNER)["candidate"]
    service.confirm_policy(OWNER, InvestmentPolicyConfirmation(
        candidate_id=candidate.candidate_id, expected_memory_revision=candidate.memory_revision,
        expected_style_profile_version=candidate.style_profile_version))
    return service.state(OWNER)["policy"]


def rebalance(**updates):
    bundle = PortfolioImportBundle.model_validate(recalculate_portfolio_values([
        {"asset_id": "600001.SH", "quantity": 5000, "price": 10},
        {"asset_id": "000001.SZ", "quantity": 3000, "price": 10},
    ], Decimal("20000"), OWNER)["portfolio"])
    profile = confirm_questionnaire(FixtureAdvisorQueryService().query_template(OWNER).questionnaire)
    parameters = dict(request_id="personal-plan", owner_id=OWNER, generated_at=NOW, bundle=bundle,
                      confirmed_profile=profile, target_weights={"600001.SH": Decimal("10"),
                      "000001.SZ": Decimal("50"), "CASH-CNY": Decimal("40")})
    parameters.update(updates)
    return PortfolioRebalancingRequest(**parameters)


def ledger(store):
    records = tuple(HistoricalTradeRecord(
        trade_id=f"history-{index}", owner_id=OWNER, batch_id="long-term-batch", revision=1,
        traded_at=NOW - timedelta(days=450-index if index < 10 else 50-(index-10)),
        security_code=f"60000{index % 10}.SH", side="BUY" if index < 10 else "SELL",
        quantity=Decimal("100"), price_cny=Decimal("10"), gross_amount_cny=Decimal("1000"),
        asset_type="STOCK", account_value_cny=Decimal("100000"), source_row=index + 1,
        created_at=NOW, updated_at=NOW,
    ) for index in range(20))
    batch = TradeImportBatch(batch_id="long-term-batch", owner_id=OWNER, source_type="CSV",
                             source_digest="a" * 64, file_count=1, accepted_count=20,
                             duplicate_count=0, rejected_count=0, confirmed_at=NOW)
    store.save_trade_import(batch, records)
    style = calculate_trading_style(OWNER, records, calculated_at=NOW)
    store.save_trading_style_profile(style)
    return records


def questionnaire(version=1):
    answers = tuple(
        QuestionnaireAnswer(question_id=question.question_id, score=3)
        if question.question_type.value == "SCORE" else
        QuestionnaireAnswer(question_id=question.question_id, selected_option_ids=()
                            if question.question_id == "Q13" else (question.options[0].option_id,))
        for question in QUESTIONNAIRE_TEMPLATE.questions
    )
    return build_questionnaire_snapshot(OWNER, answers, confirmed_at=NOW, snapshot_version=version)


def test_policy_requires_confirmation_and_survives_restart(tmp_path):
    path = tmp_path / "memory.sqlite3"
    store = SQLiteDecisionEventStore(path)
    service = InvestmentMemoryService(store, clock=lambda: NOW)
    state = service.save_preferences(OWNER, PreferenceMemoryWrite(
        expected_revision=0, preferences=InvestmentPreferences(max_turnover_pct=5)))
    assert state["policy_status"] == "UNCONFIRMED"
    with pytest.raises(InvestmentPolicyStale):
        service.resolve_policy(OWNER, 1)
    confirm(service)
    store.close()
    reopened = SQLiteDecisionEventStore(path)
    current = InvestmentMemoryService(reopened, clock=lambda: NOW).state(OWNER)
    assert current["policy_status"] == "ACTIVE"
    assert current["policy"].parameters.max_turnover_pct == 5
    assert reopened.get_current_portfolio(OWNER, "MOCK") is None
    reopened.close()


def test_personal_turnover_changes_actual_orders_and_never_loosens_request():
    store, service = setup_memory(max_turnover_pct=5)
    policy = confirm(service)
    comparison = service.compare(rebalance(), policy.revision)
    assert comparison["personalized"].metrics.total_turnover_pct <= 5
    assert comparison["personalized"].metrics.total_turnover_pct < comparison["baseline"].metrics.total_turnover_pct
    assert comparison["effective_target_weights"] != comparison["source_target_weights"]
    assert all(step.shares % 100 == 0 for step in comparison["personalized"].execution_steps)
    applied, details = service.apply_policy(rebalance(max_turnover_pct=Decimal("2")), policy)
    assert applied.max_turnover_pct == 2
    assert details["target_adjustment_ratio"] < Decimal("0.1")
    store.close()


def test_larger_deadband_reduces_real_small_orders_without_hiding_risk_gate():
    store, service = setup_memory(deadband_pct=5)
    policy = confirm(service)
    request = rebalance(target_weights={"600001.SH": Decimal("49"), "000001.SZ": Decimal("31"),
                                       "CASH-CNY": Decimal("20")})
    result = service.compare(request, policy.revision)
    assert result["baseline"].execution_steps
    assert result["personalized"].execution_steps == ()
    assert result["personalized"].metrics.total_turnover_pct == 0
    assert result["personalized"].post_trade_health is not None
    if result["personalized"].post_trade_health.status != "PASS":
        assert result["personalized"].status == GateStatus.REVIEW_REQUIRED
    store.close()


def test_cash_floor_conflict_preserves_requirement_and_requires_review():
    store, service = setup_memory(max_turnover_pct=0, minimum_cash_pct=35)
    policy = confirm(service)
    result = service.compare(rebalance(), policy.revision)
    assert result["effective_target_weights"]["CASH-CNY"] >= 35
    assert result["personalized"].metrics.turnover_cap_breached
    assert result["personalized"].status == GateStatus.REVIEW_REQUIRED
    assert any("换手率" in issue for issue in result["personalized"].issues)
    store.close()


def test_memory_update_clear_and_owner_isolation_invalidate_confirmation():
    store, service = setup_memory(max_turnover_pct=5)
    policy = confirm(service)
    assert service.state("another-owner")["memory"] is None
    with pytest.raises(InvestmentPolicyStale):
        service.apply_policy(rebalance().model_copy(update={"owner_id": "another-owner"}), policy)
    service.save_preferences(OWNER, PreferenceMemoryWrite(expected_revision=1, preferences=InvestmentPreferences()))
    assert service.state(OWNER)["policy_status"] == "STALE"
    with pytest.raises(InvestmentPolicyStale):
        service.resolve_policy(OWNER, policy.revision)
    with pytest.raises(StoreConflictError):
        service.save_preferences(OWNER, PreferenceMemoryWrite(expected_revision=1, preferences=InvestmentPreferences()))
    store.close()


def test_confirmed_long_ledger_produces_style_and_withdrawal_invalidates_policy():
    store, service = setup_memory()
    records = ledger(store)
    candidate = service.state(OWNER)["candidate"]
    assert candidate.style_status == "CALCULATED"
    assert candidate.primary_style == "低频长持型"
    assert candidate.parameters.max_turnover_pct == 10
    assert candidate.parameters.deadband_pct == 2
    policy = confirm(service)
    store.append_trade_revision(records[0].model_copy(update={"revision": 2, "status": TradeRecordStatus.WITHDRAWN}), 1)
    assert service.state(OWNER)["policy_status"] == "STALE"
    with pytest.raises(InvestmentPolicyStale):
        service.compare(rebalance(), policy.revision)
    store.close()


def test_future_trades_do_not_generate_style_and_old_candidate_cannot_confirm():
    store, service = setup_memory()
    old = service.state(OWNER)["candidate"]
    records = ledger(store)
    for record in records:
        store.append_trade_revision(record.model_copy(update={"revision": 2, "traded_at": NOW + timedelta(days=10)}), 1)
    current = service.state(OWNER)["candidate"]
    assert current.style_status == "INSUFFICIENT_DATA"
    assert current.primary_style is None
    with pytest.raises(InvestmentPolicyStale):
        service.confirm_policy(OWNER, InvestmentPolicyConfirmation(
            candidate_id=old.candidate_id, expected_memory_revision=old.memory_revision,
            expected_style_profile_version=old.style_profile_version))
    store.close()


def test_questionnaire_and_behavior_revisions_invalidate_policy():
    store, service = setup_memory(max_turnover_pct=5)
    first = questionnaire()
    store.save_questionnaire_snapshot(first)
    confirm(service)
    store.save_questionnaire_snapshot(questionnaire(version=2))
    assert service.state(OWNER)["policy_status"] == "STALE"
    confirm(service)
    behavior = calculate_behavior_profile(first.profile, (), calculated_at=NOW)
    store.save_behavior_profile(behavior)
    assert service.state(OWNER)["policy_status"] == "STALE"
    store.close()


def test_all_existing_request_constraints_are_preserved():
    store, service = setup_memory(max_turnover_pct=20, minimum_cash_pct=5, deadband_pct=1)
    policy = confirm(service)
    request = rebalance(max_turnover_pct=Decimal("2"), minimum_cash_pct=Decimal("30"), deadband_pct=Decimal("3"))
    applied, _ = service.apply_policy(request, policy)
    assert applied.max_turnover_pct == 2
    assert applied.minimum_cash_pct == 30
    assert applied.deadband_pct == 3
    assert applied.confirmed_profile == request.confirmed_profile
    assert applied.bundle == request.bundle
    store.close()


def test_saved_policy_payload_cannot_be_modified_to_bypass_confirmation():
    import json
    store, service = setup_memory(max_turnover_pct=5)
    policy = confirm(service)
    payload = policy.model_dump(mode="json")
    payload["parameters"]["max_turnover_pct"] = "100"
    store._connection.execute("UPDATE investment_style_policies SET payload_json=? WHERE owner_id=?",
                              (json.dumps(payload), OWNER))
    assert service.state(OWNER)["policy_status"] == "STALE"
    with pytest.raises(InvestmentPolicyStale):
        service.resolve_policy(OWNER, policy.revision)
    store.close()


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "101"])
def test_invalid_preference_is_rejected(value):
    with pytest.raises(ValueError):
        InvestmentPreferences(max_turnover_pct=value)
