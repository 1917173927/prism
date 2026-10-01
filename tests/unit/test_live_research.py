import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.providers.contracts import ProviderRecord, ProviderRequest, ProviderResult
from app.providers.fingerprint import compute_request_fingerprint
from app.providers.resilience import ProviderExecutionPolicy
from app.providers.runtime import execute_with_budget
from app.service.live_research import (LiveResearchNode, LiveResearchRequest, LiveResearchService,
                                       ResearchRunNotFound, ResearchAsOfError, normalize_live_observations,
                                       build_live_research_request, live_research_templates)
from app.service.research_runtime import ResearchRuntime


NOW = datetime(2026, 10, 1, tzinfo=UTC)


def node():
    return LiveResearchNode(node_id="stock", operation="MARKET_DATA", subject="600519", required_fields=("price",))


def result(request_id="test", *, rows=None, units=None, observed_at=None, period=None):
    request = ProviderRequest(request_id=request_id, operation="MARKET_DATA", subject="600519")
    return ProviderResult(request_id=request_id, request_fingerprint=compute_request_fingerprint(request),
                          provider="actual-provider", status="SUCCESS", retrieved_at=NOW,
                          records=(ProviderRecord(source="iwencai", record_id="actual-record",
                            fields={"items": rows if rows is not None else [{"股票代码": "600519", "最新价": "123.50"}]},
                            units=units or {}, observed_at=observed_at, period=period),))


def test_single_source_without_units_or_observation_time_remains_partial():
    normalized = normalize_live_observations(node(), result())
    assert normalized["status"] == "PARTIAL"
    assert normalized["missing_fields"] == ["price.observed_at", "price.unit"]
    observation = normalized["observations"][0]
    assert observation["value"] == "123.50"
    assert observation["actual_source"] == "iwencai"
    assert observation["observed_at"] is observation["unit"] is observation["lineage_id"] is None
    assert observation["verification_status"] == "SINGLE_SOURCE_UNVERIFIED"


def test_wrong_stock_and_missing_numeric_value_cannot_create_zero_observation():
    normalized = normalize_live_observations(node(), result(rows=[{"股票代码": "000001", "最新价": "123"}]))
    assert not normalized["observations"]
    assert normalized["missing_fields"] == ["price", "subject_identity"]
    normalized = normalize_live_observations(node(), result(rows=[{"股票代码": "600519", "最新价": None}]))
    assert not normalized["observations"]
    assert normalized["missing_fields"] == ["price"]


def test_explicit_units_and_times_keep_origin_and_single_source_unverified():
    normalized = normalize_live_observations(node(), result(units={"最新价": "CNY"}, observed_at=NOW))
    assert normalized["status"] == "SUCCESS"
    assert normalized["observations"][0]["observed_at"] == NOW.isoformat()
    assert normalized["observations"][0]["verification_status"] == "SINGLE_SOURCE_UNVERIFIED"


def test_financial_periods_are_not_merged_or_replaced_by_retrieval_time():
    spec = LiveResearchNode(node_id="finance", operation="COMPANY_DATA", subject="600519", required_fields=("revenue",))
    normalized = normalize_live_observations(spec, result(rows=[{"股票代码": "600519",
        "营业收入[20251231]": "100", "营业收入[20241231]": "90"}],
        units={"revenue": "CNY"}, observed_at=NOW))
    assert {item["period"] for item in normalized["observations"]} == {"20251231", "20241231"}


def test_run_status_owner_isolation_cancellation_and_shutdown():
    async def scenario():
        entered = asyncio.Event()
        cleaned = asyncio.Event()

        class Provider:
            name = "actual-provider"

            async def execute(self, request):
                entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cleaned.set()

        class Registry:
            def scoped_provider(self, provider, owner_id):
                return provider

        runtime = ResearchRuntime()
        service = LiveResearchService(provider=Provider(), registry=Registry(), runtime=runtime)
        run = service.submit("alice", LiveResearchRequest(nodes=(node(),)))
        await entered.wait()
        assert service.get("alice", run["run_id"])["status"] == "RUNNING"
        with pytest.raises(ResearchRunNotFound):
            service.get("bob", run["run_id"])
        with pytest.raises(ResearchRunNotFound):
            await service.cancel("bob", run["run_id"])
        cancelled = await service.cancel("alice", run["run_id"])
        assert cancelled["status"] == "CANCELLED"
        assert cleaned.is_set()
        assert runtime.snapshot()["active"] == runtime.snapshot()["provider_active"] == 0
        second = service.submit("alice", LiveResearchRequest(nodes=(node(),)))
        await service.aclose()
        assert service.get("alice", second["run_id"])["status"] == "CANCELLED"
        await runtime.aclose()
    asyncio.run(scenario())


def test_provider_cancellation_propagates_without_fallback():
    async def scenario():
        entered = asyncio.Event()

        class Primary:
            name = "primary"

            async def execute(self, request):
                entered.set()
                await asyncio.Event().wait()

        class Fallback:
            name = "fallback"
            calls = 0

            async def execute(self, request):
                self.calls += 1

        fallback = Fallback()
        request = ProviderRequest(request_id="cancel", operation="MARKET_DATA", subject="600519", timeout_ms=10000)
        task = asyncio.create_task(execute_with_budget(Primary(), request, policy=ProviderExecutionPolicy(fallback=fallback)))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert fallback.calls == 0
    asyncio.run(scenario())


def test_successful_run_and_deadline_preserve_terminal_states():
    async def scenario():
        class Registry:
            def scoped_provider(self, provider, owner_id):
                return provider

        class Provider:
            name = "actual-provider"

            async def execute(self, request):
                response = result(request.request_id, units={"最新价": "CNY"}, observed_at=NOW)
                return response.model_copy(update={"request_fingerprint": compute_request_fingerprint(request)})

        runtime = ResearchRuntime()
        service = LiveResearchService(provider=Provider(), registry=Registry(), runtime=runtime)
        started = service.submit("alice", LiveResearchRequest(nodes=(node(),)))
        await service._tasks[started["run_id"]]
        run = service.get("alice", started["run_id"])
        assert run["status"] == "COMPLETED"
        assert run["verification_status"] == "SINGLE_SOURCE_UNVERIFIED"
        assert run["elapsed_ms"] is not None

        class SlowProvider:
            name = "actual-provider"

            async def execute(self, request):
                await asyncio.Event().wait()

        service.provider = SlowProvider()
        started = service.submit("alice", LiveResearchRequest(nodes=(node(),), budget_seconds=0.01))
        await service._tasks[started["run_id"]]
        assert service.get("alice", started["run_id"])["status"] == "TIMED_OUT"
        assert runtime.snapshot()["active"] == runtime.snapshot()["provider_active"] == 0
        await service.aclose()
        await runtime.aclose()
    asyncio.run(scenario())


def test_dag_cycles_are_rejected_and_dependency_failure_blocks_child():
    first = node()
    child = node().model_copy(update={"node_id": "child", "dependencies": ("stock",)})
    with pytest.raises(ValueError):
        LiveResearchRequest(nodes=(first.model_copy(update={"dependencies": ("child",)}), child))
    with pytest.raises(ValueError):
        LiveResearchRequest(nodes=(first.model_copy(update={"dependencies": ("unknown",)}),))

    async def scenario():
        calls = []

        class Registry:
            def scoped_provider(self, provider, owner_id):
                return provider

        class Provider:
            name = "actual-provider"

            async def execute(self, request):
                calls.append(request.request_id)
                response = result(request.request_id)  # Missing time/unit => PARTIAL.
                return response.model_copy(update={"request_fingerprint": compute_request_fingerprint(request)})

        runtime = ResearchRuntime()
        service = LiveResearchService(provider=Provider(), registry=Registry(), runtime=runtime)
        run = service.submit("alice", LiveResearchRequest(nodes=(child, first)))
        await service._tasks[run["run_id"]]
        final = service.get("alice", run["run_id"])
        assert len(calls) == 1
        assert final["nodes"][0]["status"] == "CANCELLED"
        assert final["nodes"][0]["error_codes"] == ["DEPENDENCY_INCOMPLETE"]
        assert final["status"] == "PARTIAL"
        await service.aclose()
        await runtime.aclose()
    asyncio.run(scenario())


def test_http_reuse_and_injected_client_ownership():
    import httpx
    from app.providers.skillhub import WencaiSkillHubProvider
    from app.providers.fuyao import FuyaoFinanceProvider

    async def scenario():
        for provider in (WencaiSkillHubProvider(), FuyaoFinanceProvider(api_key="test")):
            await provider.start_http()
            shared = provider._shared_client
            await provider.start_http()
            assert provider._shared_client is shared
            await provider.aclose()
            assert shared.is_closed

        auth_values = []

        async def handle(request):
            auth_values.append(request.headers.get("X-api-key"))
            return httpx.Response(200, json={"code": 0, "data": {}})

        client = httpx.AsyncClient(base_url="https://example.test", transport=httpx.MockTransport(handle))
        provider = FuyaoFinanceProvider(api_key="first", client=client)
        await provider.start_http()
        await provider._get(client, "/test", {})
        provider._api_key_override = "second"
        await provider._get(client, "/test", {})
        await provider.aclose()
        assert auth_values == ["first", "second"]
        assert not client.is_closed
        wencai = WencaiSkillHubProvider(client=client)
        await wencai.start_http()
        await wencai.aclose()
        assert not client.is_closed
        await client.aclose()
    asyncio.run(scenario())


def test_runtime_limits_whole_multinode_runs_instead_of_provider_nodes():
    async def scenario():
        ready = asyncio.Event()
        release = asyncio.Event()
        calls = 0

        class Registry:
            def scoped_provider(self, provider, owner_id):
                return provider

        class Provider:
            name = "actual-provider"

            async def execute(self, request):
                nonlocal calls
                calls += 1
                if calls == 2:
                    ready.set()
                await release.wait()
                return result(request.request_id).model_copy(update={"request_fingerprint": compute_request_fingerprint(request)})

        runtime = ResearchRuntime(global_limit=1)
        service = LiveResearchService(provider=Provider(), registry=Registry(), runtime=runtime)
        request = LiveResearchRequest(nodes=(node(), node().model_copy(update={"node_id": "second"})))
        first = service.submit("alice", request)
        first_task = service._tasks[first["run_id"]]
        await ready.wait()
        second = service.submit("bob", request)
        second_task = service._tasks[second["run_id"]]
        await asyncio.sleep(0)
        assert runtime.snapshot()["active"] == 1
        assert runtime.snapshot()["provider_active"] == 2
        assert runtime.snapshot()["waiting"] == 1
        assert service.get("bob", second["run_id"])["status"] == "QUEUED"
        release.set()
        await asyncio.gather(first_task, second_task)
        assert runtime.snapshot()["partial"] == 2
        assert calls == 4
        await service.aclose()
        await runtime.aclose()
    asyncio.run(scenario())


def test_hundred_multinode_runs_have_hundred_research_peak_and_separate_provider_count():
    async def scenario():
        entered = 0
        release = asyncio.Event()

        class Registry:
            def scoped_provider(self, provider, owner_id):
                return provider

        class Provider:
            name = "actual-provider"

            async def execute(self, request):
                nonlocal entered
                entered += 1
                if entered == 200:
                    release.set()
                await release.wait()
                return result(request.request_id).model_copy(update={"request_fingerprint": compute_request_fingerprint(request)})

        runtime = ResearchRuntime(provider_limit=200)
        service = LiveResearchService(provider=Provider(), registry=Registry(), runtime=runtime)
        request = LiveResearchRequest(nodes=(node(), node().model_copy(update={"node_id": "second"})))
        runs = [service.submit("alice", request) for _ in range(100)]
        await asyncio.gather(*(service._tasks[run["run_id"]] for run in runs))
        stats = runtime.snapshot()
        assert stats["peak_active"] == 100
        assert stats["provider_peak"] == 200
        assert stats["partial"] == 100
        assert stats["active"] == stats["provider_active"] == stats["waiting"] == 0
        await service.aclose()
        await runtime.aclose()
    asyncio.run(scenario())


@pytest.mark.parametrize("period", ["20270101", "2027-01-01", "2026-11", "2026-Q4", "2027"])
def test_explicit_future_reporting_period_is_rejected(period):
    spec = LiveResearchNode(node_id="finance", operation="COMPANY_DATA", subject="600519", required_fields=("revenue",))
    output = normalize_live_observations(spec, result(rows=[{"股票代码": "600519", "revenue": "10"}],
        units={"revenue": "CNY"}, observed_at=NOW, period=period), cutoff=NOW)
    assert output["status"] == "FAILED"
    assert not output["observations"]
    assert "FUTURE_REPORTING_PERIOD" in output["error_codes"]


def test_future_observation_and_naive_cutoff_are_rejected():
    output = normalize_live_observations(node(), result(units={"price": "CNY"}, observed_at=NOW + timedelta(seconds=1)), cutoff=NOW)
    assert output["status"] == "FAILED" and not output["observations"]
    assert output["error_codes"] == ["FUTURE_OBSERVATION"]
    with pytest.raises(ValueError):
        LiveResearchRequest(nodes=(node(),), as_of=NOW.replace(tzinfo=None))


def test_historical_as_of_is_forwarded_and_service_future_cutoff_rejected():
    async def scenario():
        class Registry:
            def scoped_provider(self, provider, owner_id):
                return provider

        class Provider:
            name = "actual-provider"
            cutoff = None

            async def execute(self, request):
                self.cutoff = request.as_of
                return result(request.request_id, units={"price": "CNY"}, observed_at=NOW + timedelta(hours=1)).model_copy(
                    update={"request_fingerprint": compute_request_fingerprint(request)})

        runtime = ResearchRuntime()
        provider = Provider()
        service = LiveResearchService(provider=provider, registry=Registry(), runtime=runtime, clock=lambda: NOW + timedelta(days=1))
        with pytest.raises(ResearchAsOfError):
            service.submit("alice", LiveResearchRequest(nodes=(node(),), as_of=NOW + timedelta(days=2)))
        run = service.submit("alice", LiveResearchRequest(nodes=(node(),), as_of=NOW))
        await service._tasks[run["run_id"]]
        final = service.get("alice", run["run_id"])
        assert provider.cutoff == NOW
        assert final["as_of"] == NOW.isoformat()
        assert final["status"] == "FAILED"
        assert final["nodes"][0]["error_codes"] == ["FUTURE_OBSERVATION"]
        await service.aclose()
        await runtime.aclose()
    asyncio.run(scenario())


def test_live_template_contains_only_capability_requirements_and_target():
    catalog = live_research_templates()
    assert catalog[0]["template_id"] == "live-equity-basic.v1"
    assert all("expected_value" not in entry and "lineage_id" not in entry for entry in catalog[0]["nodes"])
    request = build_live_research_request("live-equity-basic.v1", "600519.SH", as_of=NOW)
    assert request.as_of == NOW and len(request.nodes) == 2
    assert all(entry.subject == "600519" for entry in request.nodes)
    with pytest.raises(ValueError):
        build_live_research_request("unavailable", "600519")
    with pytest.raises(ValueError):
        build_live_research_request("live-equity-basic.v1", "510300")
