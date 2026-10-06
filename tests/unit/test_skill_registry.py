import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.research_routes import create_research_router
from app.providers.contracts import ProviderOperation, ProviderRequest, ProviderResult, ProviderRecord
from app.providers.fingerprint import compute_request_fingerprint
from app.providers.skillhub import WencaiSkillHubProvider, load_iwencai_skill_manifest
from app.service.skill_registry import SkillMetadata, SkillRegistry, SkillUnavailable
from app.store.sqlite import SQLiteDecisionEventStore, StoreConflictError


@pytest.fixture
def store(tmp_path):
    store = SQLiteDecisionEventStore(tmp_path / "skills.sqlite3")
    try:
        # The production migration is owned by the platform integration layer.
        store._connection.execute("CREATE TABLE IF NOT EXISTS skill_versions (skill_id TEXT,version TEXT,metadata_json TEXT NOT NULL,status TEXT NOT NULL,enabled INTEGER NOT NULL,revision INTEGER NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(skill_id,version))")
        store._connection.execute("CREATE TABLE IF NOT EXISTS skill_selections (owner_id TEXT,skill_id TEXT,enabled INTEGER NOT NULL,revision INTEGER NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(owner_id,skill_id))")
        yield store
    finally:
        store.close()


def test_global_and_personal_disable_prevent_actual_provider_calls(store):
    registry = SkillRegistry(store)
    provider = WencaiSkillHubProvider(api_key="test-only")
    provider.bind_registry(registry)
    request = ProviderRequest(request_id="test", operation="MARKET_DATA", subject="600519")
    assert provider._skill_for(request)["skill_id"] == "hithink-market-query"
    registry.select("alice", "hithink-market-query", enabled=False, expected_revision=0)
    denied = asyncio.run(registry.scoped_provider(provider, "alice").execute(request))
    assert denied.status.value == "FAILED"
    assert denied.issues[0].code.value == "PERMISSION_DENIED"
    assert registry.resolve(request, "bob").skill_id == "hithink-market-query"
    registry.update("hithink-market-query", "1.0.0", action="disable", expected_revision=1)
    with pytest.raises(SkillUnavailable):
        registry.resolve(request, "bob")
    result = asyncio.run(provider.execute(request))
    assert result.status.value == "FAILED"


def test_exact_skill_reference_cannot_silently_use_another_adapter_or_version(store):
    registry = SkillRegistry(store)

    class Provider:
        name = "exact-reference-test"
        calls = 0

        async def execute(self, request):
            self.calls += 1
            return ProviderResult(request_id=request.request_id,
                request_fingerprint=compute_request_fingerprint(request), provider=self.name,
                status="EMPTY", retrieved_at=registry.clock(), scope_description="controlled exact-reference test")

    provider = Provider()
    request = ProviderRequest(request_id="exact", operation="MARKET_DATA", subject="600519")
    chosen = registry.scoped_provider(provider, "alice", skill_id="hithink-market-query", version="1.0.0")
    assert asyncio.run(chosen.execute(request)).status.value == "EMPTY"
    assert provider.calls == 1
    registry.update("hithink-market-query", "1.0.0", action="disable", expected_revision=1)
    # A different approved adapter does not satisfy a pinned private recipe.
    metadata = SkillMetadata(skill_id="alternate-market", version="1.0.0", name="替代行情",
                             operation="MARKET_DATA", endpoint="/v1/query2data")
    registry.install(metadata)
    registry.update(metadata.skill_id, metadata.version, action="verified", expected_revision=1)
    assert registry.resolve(request, "alice").skill_id == "alternate-market"
    assert asyncio.run(chosen.execute(request)).issues[0].code.value == "PERMISSION_DENIED"
    wrong_operation = registry.scoped_provider(provider, "alice", skill_id=metadata.skill_id, version=metadata.version)
    denied = asyncio.run(wrong_operation.execute(request.model_copy(update={"operation": ProviderOperation.COMPANY_DATA})))
    assert denied.status.value == "FAILED"
    assert provider.calls == 1
    with pytest.raises(ValueError):
        registry.scoped_provider(provider, "alice", skill_id="alternate-market")


def test_new_version_is_pending_and_activation_disables_old_version(store):
    registry = SkillRegistry(store)
    payload = dict(load_iwencai_skill_manifest()["skills"][3], version="1.1.0")
    metadata = SkillMetadata.model_validate(payload)
    assert registry.install(metadata)["status"] == "PENDING"
    with pytest.raises(SkillUnavailable):
        registry.update(metadata.skill_id, metadata.version, action="enable", expected_revision=1)
    activated = registry.update(metadata.skill_id, metadata.version, action="verified", expected_revision=1)
    assert activated["enabled"]
    assert not registry.get(metadata.skill_id, "1.0.0")["enabled"]
    with pytest.raises(StoreConflictError):
        registry.update(metadata.skill_id, metadata.version, action="disable", expected_revision=1)
    registry.update(metadata.skill_id, metadata.version, action="uninstall", expected_revision=2)
    request = ProviderRequest(request_id="test", operation="MARKET_DATA", subject="600519")
    with pytest.raises(SkillUnavailable):
        registry.resolve(request)
    SkillRegistry(store)  # Restart must not reinstall disabled/uninstalled skills.
    with pytest.raises(SkillUnavailable):
        registry.resolve(request)


def test_untrusted_route_and_extra_fields_are_rejected():
    payload = dict(load_iwencai_skill_manifest()["skills"][3])
    payload["endpoint"] = "https://untrusted.invalid/run"
    with pytest.raises(ValueError):
        SkillMetadata.model_validate(payload)
    payload["endpoint"] = "/v1/comprehensive/search"
    with pytest.raises(ValueError):
        SkillMetadata.model_validate(payload)


def test_selection_revisions_and_user_isolation(store):
    registry = SkillRegistry(store)
    skill_id = "hithink-market-query"
    registry.select("alice", skill_id, enabled=False, expected_revision=0)
    with pytest.raises(StoreConflictError):
        registry.select("alice", skill_id, enabled=True, expected_revision=0)
    alice = next(row for row in registry.list("alice") if row["skill_id"] == skill_id)
    bob = next(row for row in registry.list("bob") if row["skill_id"] == skill_id)
    assert not alice["callable"] and bob["callable"]


def test_registry_routes_require_admin_and_bind_selection_to_owner(store):
    app = FastAPI()
    registry = SkillRegistry(store)
    app.include_router(create_research_router(store=store, provider=WencaiSkillHubProvider(),
                       owner_dependency=lambda: "alice", auth_enabled=True, registry=registry))
    with TestClient(app) as client:
        response = client.patch("/api/v1/skills/hithink-market-query/1.0.0",
                                json={"action": "disable", "expected_revision": 1})
        assert response.status_code == 403
        response = client.put("/api/v1/skills/hithink-market-query/selection",
                              json={"enabled": False, "expected_revision": 0})
        assert response.status_code == 200
        assert any(row["skill_id"] == "hithink-market-query" and not row["callable"]
                   for row in client.get("/api/v1/skills").json()["items"])


@pytest.mark.parametrize("items,passed", [
    ([], False), ([{}], False), (["connected"], False),
    ([{"price": None}], False), ([{"price": ""}], False),
    ([{"price": 0}], True), ([{"price": "123.45"}], True),
])
def test_probe_requires_observed_row_contract(store, items, passed):
    registry = SkillRegistry(store)
    metadata = SkillMetadata.model_validate(dict(load_iwencai_skill_manifest()["skills"][3], version="1.1.0"))
    registry.install(metadata)

    class ProbeProvider:
        async def execute(self, request, *, skill):
            return ProviderResult(request_id=request.request_id,
                request_fingerprint=compute_request_fingerprint(request), provider="probe-only",
                status="SUCCESS", retrieved_at=registry.clock(),
                records=(ProviderRecord(source="controlled probe", fields={"items": items}),))

    result = asyncio.run(registry.probe(metadata.skill_id, metadata.version,
        expected_revision=1, provider=ProbeProvider()))
    assert result["status"] == ("PASS" if passed else "FAILED")
    assert registry.get(metadata.skill_id, metadata.version)["status"] == ("INSTALLED" if passed else "PENDING")
