from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from app.llm.ocr_portfolio_parser import recalculate_portfolio_values
from app.portfolio.report import build_portfolio_report
from app.profile.presentation import build_profile_presentation
from app.profile.questionnaire import QUESTIONNAIRE_TEMPLATE, QuestionnaireAnswer, build_questionnaire_snapshot
from app.store import SQLiteDecisionEventStore


def _portfolio_data(owner_id: str = "report-owner") -> dict:
    return recalculate_portfolio_values(
        [
            {
                "asset_id": "600519.SH",
                "name": "贵州茅台",
                "quantity": 10,
                "price": 1000,
                "cost_price": 900,
                "previous_close": 990,
            }
        ],
        Decimal("1000"),
        owner_id,
    )


def _questionnaire_profile(owner_id: str = "report-owner"):
    answers = [
        QuestionnaireAnswer(question_id=question.question_id, score=3)
        if question.question_type.value == "SCORE"
        else QuestionnaireAnswer(
            question_id=question.question_id,
            selected_option_ids=(question.options[0].option_id,),
        )
        for question in QUESTIONNAIRE_TEMPLATE.questions
    ]
    snapshot = build_questionnaire_snapshot(
        owner_id,
        tuple(answers),
        confirmed_at=datetime(2026, 9, 15, 10, 0, tzinfo=UTC),
        snapshot_version=1,
    )
    return snapshot.profile, build_profile_presentation(snapshot)


def test_store_migration_versions_are_unique() -> None:
    migration_dir = Path(__file__).resolve().parents[2] / "app" / "store" / "migrations"
    versions = [int(path.name.split("_", 1)[0]) for path in migration_dir.glob("*.sql")]

    assert len(versions) == len(set(versions))


def test_report_closes_values_and_keeps_missing_profile_explicit() -> None:
    data = _portfolio_data()

    report = build_portfolio_report(
        data,
        owner_id="report-owner",
        data_mode="MOCK",
    )

    assert report.schema_version == "portfolio-report.v1"
    assert report.total_value_cny == Decimal("11000.00")
    assert report.holdings_value_cny == Decimal("10000.00")
    assert report.cash_cny == Decimal("1000.00")
    assert sum((row.market_value_cny for row in report.asset_structure), Decimal("0")) == report.total_value_cny
    assert sum((row.weight_pct for row in report.asset_structure), Decimal("0")) == Decimal("100.00")
    assert report.positions[0].diagnosis_status == "PASS"
    assert report.positions[0].pnl_cny == Decimal("1000.00")
    assert report.profile is None
    assert report.risk.status == "UNAVAILABLE"
    assert report.concentration.top_asset_name == "贵州茅台"
    assert report.concentration.top_asset_weight_pct == Decimal("100.00")
    assert report.concentration.status == "CALCULATED"
    assert report.pnl_summary.loss_position_count == 0
    assert report.base_protection.defensive_weight_pct == Decimal("9.09")
    assert report.configuration_reference == ("未绑定已确认风险画像，暂不生成权益增配参考。",)


def test_report_snapshot_is_idempotent_and_owner_scoped() -> None:
    data = _portfolio_data()
    report = build_portfolio_report(data, owner_id="report-owner", data_mode="MOCK")
    store = SQLiteDecisionEventStore(":memory:")

    first, created = store.save_portfolio_report(report)
    repeated, repeated_created = store.save_portfolio_report(report)

    assert created is True
    assert repeated_created is False
    assert repeated == first == report
    assert store.get_portfolio_report("report-owner", "MOCK", report.report_id) == report
    assert store.get_portfolio_report("another-owner", "MOCK", report.report_id) is None
    store.close()


def test_report_binds_profile_range_and_configuration_reference() -> None:
    data = _portfolio_data()
    profile, presentation = _questionnaire_profile()

    report = build_portfolio_report(
        data,
        owner_id="report-owner",
        data_mode="MOCK",
        profile=profile,
        presentation=presentation,
    )

    assert report.profile is not None
    assert report.profile.equity_minimum_pct == presentation.equity_range.minimum_pct
    assert report.concentration.single_asset_limit_pct is not None
    assert report.base_protection.profile_reference_pct is not None
    assert report.configuration_reference


def test_metadata_and_cost_changes_create_distinct_immutable_reports():
    from copy import deepcopy
    data = _portfolio_data()
    first = build_portfolio_report(data, owner_id="report-owner", data_mode="MOCK")
    enriched = deepcopy(data)
    enriched["portfolio"]["position_snapshot"]["positions"][0]["sector"] = "Industrials"
    enriched["positions"][0]["sector"] = "Industrials"
    enriched["positions"][0]["cost_price"] = 800
    second = build_portfolio_report(enriched, owner_id="report-owner", data_mode="MOCK")
    assert first.source_snapshot_id == second.source_snapshot_id
    assert first.report_id != second.report_id
    assert second.report_id == build_portfolio_report(enriched, owner_id="report-owner", data_mode="MOCK").report_id
    store = SQLiteDecisionEventStore(":memory:")
    try:
        store.save_portfolio_report(first)
        store.save_portfolio_report(second)
        assert store.get_portfolio_report("report-owner", "MOCK", first.report_id) == first
    finally:
        store.close()


def test_report_save_conflict_is_not_a_false_success(monkeypatch):
    from fastapi.testclient import TestClient
    from app.api.main import create_app
    from app.runtime.mode import reset_runtime_mode_controller, DataMode
    from app.store import StoreConflictError
    reset_runtime_mode_controller(mode=DataMode.MOCK)
    store = SQLiteDecisionEventStore(":memory:")
    store.save_current_portfolio("report-owner", "MOCK", _portfolio_data())
    def conflict(report):
        raise StoreConflictError("different content")
    monkeypatch.setattr(store, "save_portfolio_report", conflict)
    with TestClient(create_app(store=store)) as client:
        response = client.get("/api/v1/advisor/portfolio/report", headers={"X-Owner-ID": "report-owner"})
        assert response.status_code == 409
        assert response.json()["error_code"] == "PORTFOLIO_REPORT_CONFLICT"
        assert "报告存储内容冲突" in response.json()["message"]
    store.close()
