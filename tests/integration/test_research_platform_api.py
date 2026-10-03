from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.providers.contracts import ProviderRecord, ProviderResult
from app.providers.fingerprint import compute_request_fingerprint
from app.providers.skillhub import WencaiSkillHubProvider


NOW = datetime(2026, 10, 1, tzinfo=UTC)
BODY = {"nodes": [{"node_id": "stock", "operation": "MARKET_DATA", "subject": "600519", "required_fields": ["price"]}]}


class ControlledTestProvider(WencaiSkillHubProvider):
    def __init__(self):
        super().__init__(api_key="test-only")
        self.calls = 0

    async def execute(self, request, *, skill=None):
        self.calls += 1
        return ProviderResult(request_id=request.request_id, request_fingerprint=compute_request_fingerprint(request),
            provider=self.name, status="SUCCESS", retrieved_at=NOW,
            records=(ProviderRecord(source="upstream-original", record_id="record-one", observed_at=NOW,
                fields={"items": [{"股票代码": "600519", "最新价": "123.50"}]}, units={"price": "CNY"}),))


def complete(client, run_id, headers=None):
    for _ in range(30):
        response = client.get(f"/api/v1/research/runs/{run_id}", headers=headers)
        assert response.status_code == 200
        value = response.json()
        if value["status"] not in {"QUEUED", "RUNNING"}:
            return value
    raise AssertionError("controlled research did not complete")


def test_main_app_live_research_and_global_skill_gate(tmp_path):
    provider = ControlledTestProvider()
    app = create_app(database_path=tmp_path / "research.sqlite3", wencai_provider=provider)
    with TestClient(app) as client:
        headers = {"X-Owner-ID": "alice"}
        response = client.post("/api/v1/research/runs", headers=headers, json=BODY)
        assert response.status_code == 202, response.text
        run = complete(client, response.json()["run_id"], headers)
        assert run["status"] == "COMPLETED"
        assert run["is_synthetic"] is False
        assert run["verification_status"] == "SINGLE_SOURCE_UNVERIFIED"
        assert run["nodes"][0]["observations"][0]["actual_source"] == "upstream-original"
        assert client.get(f"/api/v1/research/runs/{run['run_id']}", headers={"X-Owner-ID": "bob"}).status_code == 404
        metrics = client.get("/api/v1/runtime/research-metrics", headers=headers).json()
        assert metrics["peak_active"] >= 1 and metrics["active"] == 0
        assert client.patch("/api/v1/skills/hithink-market-query/1.0.0", headers=headers,
                            json={"action": "disable", "expected_revision": 1}).status_code == 200
        second = client.post("/api/v1/research/runs", headers=headers, json=BODY).json()
        assert complete(client, second["run_id"], headers)["status"] == "FAILED"
        assert provider.calls == 1


def test_authenticated_personal_skill_gate_and_run_ownership(tmp_path):
    provider = ControlledTestProvider()
    app = create_app(database_path=tmp_path / "owners.sqlite3", wencai_provider=provider, auth_enabled=True)
    with TestClient(app) as client:
        for username in ("alice", "bob"):
            client.cookies.clear()
            response = client.post("/api/v1/auth/register", json={"username": username,
                "password": "test-password-123", "password_confirmation": "test-password-123"})
            assert response.status_code == 201
            assert client.get("/api/v1/runtime/research-metrics").status_code == 403
            assert client.patch("/api/v1/skills/hithink-market-query/1.0.0",
                json={"action": "disable", "expected_revision": 1}).status_code == 403
            if username == "alice":
                assert client.put("/api/v1/skills/hithink-market-query/selection",
                    json={"enabled": False, "expected_revision": 0}).status_code == 200
                created = client.post("/api/v1/research/runs", json=BODY)
                assert created.status_code == 202
                alice_run = complete(client, created.json()["run_id"])
                assert alice_run["status"] == "FAILED"
                assert provider.calls == 0
            else:
                assert client.get(f"/api/v1/research/runs/{alice_run['run_id']}").status_code == 404
                assert client.delete(f"/api/v1/research/runs/{alice_run['run_id']}").status_code == 404
                created = client.post("/api/v1/research/runs", json=BODY)
                assert complete(client, created.json()["run_id"])["status"] == "COMPLETED"
                assert provider.calls == 1


def test_live_template_endpoints_and_future_cutoff_contract(tmp_path):
    provider = ControlledTestProvider()
    app = create_app(database_path=tmp_path / "templates.sqlite3", wencai_provider=provider, clock=lambda: NOW)
    with TestClient(app) as client:
        headers = {"X-Owner-ID": "alice"}
        templates = client.get("/api/v1/research/templates", headers=headers)
        assert templates.status_code == 200
        assert templates.json()["items"][0]["template_id"] == "live-equity-basic.v1"
        future = client.post("/api/v1/research/runs/from-template", headers=headers, json={
            "template_id": "live-equity-basic.v1", "subject": "600519", "as_of": "2027-01-01T00:00:00Z"})
        assert future.status_code == 422
        assert future.json()["error_code"] == "RESEARCH_AS_OF_FUTURE"
        assert provider.calls == 0
        created = client.post("/api/v1/research/runs/from-template", headers=headers, json={
            "template_id": "live-equity-basic.v1", "subject": "600519", "as_of": NOW.isoformat()})
        assert created.status_code == 202
        final = complete(client, created.json()["run_id"], headers)
        assert final["as_of"] == NOW.isoformat()
        assert len(final["nodes"]) == 2
        assert provider.calls == 2
        assert client.post("/api/v1/research/runs", headers=headers, json={**BODY, "as_of": "2026-09-01T00:00:00"}).status_code == 422
