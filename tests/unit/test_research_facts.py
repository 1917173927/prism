import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3

import pytest

from app.providers.contracts import ProviderRecord, ProviderRequest, ProviderResult
from app.providers.fingerprint import compute_request_fingerprint
from app.service.live_research import LiveResearchNode, LiveResearchRequest, LiveResearchService, normalize_live_observations
from app.service.research_facts import ResearchFactNotFound, ResearchFactRepository
from app.service.research_runtime import ResearchRuntime
from app.store.sqlite import SQLiteDecisionEventStore, StoreCorruptError


NOW = datetime(2026, 10, 1, tzinfo=UTC)
NODE = LiveResearchNode(node_id="stock", operation="MARKET_DATA", subject="600519", required_fields=("price",))


def response(request=None, value="12.30"):
    request = request or ProviderRequest(request_id="run:stock", operation="MARKET_DATA", subject="600519")
    return ProviderResult(request_id=request.request_id, request_fingerprint=compute_request_fingerprint(request),
        provider="actual-provider", status="SUCCESS", retrieved_at=NOW,
        records=(ProviderRecord(source="upstream-original", record_id="raw-record", lineage_id="actual-lineage",
            fields={"items": [{"股票代码": "600519", "最新价": value}]}),))


@pytest.fixture
def store(tmp_path):
    store = SQLiteDecisionEventStore(tmp_path / "facts.sqlite3")
    try:
        yield store
    finally:
        store.close()


def save(repository, result=None, normalized=None, versions=None):
    result = result or response()
    return repository.save_node(owner_id="alice", run_id="run", node_id="stock", request_payload=NODE.model_dump(mode="json"),
        provider_result=result, normalized=normalized or normalize_live_observations(NODE, result), input_versions=versions)


def test_immutable_versions_hashes_and_owner_isolation(store):
    repository = ResearchFactRepository(store)
    first = save(repository, versions={"questionnaire_snapshot_id": "q1", "portfolio_revision": 2})
    repeated = save(repository, versions={"portfolio_revision": 2, "questionnaire_snapshot_id": "q1"})
    assert first == repeated
    second = save(repository, response(value="12.40"), versions={"questionnaire_snapshot_id": "q1", "portfolio_revision": 2})
    assert second["response_hash"] != first["response_hash"]
    assert second["snapshot_id"] != first["snapshot_id"]
    assert len(repository.list_run("alice", "run")) == 2
    assert not repository.list_run("bob", "run")
    with pytest.raises(ResearchFactNotFound):
        repository.get("bob", first["fact_refs"][0])
    with pytest.raises(ResearchFactNotFound):
        repository.get_snapshot("bob", first["snapshot_id"])
    fact = repository.get("alice", first["fact_refs"][0])
    assert fact["value"] == "12.30" and fact["actual_source"] == "upstream-original"
    assert fact["lineage_id"] == "actual-lineage" and not fact["verified"]
    assert fact["quality_issues"] == ["MISSING_UNIT", "MISSING_OBSERVED_AT"]
    snapshot = repository.get_snapshot("alice", first["snapshot_id"])
    assert snapshot["input_versions"]["portfolio_revision"] == 2
    assert snapshot["missing_fields"] == ["price.observed_at", "price.unit"]


def test_missing_source_no_fact_and_verified_or_synthetic_input_rejected(store):
    repository = ResearchFactRepository(store)
    normalized = normalize_live_observations(NODE, response())
    normalized["observations"][0]["actual_source"] = None
    stored = save(repository, normalized=normalized)
    assert not stored["fact_refs"]
    assert "source" in repository.get_snapshot("alice", stored["snapshot_id"])["missing_fields"]
    normalized["observations"][0]["verification_status"] = "VERIFIED"
    with pytest.raises(ValueError):
        save(repository, normalized=normalized)
    with pytest.raises(ValueError):
        save(repository, response().model_copy(update={"provider": "fixture-provider"}))


def test_corrupted_persisted_observation_is_rejected(store):
    repository = ResearchFactRepository(store)
    saved = save(repository)
    fact_id = saved["fact_refs"][0]
    store._connection.execute("UPDATE research_facts SET fact_json=? WHERE owner_id=? AND fact_id=?",
                              (json.dumps({"verified": True}), "alice", fact_id))
    with pytest.raises(StoreCorruptError):
        repository.get("alice", fact_id)


def test_input_versions_tamper_invalidates_fact_reference(store):
    repository = ResearchFactRepository(store)
    saved = save(repository, versions={"portfolio_revision": 1})
    store._connection.execute("UPDATE research_fact_snapshots SET input_versions_json=? WHERE snapshot_id=?",
                              ('{"portfolio_revision": 99}', saved["snapshot_id"]))
    with pytest.raises(StoreCorruptError):
        repository.get_snapshot("alice", saved["snapshot_id"])
    with pytest.raises(StoreCorruptError):
        repository.get("alice", saved["fact_refs"][0])


def test_service_returns_durable_references_and_captures_input_versions_once(store):
    async def scenario():
        class Registry:
            def scoped_provider(self, provider, owner_id):
                return provider

        class Provider:
            name = "actual-provider"

            async def execute(self, request):
                return response(request)

        calls = []

        def inputs(owner):
            calls.append(owner)
            return {"profile_revision": 3}

        repository = ResearchFactRepository(store)
        runtime = ResearchRuntime()
        service = LiveResearchService(provider=Provider(), registry=Registry(), runtime=runtime,
                                      facts=repository, input_versions=inputs)
        run = service.submit("alice", LiveResearchRequest(nodes=(NODE,)))
        await service._tasks[run["run_id"]]
        final = service.get("alice", run["run_id"])
        assert calls == ["alice"]
        reference = final["nodes"][0]["fact_refs"][0]
        assert not repository.get("alice", reference)["verified"]
        await service.aclose()
        restarted_repository = ResearchFactRepository(store)
        assert restarted_repository.get("alice", reference)["input_versions"]["profile_revision"] == 3
        await runtime.aclose()
    asyncio.run(scenario())


@pytest.mark.parametrize("legacy_raw_columns", [False, True])
def test_existing_twenty_migration_upgrades_without_inventing_old_raw_data(tmp_path, legacy_raw_columns):
    database = tmp_path / "legacy020.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY,applied_at TEXT NOT NULL)")
    connection.executemany("INSERT INTO schema_migrations VALUES (?,?)", [(version, NOW.isoformat()) for version in range(1, 21)])
    migration = Path(__file__).resolve().parents[2] / "app" / "store" / "migrations" / "020_research_facts.sql"
    sql = migration.read_text(encoding="utf-8")
    if legacy_raw_columns:
        sql = sql.replace("response_hash TEXT NOT NULL,", "response_hash TEXT NOT NULL,request_json TEXT NOT NULL,response_json TEXT NOT NULL,")
    connection.executescript(sql)
    columns = "owner_id,snapshot_id,run_id,node_id,request_hash,response_hash,method_version,input_versions_json,provider_status,missing_fields_json,created_at"
    values = ("alice", "legacy", "old-run", "stock", "0" * 64, "1" * 64,
              "live-scalar-normalization.v1", "{}", "SUCCESS", "[]", NOW.isoformat())
    if legacy_raw_columns:
        columns += ",request_json,response_json"
        values += ("{}", "{}")
    connection.execute("INSERT INTO research_fact_snapshots (" + columns + ") VALUES (" + ",".join("?" for _ in values) + ")", values)
    connection.commit()
    connection.close()
    store = SQLiteDecisionEventStore(database)
    try:
        columns = {row["name"] for row in store._connection.execute("PRAGMA table_info(research_fact_payloads)").fetchall()}
        assert {"request_json", "response_json"} <= columns
        repository = ResearchFactRepository(store)
        with pytest.raises(StoreCorruptError, match="integrity"):
            repository.get_snapshot("alice", "legacy")
        current = save(repository)
        snapshot = repository.get_snapshot("alice", current["snapshot_id"])
        assert snapshot["response_hash"] == current["response_hash"]
        assert "request_json" not in snapshot and "response_json" not in snapshot
    finally:
        store.close()


def test_snapshot_tampering_and_authentication_metadata_are_rejected(store):
    repository = ResearchFactRepository(store)
    saved = save(repository)
    store._connection.execute("UPDATE research_fact_payloads SET response_json=? WHERE owner_id=? AND snapshot_id=?",
                              ("{}", "alice", saved["snapshot_id"]))
    with pytest.raises(StoreCorruptError):
        repository.get_snapshot("alice", saved["snapshot_id"])
    unsafe = response().model_copy(update={"records": (ProviderRecord(source="upstream", fields={"authorization": "must-not-be-persisted"}),)})
    with pytest.raises(ValueError, match="authentication"):
        save(repository, result=unsafe)


def test_live_call_keeps_captured_skill_version_across_upgrade(store):
    from app.providers.skillhub import WencaiSkillHubProvider, load_iwencai_skill_manifest
    from app.service.skill_registry import SkillMetadata, SkillRegistry

    async def scenario():
        old_started = asyncio.Event()
        old_release = asyncio.Event()
        actual_versions = []

        class Provider(WencaiSkillHubProvider):
            async def execute(self, request, *, skill=None):
                actual_versions.append(skill["version"])
                if skill["version"] == "1.0.0":
                    old_started.set()
                    await old_release.wait()
                return response(request)

        registry = SkillRegistry(store)
        runtime = ResearchRuntime()
        repository = ResearchFactRepository(store)
        service = LiveResearchService(provider=Provider(api_key="test"), registry=registry, runtime=runtime, facts=repository)
        first = service.submit("alice", LiveResearchRequest(nodes=(NODE,)))
        first_task = service._tasks[first["run_id"]]
        await old_started.wait()
        upgraded = SkillMetadata.model_validate(dict(load_iwencai_skill_manifest()["skills"][3], version="1.1.0"))
        registry.install(upgraded)
        registry.update(upgraded.skill_id, upgraded.version, action="verified", expected_revision=1)
        second = service.submit("alice", LiveResearchRequest(nodes=(NODE,)))
        await service._tasks[second["run_id"]]
        old_release.set()
        await first_task
        old_node = service.get("alice", first["run_id"])["nodes"][0]
        new_node = service.get("alice", second["run_id"])["nodes"][0]
        assert old_node["capability_snapshot"]["version"] == "1.0.0"
        assert new_node["capability_snapshot"]["version"] == "1.1.0"
        old_fact = repository.get("alice", old_node["fact_refs"][0])
        new_fact = repository.get("alice", new_node["fact_refs"][0])
        assert old_fact["input_versions"]["skill_version"] == "1.0.0"
        assert new_fact["input_versions"]["skill_version"] == "1.1.0"
        assert actual_versions == ["1.0.0", "1.1.0"]
        await service.aclose()
        await runtime.aclose()
    asyncio.run(scenario())
