"""Controlled adapter tests of the production application composition boundary.

These tests exercise persistence and permissions; their fixed values are not
acceptance evidence for the external market-data service.
"""
from datetime import UTC, datetime
from decimal import Decimal
import asyncio
import json

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.providers.contracts import ProviderRecord, ProviderResult
from app.providers.fingerprint import compute_request_fingerprint
from app.providers.skillhub import WencaiSkillHubProvider
from app.store.sqlite import SQLiteDecisionEventStore


NOW = datetime(2026, 10, 6, tzinfo=UTC)


class ControlledFinancialAdapter(WencaiSkillHubProvider):
    def __init__(self, *, slow=False):
        super().__init__(api_key="test-only")
        self.calls = 0
        self.slow, self.entered, self.cleaned, self.closed = slow, False, False, False

    async def start_http(self):
        pass

    async def aclose(self):
        self.closed = True

    async def execute(self, request, *, skill=None):
        self.calls += 1
        assert skill["skill_id"] == "hithink-finance-query" and skill["version"] == "1.0.0"
        self.entered = True
        if self.slow:
            try:
                await asyncio.Event().wait()
            finally:
                self.cleaned = True
        return ProviderResult(request_id=request.request_id, request_fingerprint=compute_request_fingerprint(request),
            provider=self.name, status="SUCCESS", retrieved_at=NOW,
            records=(ProviderRecord(source="controlled-issuer-report", record_id="test-annual-2025", lineage_id="test-issuer-report-2025",
                period="2025-Q4", observed_at=datetime(2026, 4, 1, tzinfo=UTC),
                fields={"items": [{"股票代码": "600519", "营业收入": "100", "净利润": "20"}]},
                units={"revenue": "CNY", "net_profit": "CNY"}),))


def complete(client, run_id):
    for _ in range(50):
        result = client.get("/api/v1/personal-research/runs/" + run_id)
        assert result.status_code == 200, result.text
        run = result.json()
        if run["status"] not in {"QUEUED", "RUNNING"}:
            return run
    raise AssertionError("controlled personal research did not finish")


def register(client, username):
    client.cookies.clear()
    result = client.post("/api/v1/auth/register", json={"username": username, "password": "test-password-123",
                                                       "password_confirmation": "test-password-123"})
    assert result.status_code == 201, result.text


def test_main_app_private_system_executes_persists_and_isolates_authenticated_owners(tmp_path):
    path = tmp_path / "systems.sqlite3"
    provider = ControlledFinancialAdapter()
    app = create_app(database_path=path, wencai_provider=provider, auth_enabled=True, clock=lambda: NOW)
    with TestClient(app) as client:
        register(client, "alice")
        alice_cookies = dict(client.cookies)
        catalog = client.get("/api/v1/personal-research/catalog").json()
        definition = catalog["templates"][0]["definition"]
        saved = client.put("/api/v1/personal-research/systems/my-profitability",
                           json={"definition": definition, "expected_revision": 0})
        assert saved.status_code == 200 and saved.json()["revision"] == 1
        body = {"expected_revision": 1, "subject": "600519", "period": "2025-Q4"}
        submitted = client.post("/api/v1/personal-research/systems/my-profitability/runs", json=body)
        assert submitted.status_code == 202, submitted.text
        run = complete(client, submitted.json()["run_id"])
        assert run["status"] == "COMPLETED" and Decimal(run["indicators"][0]["value"]) == 20
        assert run["indicators"][0]["unit"] == "%" and run["observers"][0]["matched"] is True
        assert run["system_revision"] == 1 and run["definition_snapshot"] == definition
        refs = run["data_agents"][0]["fact_refs"]
        assert len(refs) == 2
        fact = client.get("/api/v1/research/facts/" + refs[0])
        assert fact.status_code == 200 and fact.json()["input_versions"]["personal_system_revision"] == 1
        assert fact.json()["verified"] is False
        metrics = client.get("/api/v1/runtime/research-metrics").status_code
        assert metrics == 403  # Ordinary users cannot inspect administrator runtime metrics.
        assert app.state.research_runtime.snapshot()["active"] == app.state.research_runtime.snapshot()["provider_active"] == 0
        replay = client.post("/api/v1/personal-research/systems/my-profitability/fact-runs",
            json={**body, "as_of": run["effective_as_of"], "fact_ids": {"finance": refs}})
        assert replay.status_code == 200 and replay.json()["data_mode"] == "STORED_FACTS"
        assert replay.json()["indicators"][0]["value"] == run["indicators"][0]["value"] and provider.calls == 1
        assert app.state.research_runtime.snapshot()["completed"] == 2
        expired = client.post("/api/v1/personal-research/systems/my-profitability/fact-runs",
            json={**body, "as_of": run["effective_as_of"], "fact_ids": {"finance": refs}, "budget_seconds": 0.000001})
        assert expired.status_code == 200 and expired.json()["status"] == "TIMED_OUT"
        assert app.state.research_runtime.snapshot()["timed_out"] == 1 and provider.calls == 1
        register(client, "bob")
        assert client.get("/api/v1/personal-research/systems").json()["items"] == []
        assert client.get("/api/v1/personal-research/systems/my-profitability").status_code == 404
        assert client.get("/api/v1/personal-research/runs/" + run["run_id"]).status_code == 404
        assert client.delete("/api/v1/personal-research/runs/" + run["run_id"]).status_code == 404
        assert client.get("/api/v1/research/facts/" + refs[0]).status_code == 404
    assert provider.closed
    # Reopening the production store preserves the private system and completed run.
    reopened = create_app(database_path=path, wencai_provider=ControlledFinancialAdapter(), auth_enabled=True, clock=lambda: NOW)
    with TestClient(reopened) as client:
        client.cookies.update(alice_cookies)
        assert client.get("/api/v1/personal-research/systems/my-profitability").json()["revision"] == 1
        assert client.get("/api/v1/personal-research/runs/" + run["run_id"]).json()["status"] == "COMPLETED"


def test_application_lifespan_cancels_running_system_before_closing_provider_and_store(tmp_path):
    path = tmp_path / "cancel.sqlite3"
    provider = ControlledFinancialAdapter(slow=True)
    app = create_app(database_path=path, wencai_provider=provider, clock=lambda: NOW)
    headers = {"X-Owner-ID": "alice"}
    with TestClient(app) as client:
        definition = client.get("/api/v1/personal-research/catalog", headers=headers).json()["templates"][0]["definition"]
        assert client.put("/api/v1/personal-research/systems/slow-system", headers=headers,
                          json={"definition": definition, "expected_revision": 0}).status_code == 200
        created = client.post("/api/v1/personal-research/systems/slow-system/runs", headers=headers,
                              json={"expected_revision": 1, "subject": "600519"}).json()
        for _ in range(30):
            running = client.get("/api/v1/personal-research/runs/" + created["run_id"], headers=headers).json()
            if provider.entered:
                break
        assert running["status"] == "RUNNING" and provider.entered
    assert provider.cleaned and provider.closed
    assert app.state.research_runtime.snapshot()["active"] == app.state.research_runtime.snapshot()["provider_active"] == 0
    store = SQLiteDecisionEventStore(path)
    try:
        row = store._connection.execute("SELECT result_json FROM personal_research_runs WHERE owner_id=? AND run_id=?", ("alice", created["run_id"])).fetchone()
        assert json.loads(row["result_json"])["status"] == "CANCELLED"
    finally:
        store.close()


def test_main_app_same_unknown_units_do_not_make_price_to_pe_ratio_calculable(tmp_path):
    class UnknownUnitAdapter(ControlledFinancialAdapter):
        async def execute(self, request, *, skill=None):
            self.calls += 1
            assert skill["skill_id"] == "hithink-market-query"
            return ProviderResult(request_id=request.request_id, request_fingerprint=compute_request_fingerprint(request),
                provider=self.name, status="SUCCESS", retrieved_at=NOW,
                records=(ProviderRecord(source="controlled-market", observed_at=NOW,
                    fields={"items": [{"股票代码": "600519", "最新价": "200", "市盈率": "20"}]},
                    units={"price": "unknown-unit", "pe": "unknown-unit"}),))

    provider = UnknownUnitAdapter()
    app = create_app(database_path=tmp_path / "units.sqlite3", wencai_provider=provider, clock=lambda: NOW)
    headers = {"X-Owner-ID": "alice"}
    definition = {"name": "报价估值观察", "data_agents": [{"agent_id": "market", "name": "行情助手",
        "skill_id": "hithink-market-query", "version": "1.0.0", "fields": ["price", "pe"]}],
        "indicators": [{"indicator_id": "ratio", "name": "自定义比率", "operator": "ratio_pct", "inputs": ["market.price", "market.pe"]}]}
    with TestClient(app) as client:
        assert client.put("/api/v1/personal-research/systems/unit-check", headers=headers,
                          json={"definition": definition, "expected_revision": 0}).status_code == 200
        submitted = client.post("/api/v1/personal-research/systems/unit-check/runs", headers=headers,
                               json={"expected_revision": 1, "subject": "600519"})
        assert submitted.status_code == 202
        for _ in range(50):
            run = client.get("/api/v1/personal-research/runs/" + submitted.json()["run_id"], headers=headers).json()
            if run["status"] not in {"QUEUED", "RUNNING"}:
                break
        assert run["status"] == "PARTIAL"
        indicator = run["indicators"][0]
        assert indicator["status"] == "UNAVAILABLE" and indicator["value"] is None
        assert indicator["reason"] == "UNSUPPORTED_UNIT" and "单位" in indicator["reason_message"]
