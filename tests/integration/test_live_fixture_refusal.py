from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.optimization import PortfolioOptimizationRequest
from app.research import ResearchSpecialistMatrixRequest
from app.runtime.mode import DataMode, reset_runtime_mode_controller
from app.service import (
    AdvisorQueryRequest,
    FixtureAdvisorQueryService,
    FixturePortfolioOptimizationService,
    FixtureResearchSpecialistMatrixService,
)
from app.service.workflow import default_workflow
from app.simulation import ScenarioSimulationRequest
from app.store import SQLiteDecisionEventStore


NOW = datetime(2026, 9, 14, 12, tzinfo=UTC)


@pytest.fixture(autouse=True)
def reset_mode_after_test():
    reset_runtime_mode_controller(DataMode.MOCK)
    yield
    reset_runtime_mode_controller(DataMode.MOCK)


def test_live_mode_refuses_every_default_fixture_research_run() -> None:
    owner = "live-fixture-guard-owner"
    store = SQLiteDecisionEventStore(":memory:")
    client = TestClient(create_app(store, clock=lambda: NOW))
    headers = {"X-Owner-ID": owner}

    advisor_template = FixtureAdvisorQueryService().query_template(owner)
    advisor = AdvisorQueryRequest(
        query_id="live-guard-advisor",
        fixture_id=advisor_template.fixture_id,
        generated_at=advisor_template.generated_at,
        questionnaire=advisor_template.questionnaire,
        portfolio=advisor_template.portfolio,
    )
    optimization_template = FixturePortfolioOptimizationService().template(owner)
    optimization = PortfolioOptimizationRequest(
        request_id="live-guard-optimization",
        owner_id=owner,
        generated_at=optimization_template.generated_at,
        questionnaire=optimization_template.questionnaire,
        portfolio=optimization_template.portfolio,
    )
    simulation = ScenarioSimulationRequest(
        request_id="live-guard-simulation",
        owner_id=owner,
        generated_at=optimization_template.generated_at,
        questionnaire=optimization_template.questionnaire,
        portfolio=optimization_template.portfolio,
    )
    requests = (
        ("/api/v1/advisor/queries", advisor.model_dump(mode="json")),
        ("/api/v1/advisor/research-runs", ResearchSpecialistMatrixRequest(
            matrix_id="specialist-matrix-four-track-001",
            request_id="live-guard-matrix",
            owner_id=owner,
            generated_at=NOW,
        ).model_dump(mode="json")),
        ("/api/v1/advisor/stock-research-runs", {
            "request_id": "live-guard-stock", "owner_id": owner,
            "subject": "PRISM_STOCK_DEMO_F", "period": "2026-Q2",
            "generated_at": NOW.isoformat(),
        }),
        ("/api/v1/advisor/fund-research-runs", {
            "request_id": "live-guard-fund", "owner_id": owner,
            "subject": "PRISM_FUND_DEMO_G", "period": "2026-Q2",
            "generated_at": NOW.isoformat(),
        }),
        ("/api/v1/advisor/convertible-bond-research-runs", {
            "request_id": "live-guard-bond", "owner_id": owner,
            "subject": "PRISM_CONVERTIBLE_BOND_DEMO_H", "period": "2026-Q2",
            "generated_at": NOW.isoformat(),
        }),
        ("/api/v1/advisor/scenario-simulation-runs", simulation.model_dump(mode="json")),
    )

    reset_runtime_mode_controller(DataMode.LIVE)
    fixture_gets = (
        "/api/v1/advisor/query-template",
        "/api/v1/advisor/research-matrix-template",
        "/api/v1/advisor/stock-research-template",
        "/api/v1/advisor/fund-research-template",
        "/api/v1/advisor/convertible-bond-research-template",
        "/api/v1/advisor/portfolio-optimization-template",
        "/api/v1/advisor/scenario-simulation-template",
        "/api/v1/advisor/rebalancing-template",
        "/api/v1/advisor/evaluation-dashboard-summary",
        "/api/v1/advisor/workflow",
    )
    for endpoint in fixture_gets:
        response = client.get(endpoint, headers=headers)
        assert response.status_code == 409, endpoint
        assert response.json()["error_code"] == "LIVE_RESEARCH_NOT_AVAILABLE"
        assert response.json()["status"] == "UNAVAILABLE"
        assert response.json()["actual_source"] is None
        assert response.json()["missing_fields"]

    for endpoint, payload in requests:
        response = client.post(endpoint, headers=headers, json=payload)
        assert response.status_code == 409, endpoint
        assert response.json()["error_code"] == "LIVE_RESEARCH_NOT_AVAILABLE"
        assert "演示数据" in response.json()["message"]

    optimization_response = client.post(
        "/api/v1/advisor/portfolio-optimization-runs",
        headers=headers,
        json=optimization.model_dump(mode="json"),
    )
    assert optimization_response.status_code == 409
    assert optimization_response.json()["error_code"] == "LIVE_PORTFOLIO_REFRESH_REQUIRED"

    workflow = client.post(
        "/api/v1/advisor/workflow-runs",
        headers=headers,
        json={"expected_revision": 1},
    )
    assert workflow.status_code == 409
    assert workflow.json()["error_code"] == "LIVE_RESEARCH_NOT_AVAILABLE"
    workflow_definition = default_workflow(
        FixtureResearchSpecialistMatrixService().matrix_template(owner)
    )
    workflow_save = client.post(
        "/api/v1/advisor/workflow",
        headers=headers,
        json={"definition": workflow_definition.model_dump(mode="json"), "expected_revision": 0},
    )
    assert workflow_save.status_code == 409
    assert workflow_save.json()["error_code"] == "LIVE_RESEARCH_NOT_AVAILABLE"
    store.close()


def test_capability_gap_report_never_marks_fixture_research_available() -> None:
    reset_runtime_mode_controller(DataMode.LIVE)
    client = TestClient(create_app())
    response = client.get(
        "/api/v1/runtime/capability-gaps",
        headers={"X-Owner-ID": "gap-report-owner"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "INCOMPLETE"
    by_capability = {item["capability"]: item for item in body["items"]}
    for capability in ("stock_research", "fund_research", "convertible_bond_research",
                       "specialist_matrix", "advisor", "scenario"):
        item = by_capability[capability]
        assert item["status"] == "UNAVAILABLE"
        assert item["missing"]
        assert item["verification"]


def test_authenticated_workspace_refuses_fixture_even_when_global_mode_is_mock() -> None:
    reset_runtime_mode_controller(DataMode.MOCK)
    client = TestClient(create_app(auth_enabled=True))
    registered = client.post("/api/v1/auth/register", json={
        "username": "fixture-guard-user",
        "password": "fixture-guard-password",
        "password_confirmation": "fixture-guard-password",
    })
    assert registered.status_code == 201
    response = client.get("/api/v1/advisor/stock-research-template")
    assert response.status_code == 409
    assert response.json()["error_code"] == "LIVE_RESEARCH_NOT_AVAILABLE"
    assert response.json()["actual_source"] is None
    for endpoint in (
        "/api/v1/copilot/live-quote?symbol=600519",
        "/api/v1/copilot/live-fund?fund_code=588000",
    ):
        direct = client.get(endpoint)
        assert direct.status_code == 409
        assert direct.json()["error_code"] == "REAL_DATA_MODE_REQUIRED"
        assert direct.json()["actual_source"] is None


@pytest.mark.parametrize("declared_mode", [None, "LIVE"])
def test_fixture_subclass_cannot_bypass_live_guard(declared_mode) -> None:
    attributes = {} if declared_mode is None else {"serving_mode": declared_mode}
    FixtureSubclass = type("FixtureSubclass", (FixtureAdvisorQueryService,), attributes)

    store = SQLiteDecisionEventStore(":memory:")
    client = TestClient(create_app(store, advisor_service=FixtureSubclass()))
    reset_runtime_mode_controller(DataMode.LIVE)

    response = client.get(
        "/api/v1/advisor/query-template",
        headers={"X-Owner-ID": "unmarked-fixture-owner"},
    )

    assert response.status_code == 409
    assert response.json()["error_code"] == "LIVE_RESEARCH_NOT_AVAILABLE"
    store.close()
