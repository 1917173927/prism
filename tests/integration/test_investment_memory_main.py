"""The real API binds personalized calculations to current server-owned facts."""
from contextlib import closing
from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.llm.ocr_portfolio_parser import recalculate_portfolio_values
from app.profile.questionnaire import QUESTIONNAIRE_TEMPLATE, QuestionnaireAnswer, build_questionnaire_snapshot
from app.store.sqlite import SQLiteDecisionEventStore


NOW = datetime(2026, 10, 6, 8, tzinfo=UTC)
ROOT = "/api/v1/advisor/investment-memory"


def seed(store, owner):
    answers = tuple(QuestionnaireAnswer.model_validate({"question_id": question.question_id,
        **({"score": 3} if question.question_type.value == "SCORE" else
           {"selected_option_ids": [question.options[0].option_id]})}) for question in QUESTIONNAIRE_TEMPLATE.questions)
    store.save_questionnaire_snapshot(build_questionnaire_snapshot(owner, answers, confirmed_at=NOW, snapshot_version=1))
    data = recalculate_portfolio_values([
        {"asset_id": "600001.SH", "quantity": 5000, "price": 10},
        {"asset_id": "000001.SZ", "quantity": 3000, "price": 10},
    ], Decimal("20000"), owner)
    store.save_current_portfolio(owner, "MOCK", data)
    return data["portfolio"]


def confirm(client, headers):
    candidate = client.put(ROOT, headers=headers, json={"expected_revision": 0,
        "preferences": {"max_turnover_pct": "5", "minimum_cash_pct": "10", "deadband_pct": "1"}}).json()["candidate"]
    return client.post(ROOT + "/policy/confirm", headers=headers, json={
        "candidate_id": candidate["candidate_id"], "expected_memory_revision": candidate["memory_revision"],
        "expected_style_profile_version": candidate["style_profile_version"]}).json()["policy"]


def test_current_profile_and_portfolio_bind_both_comparison_and_original_route(tmp_path):
    with closing(SQLiteDecisionEventStore(tmp_path / "main-memory.sqlite")) as store:
        portfolio = seed(store, "alice")
        with TestClient(create_app(store=store, clock=lambda: NOW)) as client:
            headers = {"X-Owner-ID": "alice"}
            policy = confirm(client, headers)
            prepared = client.get(ROOT + "/rebalancing-input", headers=headers)
            assert prepared.status_code == 200
            assert prepared.json()["bundle"]["owner_id"] == "alice"
            assert sum(map(Decimal, prepared.json()["target_weights"].values())) == 100
            assert prepared.json()["profile_ready"] and prepared.json()["is_synthetic"]
            assert client.get(ROOT + "/rebalancing-input", headers={"X-Owner-ID": "bob"}).status_code == 409
            body = {"expected_policy_revision": policy["revision"], "bundle": portfolio,
                "target_weights": {"600001.SH": "10", "000001.SZ": "50", "CASH-CNY": "40"}}
            response = client.post(ROOT + "/rebalancing-preview", headers=headers, json=body)
            assert response.status_code == 200, response.text
            comparison = response.json()
            assert Decimal(comparison["personalized"]["metrics"]["total_turnover_pct"]) <= 5
            assert comparison["personalized"]["actions"] != comparison["baseline"]["actions"]
            assert comparison["personalized"]["post_trade_health"] is not None
            original = client.post("/api/v1/advisor/rebalancing-runs", headers=headers, json={
                "request_id": "personal-main", "owner_id": "alice", "generated_at": NOW.isoformat(),
                "bundle": portfolio, "target_weights": body["target_weights"], "personal_policy_revision": policy["revision"]})
            assert original.status_code == 200, original.text
            assert original.json()["metrics"] == comparison["personalized"]["metrics"]
            assert original.json()["policy_application"]["policy"]["revision"] == policy["revision"]
            assert original.json()["post_trade_health"] is not None
            tampered = client.post(ROOT + "/rebalancing-preview", headers=headers, json={
                **body, "prices_cny": {"600001.SH": "20", "000001.SZ": "500"}, "round_to_lot": False,
                "asset_types": {"600001.SH": "CASH"}})
            assert tampered.status_code == 200
            # Client scenario parameters cannot change the price, security type
            # or lot rules of a server-confirmed portfolio.
            assert tampered.json()["personalized"]["metrics"] == comparison["personalized"]["metrics"]
            assert tampered.json()["personalized"]["actions"] == comparison["personalized"]["actions"]
            changed = recalculate_portfolio_values([{"asset_id": "600001.SH", "quantity": 2000, "price": 10}], Decimal("80000"), "alice")
            store.save_current_portfolio("alice", "MOCK", changed)
            stale = client.post(ROOT + "/rebalancing-preview", headers=headers, json=body)
            assert stale.status_code == 409 and stale.json()["error_code"] == "PERSONAL_REBALANCING_CONTEXT_CHANGED"


def test_personal_calculation_requires_confirmed_profile_and_authentication(tmp_path):
    with closing(SQLiteDecisionEventStore(tmp_path / "missing-memory.sqlite")) as store:
        data = recalculate_portfolio_values([{"asset_id": "600001.SH", "quantity": 1000, "price": 10}], Decimal("10000"), "alice")
        with TestClient(create_app(store=store, clock=lambda: NOW)) as client:
            headers = {"X-Owner-ID": "alice"}
            policy = confirm(client, headers)
            response = client.post(ROOT + "/rebalancing-preview", headers=headers, json={
                "expected_policy_revision": policy["revision"], "bundle": data["portfolio"],
                "target_weights": {"600001.SH": "50", "CASH-CNY": "50"}})
            assert response.status_code == 409 and response.json()["error_code"] == "PERSONAL_REBALANCING_PROFILE_REQUIRED"
        with TestClient(create_app(store=store, auth_enabled=True)) as client:
            assert client.get(ROOT).status_code == 401


def test_readonly_goal_input_closes_rounding_without_changing_position_facts(tmp_path):
    with closing(SQLiteDecisionEventStore(tmp_path / "rounded-input.sqlite")) as store:
        data = recalculate_portfolio_values([
            {"asset_id": "600001.SH", "quantity": 1, "price": 1},
            {"asset_id": "000001.SZ", "quantity": 1, "price": 1},
            {"asset_id": "600519.SH", "quantity": 1, "price": 1},
        ], Decimal("0"), "alice")
        store.save_current_portfolio("alice", "MOCK", data)
        before = store.get_current_portfolio("alice", "MOCK")
        with TestClient(create_app(store=store)) as client:
            response = client.get(ROOT + "/rebalancing-input", headers={"X-Owner-ID": "alice"})
            assert response.status_code == 200
            assert sum(map(Decimal, response.json()["target_weights"].values())) == 100
            assert response.json()["profile_ready"] is False
        assert store.get_current_portfolio("alice", "MOCK") == before
