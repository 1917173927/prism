import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api.personal_research_routes import create_personal_research_router
from app.providers.contracts import ProviderRecord, ProviderResult
from app.providers.fingerprint import compute_request_fingerprint
from app.service.personal_research import (DataAgent, PersonalIndicator, PersonalResearchDefinition,
    PersonalResearchFactRun, PersonalResearchInvalid, PersonalResearchNotFound, PersonalResearchRun,
    PersonalResearchSave, PersonalResearchService, calculate_personal_indicators, profitability_template)
from app.service.research_facts import ResearchFactRepository
from app.service.research_runtime import ResearchRuntime
from app.service.skill_registry import SkillRegistry, SkillUnavailable
from app.store.sqlite import SQLiteDecisionEventStore, StoreConflictError


NOW = datetime(2026, 10, 6, tzinfo=UTC)


@pytest.fixture
def store(tmp_path):
    store = SQLiteDecisionEventStore(tmp_path / "personal-research.sqlite3")
    # Production schema is integrated by the parent agent's shared migration.
    store._connection.execute("CREATE TABLE IF NOT EXISTS personal_research_versions (owner_id TEXT NOT NULL,system_id TEXT NOT NULL,revision INTEGER NOT NULL,definition_json TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(owner_id,system_id,revision))")
    store._connection.execute("CREATE TABLE IF NOT EXISTS personal_research_runs (owner_id TEXT NOT NULL,run_id TEXT NOT NULL,system_id TEXT NOT NULL,system_revision INTEGER NOT NULL,request_json TEXT NOT NULL,result_json TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(owner_id,run_id))")
    try:
        yield store
    finally:
        store.close()


def observation(metric, value, **extra):
    return {"metric": metric, "value": str(value), "subject": "600519", "unit": "万元", "period": "2025-Q4",
            "observed_at": "2026-04-01T08:00:00+08:00", "actual_source": "annual-report", "evidence_id": "e:" + metric,
            "provider_serving_mode": "DIRECT", **extra}


def inputs(*observations):
    return [{"agent_id": "finance", "operation": "COMPANY_DATA", "status": "SUCCESS", "observations": list(observations)}]


def calculate(data, *, definition=None, period="2025-Q4"):
    return calculate_personal_indicators(definition or profitability_template(), data, subject="600519", period=period, as_of=NOW)


def test_personal_indicator_is_computed_and_observer_uses_its_result():
    indicators, observers = calculate(inputs(observation("revenue", 100), observation("net_profit", 20)))
    margin = indicators[0]
    assert margin["status"] == "CALCULATED"
    assert Decimal(margin["value"]) == Decimal("20")
    assert margin["unit"] == "%" and margin["period"] == "2025-12-31"
    assert margin["evidence_refs"] == ["e:net_profit", "e:revenue"]
    assert margin["verification_status"] == "DERIVED_FROM_SINGLE_SOURCE_UNVERIFIED"
    assert observers[0]["matched"] is True and "15%" in observers[0]["message"]
    # Currency scaling is deterministic rather than comparing 万元 to 元.
    margin, _ = calculate(inputs(observation("revenue", 100), observation("net_profit", 200000, unit="CNY")))
    assert Decimal(margin[0]["value"]) == Decimal("20")


@pytest.mark.parametrize("override,reason", [
    ({"value": "0"}, "ZERO_DENOMINATOR"), ({"unit": None}, "MISSING_UNIT"),
    ({"unit": "%"}, "NON_MONETARY_UNIT"), ({"subject": "000001"}, "SUBJECT_MISMATCH"),
    ({"period": "2024-Q4"}, "PERIOD_MISMATCH"), ({"period": None}, "MISSING_PERIOD"),
    ({"observed_at": None}, "MISSING_OBSERVATION_TIME"),
    ({"observed_at": (NOW + timedelta(days=1)).isoformat()}, "FUTURE_OBSERVATION"),
    ({"provider_serving_mode": "CACHE_STALE_FALLBACK"}, "STALE_SOURCE"),
])
def test_invalid_inputs_never_create_an_indicator_or_observation(override, reason):
    data = inputs({**observation("revenue", 100), **override}, observation("net_profit", 20))
    indicators, observers = calculate(data, period=None)
    assert indicators[0]["status"] == "UNAVAILABLE" and indicators[0]["reason"] == reason
    assert indicators[0]["value"] is None
    assert observers[0]["matched"] is None and observers[0]["status"] == "UNAVAILABLE"


def test_multiple_periods_require_explicit_choice_and_conflicts_are_blocked():
    data = inputs(observation("revenue", 100), observation("revenue", 90, period="2024-Q4"), observation("net_profit", 20))
    result, _ = calculate(data, period=None)
    assert result[0]["reason"] == "AMBIGUOUS_PERIOD"
    result, _ = calculate(data)
    assert result[0]["status"] == "CALCULATED"
    data = inputs(observation("revenue", 100), observation("revenue", 101, evidence_id="conflict"), observation("net_profit", 20))
    result, _ = calculate(data)
    assert result[0]["reason"] == "AMBIGUOUS_INPUT"


def test_indicator_graph_handles_derived_inputs_and_independent_operator_benchmarks():
    definition = PersonalResearchDefinition(name="个人利润体系", data_agents=profitability_template().data_agents,
        indicators=(PersonalIndicator(indicator_id="difference", name="利润差值", operator="difference", inputs=("finance.revenue", "finance.net_profit")),
                    PersonalIndicator(indicator_id="combined", name="自定义综合规模", operator="weighted_mean", inputs=("difference", "finance.net_profit"), weights=(Decimal("3"), Decimal("1"))),
                    PersonalIndicator(indicator_id="ratio", name="规模比率", operator="ratio_pct", inputs=("combined", "finance.revenue"))))
    result, _ = calculate(inputs(observation("revenue", 100, unit="CNY"), observation("net_profit", 20, unit="CNY")), definition=definition)
    # Hand-calculated independent benchmark: 100-20=80; (80*3+20)/4=65; 65/100*100=65%.
    assert [Decimal(item["value"]) for item in result] == [Decimal("80"), Decimal("65"), Decimal("65")]
    assert [item["unit"] for item in result] == ["CNY", "CNY", "%"]


def test_cycles_unknown_fields_and_executable_payloads_are_rejected():
    payload = profitability_template().model_dump(mode="json")
    payload["indicators"][0]["inputs"] = ["margin", "finance.revenue"]
    with pytest.raises(ValueError):
        PersonalResearchDefinition.model_validate(payload)
    payload = profitability_template().model_dump(mode="json")
    payload["data_agents"][0]["endpoint"] = "http://127.0.0.1/private"
    with pytest.raises(ValueError):
        PersonalResearchDefinition.model_validate(payload)
    with pytest.raises(ValueError):
        PersonalIndicator(indicator_id="unsafe", name="错误指标", operator="eval", inputs=("finance.revenue", "finance.net_profit"))
    with pytest.raises(ValueError):
        PersonalIndicator(indicator_id="unsafe", name="错误指标", operator="weighted_mean", inputs=("finance.revenue", "finance.net_profit"), weights=(Decimal("0"), Decimal("0")))


class FinanceProvider:
    name = "actual-provider"
    calls = 0

    async def execute(self, request, **kwargs):
        self.calls += 1
        return ProviderResult(request_id=request.request_id, request_fingerprint=compute_request_fingerprint(request),
            provider=self.name, status="SUCCESS", retrieved_at=NOW,
            records=(ProviderRecord(source="issuer-report", record_id="annual-2025", lineage_id="issuer-2025", period="2025-Q4",
                observed_at=datetime(2026, 4, 1, tzinfo=UTC), units={"revenue": "CNY", "net_profit": "CNY"},
                fields={"items": [{"股票代码": "600519", "营业收入": 100, "净利润": 20}]}),))


def service(store, *, provider=None, facts=None):
    return PersonalResearchService(store=store, provider=provider or FinanceProvider(), registry=SkillRegistry(store, clock=lambda: NOW),
        runtime=ResearchRuntime(), clock=lambda: NOW, facts=facts)


def test_versioned_private_systems_persist_and_cas_changes_are_immutable(store):
    research = service(store)
    first = research.save("alice", "profitability", PersonalResearchSave(definition=profitability_template(), expected_revision=0))
    assert first["revision"] == 1 and first["personal_skill_id"] == "personal:profitability"
    second_definition = profitability_template().model_copy(update={"name": "我的长期研究"})
    second = research.save("alice", "profitability", PersonalResearchSave(definition=second_definition, expected_revision=1))
    assert second["revision"] == 2
    assert research.get("alice", "profitability", 1)["name"] != second["name"]
    assert research.list("bob") == []
    with pytest.raises(PersonalResearchNotFound):
        research.get("bob", "profitability")
    with pytest.raises(StoreConflictError):
        research.save("alice", "profitability", PersonalResearchSave(definition=second_definition, expected_revision=1))
    assert service(store).get("alice", "profitability")["revision"] == 2


def test_saved_system_runs_exact_skill_version_and_persists_live_facts(store):
    async def scenario():
        facts = ResearchFactRepository(store, clock=lambda: NOW)
        provider = FinanceProvider()
        research = service(store, provider=provider, facts=facts)
        research.save("alice", "profitability", PersonalResearchSave(definition=profitability_template(), expected_revision=0))
        submitted = research.submit("alice", "profitability", PersonalResearchRun(expected_revision=1, subject="600519", period="2025-Q4"))
        await research._tasks[submitted["run_id"]]
        run = research.get_run("alice", submitted["run_id"])
        assert run["status"] == "COMPLETED", run
        assert run["system_revision"] == 1 and run["definition_snapshot"]["name"] == "盈利质量观察"
        assert run["data_agents"][0]["capability_snapshot"]["skill_id"] == "hithink-finance-query"
        assert run["data_agents"][0]["capability_snapshot"]["version"] == "1.0.0"
        assert run["data_agents"][0]["fact_refs"]
        assert Decimal(run["indicators"][0]["value"]) == 20
        assert provider.calls == 1
        assert research.runtime.snapshot()["active"] == research.runtime.snapshot()["provider_active"] == 0
        with pytest.raises(PersonalResearchNotFound):
            research.get_run("bob", run["run_id"])
        facts_for_run = facts.list_run("alice", run["run_id"])
        replay = await research.from_facts("alice", "profitability", PersonalResearchFactRun(expected_revision=1, subject="600519", period="2025-Q4", fact_ids={"finance": tuple(item["fact_id"] for item in facts_for_run)}))
        assert replay["status"] == "COMPLETED" and replay["data_mode"] == "STORED_FACTS"
        assert provider.calls == 1
        assert replay["indicators"][0]["value"] == run["indicators"][0]["value"]
        assert replay["indicators"][0]["evidence_refs"] == sorted(item["fact_id"] for item in facts_for_run)
        assert research.runtime.snapshot()["completed"] == 2
        await research.aclose()
        await research.runtime.aclose()
    asyncio.run(scenario())


def test_disabled_skill_and_old_revision_block_new_execution(store):
    async def scenario():
        provider = FinanceProvider()
        research = service(store, provider=provider)
        research.save("alice", "profitability", PersonalResearchSave(definition=profitability_template(), expected_revision=0))
        research.registry.select("alice", "hithink-finance-query", enabled=False, expected_revision=0)
        with pytest.raises(SkillUnavailable):
            research.submit("alice", "profitability", PersonalResearchRun(expected_revision=1, subject="600519"))
        research.registry.select("alice", "hithink-finance-query", enabled=True, expected_revision=1)
        research.registry.update("hithink-finance-query", "1.0.0", action="disable", expected_revision=1)
        with pytest.raises(SkillUnavailable):
            research.submit("alice", "profitability", PersonalResearchRun(expected_revision=1, subject="600519"))
        assert provider.calls == 0
        await research.aclose()
        await research.runtime.aclose()
    asyncio.run(scenario())


def test_queued_and_active_cancellation_release_all_runtime_resources(store):
    async def scenario():
        entered = asyncio.Event()
        cleaned = asyncio.Event()

        class SlowProvider(FinanceProvider):
            async def execute(self, request, **kwargs):
                entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cleaned.set()

        research = service(store, provider=SlowProvider())
        research.runtime = ResearchRuntime(global_limit=1)
        research.save("alice", "profitability", PersonalResearchSave(definition=profitability_template(), expected_revision=0))
        request = PersonalResearchRun(expected_revision=1, subject="600519")
        active = research.submit("alice", "profitability", request)
        await entered.wait()
        queued = research.submit("alice", "profitability", request)
        await asyncio.sleep(0)
        assert research.runtime.snapshot()["waiting"] == 1
        assert (await research.cancel("alice", queued["run_id"]))["status"] == "CANCELLED"
        assert research.runtime.snapshot()["waiting"] == 0
        assert (await research.cancel("alice", active["run_id"]))["status"] == "CANCELLED"
        assert cleaned.is_set()
        assert research.runtime.snapshot()["active"] == research.runtime.snapshot()["provider_active"] == 0
        await research.aclose()
        await research.runtime.aclose()
    asyncio.run(scenario())


def test_routes_get_owner_from_authentication_and_reject_owner_in_body(store):
    research = service(store)
    app = FastAPI()
    app.include_router(create_personal_research_router(service=research, owner_dependency=lambda: "alice"))
    body = {"definition": profitability_template().model_dump(mode="json"), "expected_revision": 0}
    with TestClient(app) as client:
        assert client.put("/api/v1/personal-research/systems/profitability", json={**body, "owner_id": "bob"}).status_code == 422
        response = client.put("/api/v1/personal-research/systems/profitability", json=body)
        assert response.status_code == 200, response.text
        assert client.put("/api/v1/personal-research/systems/profitability", json=body).status_code == 409
        items = client.get("/api/v1/personal-research/systems").json()["items"]
        assert items[0]["system_id"] == "profitability"
        assert client.get("/api/v1/personal-research/systems/unknown").status_code == 404
        catalog = client.get("/api/v1/personal-research/catalog").json()
        assert [role["role"] for role in catalog["agent_roles"]] == ["DATA", "INDICATOR", "OBSERVER"]
        assert any(skill["fields"] == ["revenue", "net_profit", "pe"] for skill in catalog["skills"])


def test_current_quote_uses_fetch_cutoff_and_explicit_history_never_advances(store):
    async def scenario():
        current = [NOW]
        requests = []

        class FreshProvider(FinanceProvider):
            async def execute(self, request, **kwargs):
                requests.append(request)
                current[0] = NOW + timedelta(milliseconds=20)
                result = await super().execute(request)
                record = result.records[0].model_copy(update={"observed_at": current[0]})
                return result.model_copy(update={"records": (record,), "retrieved_at": current[0]})

        research = service(store, provider=FreshProvider())
        research.clock = lambda: current[0]
        research.save("alice", "profitability", PersonalResearchSave(definition=profitability_template(), expected_revision=0))
        run = await research.run_and_wait("alice", "profitability", PersonalResearchRun(expected_revision=1, subject="600519"))
        assert run["status"] == "COMPLETED"
        assert requests[0].as_of is None
        assert run["as_of"] is None and run["effective_as_of"] == current[0].isoformat()
        historical = await research.run_and_wait("alice", "profitability", PersonalResearchRun(expected_revision=1, subject="600519", as_of=NOW))
        assert historical["status"] == "PARTIAL" and historical["indicators"][0]["status"] == "UNAVAILABLE"
        assert requests[1].as_of == NOW and historical["effective_as_of"] == NOW.isoformat()
        assert "FUTURE_OBSERVATION" in historical["data_agents"][0]["error_codes"]
        await research.aclose()
        await research.runtime.aclose()
    asyncio.run(scenario())


def test_running_system_keeps_definition_and_capability_snapshots(store):
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        class HeldProvider(FinanceProvider):
            async def execute(self, request, **kwargs):
                entered.set()
                await release.wait()
                return await super().execute(request)

        research = service(store, provider=HeldProvider())
        research.save("alice", "profitability", PersonalResearchSave(definition=profitability_template(), expected_revision=0))
        submitted = research.submit("alice", "profitability", PersonalResearchRun(expected_revision=1, subject="600519"))
        await entered.wait()
        revised = profitability_template().model_copy(update={"name": "新的研究系统", "observers": ()})
        research.save("alice", "profitability", PersonalResearchSave(definition=revised, expected_revision=1))
        research.registry.update("hithink-finance-query", "1.0.0", action="disable", expected_revision=1)
        with pytest.raises(StoreConflictError):
            research.submit("alice", "profitability", PersonalResearchRun(expected_revision=1, subject="600519"))
        with pytest.raises(SkillUnavailable):
            research.submit("alice", "profitability", PersonalResearchRun(expected_revision=2, subject="600519"))
        release.set()
        await research._tasks[submitted["run_id"]]
        run = research.get_run("alice", submitted["run_id"])
        assert run["status"] == "COMPLETED" and run["system_revision"] == 1
        assert run["name"] == "盈利质量观察" and run["observers"][0]["matched"] is True
        assert run["data_agents"][0]["capability_snapshot"]["version"] == "1.0.0"
        await research.aclose()
        await research.runtime.aclose()
    asyncio.run(scenario())


def test_budget_includes_queue_wait_and_copilot_cancellation_propagates(store):
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        provider = FinanceProvider()
        research = service(store, provider=provider)
        research.runtime = ResearchRuntime(global_limit=1)
        research.save("alice", "profitability", PersonalResearchSave(definition=profitability_template(), expected_revision=0))

        async def hold_slot():
            entered.set()
            await release.wait()
            return {"status": "COMPLETED"}

        held = asyncio.create_task(research.runtime.run("other", hold_slot))
        await entered.wait()
        timed_out = await research.run_and_wait("alice", "profitability", PersonalResearchRun(expected_revision=1, subject="600519", budget_seconds=0.01))
        assert timed_out["status"] == "TIMED_OUT" and provider.calls == 0
        parent = asyncio.create_task(research.run_and_wait("alice", "profitability", PersonalResearchRun(expected_revision=1, subject="600519")))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        parent.cancel()
        with pytest.raises(asyncio.CancelledError):
            await parent
        assert research.runtime.snapshot()["waiting"] == 0 and provider.calls == 0
        release.set()
        await held
        assert research.runtime.snapshot()["active"] == 0
        await research.aclose()
        await research.runtime.aclose()
    asyncio.run(scenario())


def test_replayed_facts_still_obey_current_capability_and_recorded_version(store):
    async def scenario():
        facts = ResearchFactRepository(store, clock=lambda: NOW)
        research = service(store, facts=facts)
        research.save("alice", "profitability", PersonalResearchSave(definition=profitability_template(), expected_revision=0))
        run = await research.run_and_wait("alice", "profitability", PersonalResearchRun(expected_revision=1, subject="600519"))
        ids = tuple(item["fact_id"] for item in facts.list_run("alice", run["run_id"]))
        body = PersonalResearchFactRun(expected_revision=1, subject="600519", fact_ids={"finance": ids})
        research.registry.select("alice", "hithink-finance-query", enabled=False, expected_revision=0)
        with pytest.raises(SkillUnavailable):
            await research.from_facts("alice", "profitability", body)
        research.registry.select("alice", "hithink-finance-query", enabled=True, expected_revision=1)

        class WrongVersionRepository:
            def get(self, owner, fact_id):
                fact = facts.get(owner, fact_id)
                return {**fact, "input_versions": {**fact["input_versions"], "skill_version": "9.0.0"}}

        research.facts = WrongVersionRepository()
        with pytest.raises(PersonalResearchInvalid):
            await research.from_facts("alice", "profitability", body)
        await research.aclose()
        await research.runtime.aclose()
    asyncio.run(scenario())


def test_restart_retains_inputs_but_marks_unfinished_jobs_interrupted(store):
    research = service(store)
    record = research.save("alice", "profitability", PersonalResearchSave(definition=profitability_template(), expected_revision=0))
    request = PersonalResearchRun(expected_revision=1, subject="600519")
    run = research._new_run("alice", record, request, "LIVE")
    restarted = service(store)
    persisted = restarted.get_run("alice", run["run_id"])
    assert persisted["status"] == "FAILED" and persisted["error_code"] == "RESEARCH_INTERRUPTED"
    assert persisted["definition_sha256"] == run["definition_sha256"]
    assert persisted["definition_snapshot"] == record["definition"]


@pytest.mark.parametrize("period", ["2025-13", "2025-02-30", "20250230", "0000", "0000-Q4"])
def test_invalid_reporting_dates_return_safe_validation_error(store, period):
    research = service(store)
    app = FastAPI()
    app.include_router(create_personal_research_router(service=research, owner_dependency=lambda: "alice"))
    with TestClient(app) as client:
        client.put("/api/v1/personal-research/systems/profitability", json={"definition": profitability_template().model_dump(mode="json"), "expected_revision": 0})
        response = client.post("/api/v1/personal-research/systems/profitability/runs", json={"expected_revision": 1, "subject": "600519", "period": period})
        assert response.status_code == 422 and response.json()["detail"] == "PERSONAL_RESEARCH_INVALID"


@pytest.mark.parametrize("period", ["unknown-quarter", "0000", "0000-Q4", "20251331"])
def test_bad_provider_reporting_period_is_unavailable_with_clear_reason(period):
    result, _ = calculate(inputs(observation("revenue", 100, period=period), observation("net_profit", 20)), period=None)
    assert result[0]["status"] == "UNAVAILABLE" and result[0]["reason"] == "INVALID_PERIOD"
    assert "报告期" in result[0]["reason_message"]


def field_definition(field, *, second=None):
    fields = (field, second) if second else (field,)
    return PersonalResearchDefinition(name="单位口径研究", data_agents=(DataAgent(agent_id="data", name="资料助手",
        skill_id="hithink-market-query", version="1.0.0", fields=fields),),
        indicators=(PersonalIndicator(indicator_id="ratio", name="自定义比率", operator="ratio_pct",
                                      inputs=("data." + field, "data." + (second or field))),))


@pytest.mark.parametrize("field,unit", [
    ("price", "unknown-unit"), ("price", "亿元"), ("price", "万元"), ("price", "%"), ("price", "倍"),
    ("pe", "unknown-unit"), ("pe", "元"), ("pe", "%"),
    ("nav", "unknown-unit"), ("nav", "亿元"), ("nav", "元/股"), ("nav", "倍"),
    ("revenue", "unknown-unit"), ("net_profit", "unknown-unit"),
])
def test_field_unit_whitelists_reject_unknown_or_wrong_dimensions(field, unit):
    result, _ = calculate_personal_indicators(field_definition(field),
        [{"agent_id": "data", "operation": "MARKET_DATA", "observations": [observation(field, 100, unit=unit, period=None)]}],
        subject="600519", as_of=NOW)
    assert result[0]["status"] == "UNAVAILABLE" and result[0]["value"] is None
    assert result[0]["reason"] in {"UNSUPPORTED_UNIT", "NON_MONETARY_UNIT"}
    assert "单位" in result[0]["reason_message"]


@pytest.mark.parametrize("field,unit", [
    ("price", "CNY"), ("price", "元"), ("price", "元/股"),
    ("pe", "倍"), ("pe", "倍数"), ("pe", "ratio"),
    ("nav", "CNY"), ("nav", "元"), ("nav", "元/份"), ("nav", "元每份"),
    ("revenue", "CNY"), ("revenue", "万元"), ("net_profit", "亿元"),
])
def test_recognized_field_unit_aliases_are_explicitly_normalized(field, unit):
    result, _ = calculate_personal_indicators(field_definition(field),
        [{"agent_id": "data", "operation": "MARKET_DATA", "observations": [observation(field, 100, unit=unit, period=None)]}],
        subject="600519", as_of=NOW)
    assert result[0]["status"] == "CALCULATED" and Decimal(result[0]["value"]) == 100
    expected_unit = {"price": "元/股", "pe": "倍", "nav": "元/份", "revenue": "CNY", "net_profit": "CNY"}[field]
    assert result[0]["input_values"][0]["unit"] == expected_unit


def test_price_pe_ratio_and_price_nav_mix_cannot_share_the_same_dimension():
    for second, unit in (("pe", "倍"), ("nav", "元/份")):
        result, _ = calculate_personal_indicators(field_definition("price", second=second),
            [{"agent_id": "data", "operation": "MARKET_DATA", "observations": [observation("price", 200, unit="CNY", period=None), observation(second, 20, unit=unit, period=None)]}],
            subject="600519", as_of=NOW)
        assert result[0]["status"] == "UNAVAILABLE" and result[0]["reason"] == "UNIT_MISMATCH"


class RecordedFacts:
    calls = 0

    def get(self, owner_id, fact_id):
        self.calls += 1
        metric = "revenue" if fact_id == "revenue" else "net_profit"
        return observation(metric, 100 if metric == "revenue" else 20, fact_id=metric,
            input_versions={"skill_id": "hithink-finance-query", "skill_version": "1.0.0"})


def replay_request(*, budget=60):
    return PersonalResearchFactRun(expected_revision=1, subject="600519", budget_seconds=budget,
                                  fact_ids={"finance": ("revenue", "net_profit")})


def test_stored_fact_research_rejects_expired_budget_without_bypassing_runtime(store):
    async def scenario():
        facts = RecordedFacts()
        research = service(store, facts=facts)
        research.save("alice", "profitability", PersonalResearchSave(definition=profitability_template(), expected_revision=0))
        result = await research.from_facts("alice", "profitability", replay_request(budget=0.000001))
        assert result["status"] == "TIMED_OUT" and facts.calls == 0
        metrics = research.runtime.snapshot()
        assert metrics["timed_out"] == 1 and metrics["completed"] == metrics["active"] == metrics["waiting"] == 0
        assert not research._tasks
        await research.aclose()
        await research.runtime.aclose()
    asyncio.run(scenario())


@pytest.mark.parametrize("slow_stage", ["database", "calculation"])
def test_stored_fact_budget_checks_blocking_reads_and_arithmetic(store, slow_stage):
    async def scenario():
        facts = RecordedFacts()
        research = service(store, facts=facts)
        research.save("alice", "profitability", PersonalResearchSave(definition=profitability_template(), expected_revision=0))
        if slow_stage == "database":
            original = facts.get

            def delayed_get(owner_id, fact_id):
                time.sleep(0.15)
                return original(owner_id, fact_id)

            facts.get = delayed_get
        else:
            original = research._calculate

            def delayed_calculate(run, definition):
                time.sleep(0.15)
                return original(run, definition)

            research._calculate = delayed_calculate
        result = await research.from_facts("alice", "profitability", replay_request(budget=0.1))
        assert result["status"] == "TIMED_OUT" and result["elapsed_ms"] >= 100
        assert research.runtime.snapshot()["timed_out"] == 1
        assert research.runtime.snapshot()["active"] == research.runtime.snapshot()["waiting"] == 0
        await research.aclose()
        await research.runtime.aclose()
    asyncio.run(scenario())


def test_fact_replay_queue_cancellation_obeys_global_capacity_and_shutdown(store):
    async def scenario():
        facts = RecordedFacts()
        research = service(store, facts=facts)
        research.runtime = ResearchRuntime(global_limit=1)
        research.save("alice", "profitability", PersonalResearchSave(definition=profitability_template(), expected_revision=0))
        entered, release = asyncio.Event(), asyncio.Event()

        async def hold_slot():
            entered.set()
            await release.wait()
            return {"status": "COMPLETED"}

        held = asyncio.create_task(research.runtime.run("other", hold_slot))
        await entered.wait()
        replay = asyncio.create_task(research.from_facts("alice", "profitability", replay_request()))
        await asyncio.sleep(0)
        assert research.runtime.snapshot()["waiting"] == 1 and facts.calls == 0
        run_id = next(iter(research._tasks))
        cancelled = await research.cancel("alice", run_id)
        assert cancelled["status"] == "CANCELLED" and replay.cancelled()
        assert research.runtime.snapshot()["waiting"] == 0 and facts.calls == 0
        assert research.runtime.snapshot()["cancelled"] == 1
        second = asyncio.create_task(research.from_facts("alice", "profitability", replay_request()))
        await asyncio.sleep(0)
        second_id = next(iter(research._tasks))
        await research.aclose()
        assert second.cancelled() and research.get_run("alice", second_id)["status"] == "CANCELLED"
        assert research.runtime.snapshot()["waiting"] == 0 and facts.calls == 0
        release.set()
        await held
        assert research.runtime.snapshot()["active"] == 0
        await research.runtime.aclose()
    asyncio.run(scenario())


def test_stored_fact_budget_contains_queue_time_and_rechecks_disabled_skill(store):
    async def scenario():
        facts = RecordedFacts()
        research = service(store, facts=facts)
        research.runtime = ResearchRuntime(global_limit=1)
        research.save("alice", "profitability", PersonalResearchSave(definition=profitability_template(), expected_revision=0))
        entered, release = asyncio.Event(), asyncio.Event()

        async def hold_slot():
            entered.set()
            await release.wait()
            return {"status": "COMPLETED"}

        held = asyncio.create_task(research.runtime.run("other", hold_slot))
        await entered.wait()
        result = await research.from_facts("alice", "profitability", replay_request(budget=0.01))
        assert result["status"] == "TIMED_OUT" and facts.calls == 0
        queued = asyncio.create_task(research.from_facts("alice", "profitability", replay_request()))
        await asyncio.sleep(0)
        research.registry.select("alice", "hithink-finance-query", enabled=False, expected_revision=0)
        release.set()
        await held
        with pytest.raises(SkillUnavailable):
            await queued
        assert facts.calls == 0 and research.runtime.snapshot()["active"] == research.runtime.snapshot()["waiting"] == 0
        await research.aclose()
        await research.runtime.aclose()
    asyncio.run(scenario())
