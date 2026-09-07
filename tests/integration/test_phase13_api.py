from datetime import UTC, datetime
from decimal import Decimal
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.api import create_app
from app.gates import GateStatus
from app.recommendation import (
    RecommendationCompositionResult,
    RecommendationIssue,
    RecommendationIssueCode,
    compose_recommendations,
)
from app.store import SQLiteDecisionEventStore
from tests.recommendation_scenario import build_recommendation_case


OWNER = "gate-owner-001"
RECORDED_AT = datetime(2026, 9, 2, 3, 0, tzinfo=UTC)
DECISION_EVENT_FIXTURE = (
    Path(__file__).parents[1]
    / "fixtures"
    / "decision-events"
    / "decision_event_cases.json"
)


def _result(level=None):
    case = build_recommendation_case(level) if level is not None else build_recommendation_case()
    return compose_recommendations(
        profile=case.profile,
        portfolio=case.portfolio,
        exposure=case.exposure,
        concentration=case.concentration,
        assessment=case.assessment,
        allocation=case.allocation,
        pipeline=case.pipeline,
        candidate=case.candidate,
        decision_gate=case.decision_gate,
        generated_at=case.generated_at,
    )


def _client():
    store = SQLiteDecisionEventStore(":memory:")
    return TestClient(create_app(store, clock=lambda: RECORDED_AT)), store


def test_decision_event_fixture_declares_all_mvp_states_without_private_payload() -> None:
    fixture = json.loads(DECISION_EVENT_FIXTURE.read_text(encoding="utf-8"))
    assert fixture["schema_version"] == "decision-event-fixture.v1"
    assert {item["expected_status"] for item in fixture["cases"]} == {
        "PASS",
        "REVIEW_REQUIRED",
        "BLOCKED",
    }
    assert {item["expected_action"] for item in fixture["cases"]} >= {
        "HOLD",
        "REDUCE",
        None,
    }
    serialized = json.dumps(fixture, ensure_ascii=False)
    assert "raw_provider_payload" in serialized
    assert "credential" in serialized
    assert "api_key" not in serialized.casefold()
    assert "password" not in serialized.casefold()


def test_api_health_and_decision_event_round_trip_are_owner_scoped() -> None:
    client, store = _client()
    result = _result()
    payload = result.model_dump(mode="json")

    health = client.get("/api/health")
    assert health.status_code == 200
    health_data = health.json()
    assert health_data["status"] == "ok"
    assert health_data["schema_version"] == "decision-event.v1"
    assert health_data["data_mode"] in ("MOCK", "LIVE")
    assert "capabilities" in health_data

    created = client.post(
        "/api/v1/decision-events",
        headers={"X-Owner-ID": OWNER},
        json=payload,
    )
    assert created.status_code == 200
    assert created.json()["created"] is True
    event_id = created.json()["event"]["event_id"]
    assert created.json()["event"]["receipt_id"] == result.receipt.receipt_id

    repeated = client.post(
        "/api/v1/decision-events",
        headers={"X-Owner-ID": OWNER},
        json=payload,
    )
    assert repeated.status_code == 200
    assert repeated.json()["created"] is False
    assert repeated.json()["event"] == created.json()["event"]

    listing = client.get(
        "/api/v1/decision-events", headers={"X-Owner-ID": OWNER}
    )
    assert listing.status_code == 200
    assert len(listing.json()["items"]) == 1
    detail = client.get(
        f"/api/v1/decision-events/{event_id}", headers={"X-Owner-ID": OWNER}
    )
    assert detail.status_code == 200
    assert detail.json()["event_id"] == event_id
    assert detail.json()["result"]["status"] == GateStatus.PASS.value

    other = client.get(
        "/api/v1/decision-events", headers={"X-Owner-ID": "other-owner"}
    )
    assert other.status_code == 200 and other.json()["items"] == []
    hidden = client.get(
        f"/api/v1/decision-events/{event_id}", headers={"X-Owner-ID": "other-owner"}
    )
    assert hidden.status_code == 404
    assert "receipt-owner-001" not in hidden.text
    store.close()


def test_api_rejects_scope_missing_body_tampering_and_sensitive_errors() -> None:
    client, store = _client()
    result = _result()
    payload = result.model_dump(mode="json")

    missing_owner = client.post("/api/v1/decision-events", json=payload)
    assert missing_owner.status_code == 403
    assert "receipt-owner-001" not in missing_owner.text

    wrong_owner = client.post(
        "/api/v1/decision-events",
        headers={"X-Owner-ID": "other-owner"},
        json=payload,
    )
    assert wrong_owner.status_code == 403
    assert result.summary not in wrong_owner.text

    invalid = client.post(
        "/api/v1/decision-events",
        headers={"X-Owner-ID": OWNER},
        json={"summary": "保证收益率达到20%", "owner_id": OWNER},
    )
    assert invalid.status_code == 422
    assert invalid.json() == {
        "schema_version": "api-error.v1",
        "error_code": "INVALID_INPUT",
        "message": "request failed contract validation",
    }
    assert "保证收益" not in invalid.text

    forged = result.model_copy(update={"summary": "保证收益率达到20%"})
    forged_response = client.post(
        "/api/v1/decision-events",
        headers={"X-Owner-ID": OWNER},
        json=forged.model_dump(mode="json"),
    )
    assert forged_response.status_code == 400
    assert forged_response.json()["error_code"] == "STORE_ERROR"
    assert "保证收益" not in forged_response.text

    sensitive_header = client.get(
        "/api/v1/decision-events", headers={"X-Owner-ID": "api_key-owner"}
    )
    assert sensitive_header.status_code == 403
    assert "api_key" not in sensitive_header.text
    store.close()


def test_api_preserves_review_and_blocked_events_without_receipt() -> None:
    client, store = _client()
    case = build_recommendation_case()
    partial_snapshot = case.portfolio.fund_holdings[0].model_copy(
        update={"coverage_pct": Decimal("80")}
    )
    portfolio = case.portfolio.model_copy(
        update={"fund_holdings": (partial_snapshot,)}
    )
    from app.allocation import build_allocation_envelope
    from app.portfolio import calculate_exposure
    from app.risk import assess_risk_budget, calculate_concentration
    from app.gates import evaluate_decision_gates

    exposure = calculate_exposure(portfolio)
    concentration = calculate_concentration(exposure)
    assessment = assess_risk_budget(case.profile, concentration)
    allocation = build_allocation_envelope(
        case.profile, exposure, concentration, assessment
    )
    gate = evaluate_decision_gates(
        case.profile, case.pipeline, assessment, allocation, case.candidate
    )
    review = compose_recommendations(
        profile=case.profile,
        portfolio=portfolio,
        exposure=exposure,
        concentration=concentration,
        assessment=assessment,
        allocation=allocation,
        pipeline=case.pipeline,
        candidate=case.candidate,
        decision_gate=gate,
        generated_at=case.generated_at,
    )
    assert review.status == GateStatus.REVIEW_REQUIRED
    response = client.post(
        "/api/v1/decision-events",
        headers={"X-Owner-ID": OWNER},
        json=review.model_dump(mode="json"),
    )
    assert response.status_code == 200
    body = response.json()["event"]["result"]
    assert body["receipt"] is None
    assert body["trace"] == {
        "evidence": [],
        "facts": [],
        "findings": [],
        "recommendations": [],
    }
    assert body["summary"] is None
    store.close()


def test_api_static_workbench_has_explainable_sections() -> None:
    client, store = _client()
    page = client.get("/")
    assert page.status_code == 200
    assert "决策工作台" in page.text
    assert "证据链" in page.text
    assert "风险画像" in page.text
    css = client.get("/static/styles.css")
    js = client.get("/static/app.js")
    assert css.status_code == 200 and "--clay" in css.text
    assert js.status_code == 200 and "textContent" in js.text
    store.close()


def test_api_conflict_does_not_overwrite_a_decision_event() -> None:
    client, store = _client()
    first = RecommendationCompositionResult(
        composition_id="api-conflict-composition",
        owner_id=OWNER,
        status=GateStatus.BLOCKED,
        issues=(
            RecommendationIssue(
                code=RecommendationIssueCode.INVALID_INPUT,
                safe_message="first safe refusal",
            ),
        ),
    )
    second = first.model_copy(
        update={
            "issues": (
                RecommendationIssue(
                    code=RecommendationIssueCode.INVALID_INPUT,
                    safe_message="different safe refusal",
                ),
            )
        }
    )
    first_response = client.post(
        "/api/v1/decision-events",
        headers={"X-Owner-ID": OWNER},
        json=first.model_dump(mode="json"),
    )
    second_response = client.post(
        "/api/v1/decision-events",
        headers={"X-Owner-ID": OWNER},
        json=second.model_dump(mode="json"),
    )
    assert first_response.status_code == 200
    assert second_response.status_code == 409
    assert second_response.json()["error_code"] == "CONFLICT"
    assert "different safe refusal" not in second_response.text
    assert len(client.get("/api/v1/decision-events", headers={"X-Owner-ID": OWNER}).json()["items"]) == 1
    store.close()
