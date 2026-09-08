from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
import tempfile

from fastapi.testclient import TestClient

from app.api import create_app
from app.service import FixtureAdvisorQueryService, confirm_questionnaire
from app.store import SQLiteDecisionEventStore


NOW = datetime(2026, 9, 2, 4, 0, tzinfo=UTC)


def _client(database: str | Path = ":memory:"):
    store = SQLiteDecisionEventStore(database)
    return TestClient(create_app(store, clock=lambda: NOW)), store


def _payload(owner: str = "phase29-api-owner") -> dict[str, object]:
    template = FixtureAdvisorQueryService().query_template(owner)
    profile = confirm_questionnaire(template.questionnaire)
    return {
        "schema_version": "context-memory-write-request.v1",
        "owner_id": owner,
        "questionnaire": template.questionnaire.model_dump(mode="json"),
        "profile": profile.model_dump(mode="json"),
        "portfolio": template.portfolio.model_dump(mode="json"),
        "references": {
            "research_matrix_id": "matrix-api-001",
            "research_run_id": "run-api-001",
            "research_scenario_id": "BASELINE_READY",
            "optimization_request_id": "optimization-api-001",
            "optimization_scenario_id": "BASELINE_READY",
        },
    }


def test_api_context_memory_is_idempotent_owner_scoped_and_has_no_event_side_effect() -> None:
    client, store = _client()
    payload = _payload()
    first = client.post(
        "/api/v1/advisor/context-memory",
        headers={"X-Owner-ID": "phase29-api-owner"},
        json=payload,
    )
    assert first.status_code == 200
    assert first.json()["created"] is True
    record = first.json()["record"]
    assert record["source"] == "EXPLICIT_SAVE"
    assert record["memory_id"].startswith("context-memory:")
    assert len(record["content_hash"]) == 64

    repeated = client.post(
        "/api/v1/advisor/context-memory",
        headers={"X-Owner-ID": "phase29-api-owner"},
        json=payload,
    )
    assert repeated.status_code == 200
    assert repeated.json()["created"] is False
    assert repeated.json()["record"] == record
    assert store.list("phase29-api-owner") == ()

    listed = client.get(
        "/api/v1/advisor/context-memory?limit=1",
        headers={"X-Owner-ID": "phase29-api-owner"},
    )
    assert listed.status_code == 200
    assert listed.json()["records"] == [record]
    assert client.get(
        "/api/v1/advisor/context-memory",
        headers={"X-Owner-ID": "different-owner"},
    ).json()["records"] == []
    store.close()


def test_historical_search_is_scoped_and_never_restores_current_state():
    client, store = _client()
    headers = {"X-Owner-ID":"phase29-api-owner"}
    with client:
        saved = client.post("/api/v1/advisor/context-memory", headers=headers, json=_payload())
        assert saved.status_code == 200
        result = client.post("/api/v1/advisor/context-memory/search", headers=headers, json={"query":"基金"})
        assert result.status_code == 200
        body = result.json()
        assert body["status"] == "HISTORICAL_ONLY"
        assert body["candidate_count"] == 1
        assert body["matches"][0]["memory_id"] == saved.json()["record"]["memory_id"]
        assert store.get_current_portfolio("phase29-api-owner", "MOCK") is None
        assert store.get_latest_questionnaire_snapshot("phase29-api-owner") is None
        assert client.post("/api/v1/advisor/context-memory/search", headers={"X-Owner-ID":"other"},
                           json={"query":"基金"}).json()["candidate_count"] == 0
        assert client.post("/api/v1/advisor/context-memory/search", headers=headers,
                           json={"query":"password=test"}).status_code == 422


def test_api_context_memory_rejects_cross_owner_sensitive_and_limit_inputs() -> None:
    client, store = _client()
    payload = _payload()
    forbidden = client.post(
        "/api/v1/advisor/context-memory",
        headers={"X-Owner-ID": "different-owner"},
        json=payload,
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error_code"] == "OWNER_SCOPE"

    forged = dict(payload)
    forged["memory_id"] = "context-memory:" + "0" * 32
    response = client.post(
        "/api/v1/advisor/context-memory",
        headers={"X-Owner-ID": "phase29-api-owner"},
        json=forged,
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "INVALID_INPUT"

    sensitive = _payload("safe-owner")
    sensitive["owner_id"] = "api_key-owner"
    response = client.post(
        "/api/v1/advisor/context-memory",
        headers={"X-Owner-ID": "api_key-owner"},
        json=sensitive,
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "INVALID_INPUT"

    for limit in (0, 101):
        response = client.get(
            f"/api/v1/advisor/context-memory?limit={limit}",
            headers={"X-Owner-ID": "phase29-api-owner"},
        )
        assert response.status_code == 422
        assert response.json()["error_code"] == "INVALID_INPUT"
    store.close()


def test_api_context_memory_persists_across_restart_and_missing_owner_is_safe() -> None:
    temp_dir = tempfile.TemporaryDirectory()
    database = Path(temp_dir.name) / "phase29.sqlite3"
    client, store = _client(database)
    payload = _payload("restart-owner")
    created = client.post(
        "/api/v1/advisor/context-memory",
        headers={"X-Owner-ID": "restart-owner"},
        json=payload,
    )
    assert created.status_code == 200
    memory_id = created.json()["record"]["memory_id"]
    store.close()

    reopened_client, reopened_store = _client(database)
    response = reopened_client.get(
        "/api/v1/advisor/context-memory",
        headers={"X-Owner-ID": "restart-owner"},
    )
    assert response.status_code == 200
    assert response.json()["records"][0]["memory_id"] == memory_id
    missing = reopened_client.get(
        "/api/v1/advisor/context-memory",
        headers={},
    )
    assert missing.status_code == 403
    reopened_store.close()
    temp_dir.cleanup()


def test_api_context_memory_corruption_returns_safe_store_corrupt_error() -> None:
    client, store = _client()
    created = client.post(
        "/api/v1/advisor/context-memory",
        headers={"X-Owner-ID": "corrupt-owner"},
        json=_payload("corrupt-owner"),
    )
    assert created.status_code == 200
    memory_id = created.json()["record"]["memory_id"]
    store._connection.execute(
        "UPDATE context_memory SET content_hash = ? WHERE memory_id = ?",
        ("f" * 64, memory_id),
    )
    response = client.get(
        "/api/v1/advisor/context-memory",
        headers={"X-Owner-ID": "corrupt-owner"},
    )
    assert response.status_code == 500
    assert response.json() == {
        "schema_version": "api-error.v1",
        "error_code": "STORE_CORRUPT",
        "message": "stored context memory failed integrity validation",
    }
    store.close()


def test_api_context_memory_100_owner_writes_are_isolated_and_idempotent() -> None:
    client, store = _client()
    payloads = tuple(_payload(f"owner-{index:03d}") for index in range(100))

    def write(payload: dict[str, object]):
        owner = str(payload["owner_id"])
        response = client.post(
            "/api/v1/advisor/context-memory",
            headers={"X-Owner-ID": owner},
            json=payload,
        )
        return owner, response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=16) as executor:
        results = tuple(executor.map(write, payloads))
    assert all(status == 200 for _, status, _ in results)
    assert all(body["created"] is True for _, _, body in results)
    for owner, _, body in results:
        listed = client.get(
            "/api/v1/advisor/context-memory",
            headers={"X-Owner-ID": owner},
        )
        assert listed.status_code == 200
        assert [item["owner_id"] for item in listed.json()["records"]] == [owner]
        assert listed.json()["records"][0]["memory_id"] == body["record"]["memory_id"]
    assert sum(len(store.list_context_memory(owner)) for owner, _, _ in results) == 100
    store.close()
