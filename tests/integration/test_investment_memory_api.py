from datetime import UTC, datetime
from decimal import Decimal

from fastapi import FastAPI, Header
from fastapi.testclient import TestClient

from app.api.investment_memory_routes import create_investment_memory_router
from app.llm.ocr_portfolio_parser import recalculate_portfolio_values
from app.portfolio import PortfolioImportBundle
from app.rebalancing.contracts import PortfolioRebalancingRequest
from app.service import FixtureAdvisorQueryService, confirm_questionnaire
from app.service.investment_memory import InvestmentMemoryService
from app.store import SQLiteDecisionEventStore


NOW = datetime(2026, 10, 6, 8, tzinfo=UTC)


def client_for(store):
    app = FastAPI()
    def owner_dependency(x_owner_id: str = Header()):
        return x_owner_id
    def builder(owner_id, body):
        bundle = PortfolioImportBundle.model_validate(recalculate_portfolio_values([
            {"asset_id": "600001.SH", "quantity": 5000, "price": 10},
            {"asset_id": "000001.SZ", "quantity": 3000, "price": 10},
        ], Decimal("20000"), owner_id)["portfolio"])
        return PortfolioRebalancingRequest(
            request_id="api-comparison", owner_id=owner_id, generated_at=NOW, bundle=bundle,
            confirmed_profile=confirm_questionnaire(FixtureAdvisorQueryService().query_template(owner_id).questionnaire),
            target_weights=body.target_weights, deadband_pct=body.deadband_pct,
            max_turnover_pct=body.max_turnover_pct, minimum_cash_pct=body.minimum_cash_pct,
        )
    app.include_router(create_investment_memory_router(
        service=InvestmentMemoryService(store, clock=lambda: NOW),
        owner_dependency=owner_dependency, rebalance_request_builder=builder))
    return TestClient(app)


ROOT = "/api/v1/advisor/investment-memory"


def save_and_confirm(client, headers):
    saved = client.put(ROOT, headers=headers, json={"expected_revision": 0,
        "preferences": {"max_turnover_pct": "5", "deadband_pct": "1", "minimum_cash_pct": "10"}})
    assert saved.status_code == 200
    state = saved.json()
    candidate = state["candidate"]
    confirmation = client.post(ROOT + "/policy/confirm", headers=headers, json={
        "candidate_id": candidate["candidate_id"],
        "expected_memory_revision": candidate["memory_revision"],
        "expected_style_profile_version": candidate["style_profile_version"],
    })
    assert confirmation.status_code == 200
    assert confirmation.json()["policy_status"] == "ACTIVE"
    return confirmation.json()


def test_api_confirm_and_real_order_comparison_are_owner_scoped():
    store = SQLiteDecisionEventStore()
    client = client_for(store)
    owner = {"X-Owner-ID": "memory-api-owner"}
    state = save_and_confirm(client, owner)
    response = client.post(ROOT + "/rebalancing-preview", headers=owner, json={
        "expected_policy_revision": state["policy"]["revision"],
        "target_weights": {"600001.SH": "10", "000001.SZ": "50", "CASH-CNY": "40"},
    })
    assert response.status_code == 200
    comparison = response.json()
    assert Decimal(comparison["personalized"]["metrics"]["total_turnover_pct"]) <= 5
    assert Decimal(comparison["personalized"]["metrics"]["total_turnover_pct"]) < Decimal(comparison["baseline"]["metrics"]["total_turnover_pct"])
    assert comparison["effective_target_weights"] != comparison["source_target_weights"]
    assert comparison["policy"]["owner_id"] == "memory-api-owner"
    outsider = {"X-Owner-ID": "another-api-owner"}
    assert client.get(ROOT, headers=outsider).json()["memory"] is None
    denied = client.post(ROOT + "/rebalancing-preview", headers=outsider, json={
        "expected_policy_revision": 1,
        "target_weights": {"600001.SH": "10", "000001.SZ": "50", "CASH-CNY": "40"},
    })
    assert denied.status_code == 409
    assert denied.json()["detail"] == "INVESTMENT_POLICY_STALE"
    store.close()


def test_api_updates_stale_policy_and_rejects_model_owner_or_invalid_numbers():
    store = SQLiteDecisionEventStore()
    client = client_for(store)
    headers = {"X-Owner-ID": "memory-api-owner"}
    state = save_and_confirm(client, headers)
    assert client.put(ROOT, headers=headers, json={"owner_id": "victim", "expected_revision": 1,
                                                   "preferences": {}}).status_code == 422
    assert client.put(ROOT, headers=headers, json={"expected_revision": 1,
        "preferences": {"max_turnover_pct": "NaN"}}).status_code == 422
    update = client.put(ROOT, headers=headers, json={"expected_revision": 1, "preferences": {}})
    assert update.json()["policy_status"] == "STALE"
    assert client.put(ROOT, headers=headers, json={"expected_revision": 1, "preferences": {}}).status_code == 409
    preview = client.post(ROOT + "/rebalancing-preview", headers=headers, json={
        "expected_policy_revision": state["policy"]["revision"],
        "target_weights": {"600001.SH": "10", "000001.SZ": "50", "CASH-CNY": "40"},
    })
    assert preview.status_code == 409
    assert client.post(ROOT + "/rebalancing-preview", headers=headers, json={
        "expected_policy_revision": 1, "target_weights": {"600001.SH": "99"},
    }).status_code == 422
    store.close()
