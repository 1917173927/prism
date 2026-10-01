"""Measure 25/50/100 independent jobs through the actual LIVE service pipeline.

Controlled mode proves local scheduling and normalization only. Real mode uses
server-side Wencai configuration; it never reads or prints credential stores.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path
import platform
import time
import tracemalloc

from app.providers.contracts import ProviderRecord, ProviderRequest, ProviderResult
from app.providers.fingerprint import compute_request_fingerprint
from app.providers.runtime import execute_with_budget
from app.service.live_research import LiveResearchNode, LiveResearchRequest, LiveResearchService
from app.service.research_facts import ResearchFactRepository
from app.service.research_runtime import ResearchRuntime
from app.service.skill_registry import SkillRegistry
from app.store.sqlite import SQLiteDecisionEventStore


class ControlledProvider:
    name = "controlled-regression-provider"

    def __init__(self, count, delay_seconds=0.025):
        self.count = count
        self.delay_seconds = delay_seconds
        self.entered = 0
        self.release = asyncio.Event()

    async def execute(self, request):
        self.entered += 1
        if self.entered == self.count:
            self.release.set()
        await self.release.wait()
        await asyncio.sleep(self.delay_seconds)
        observed = datetime.now(UTC)
        return ProviderResult(request_id=request.request_id, request_fingerprint=compute_request_fingerprint(request),
            provider=self.name, status="SUCCESS", retrieved_at=observed,
            records=(ProviderRecord(source="controlled-regression-data", record_id=request.request_id,
                fields={"items": [{"股票代码": "600519", "最新价": "12.30"}]}, units={"price": "CNY"},
                observed_at=observed, lineage_id="controlled-single-origin"),))


def percentile(values, quantile):
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower), 3)


def configured_real_components():
    # Reuse the application's normal protected-store initialization. Do not
    # inspect, serialize or print its credentials or private database records.
    from app.api.main import app
    provider = app.state.live_research_service.provider
    if not provider.is_configured:
        raise ValueError("real mode requires the application's configured Wencai provider")
    return provider, app.state.skill_registry


async def real_smoke(provider, registry):
    await provider.start_http()
    try:
        request = ProviderRequest(request_id="research-load-smoke", operation="MARKET_DATA",
                                  subject="贵州茅台最新价", parameters={"limit": 1}, timeout_ms=8000)
        result = await execute_with_budget(registry.scoped_provider(provider, "benchmark-smoke"), request)
        usable = result.status.value in {"SUCCESS", "PARTIAL"} and any(record.fields.get("items") for record in result.records)
        return {"status": "PASS" if usable else "BLOCKED", "provider_status": result.status.value,
                "error_codes": [issue.code.value for issue in result.issues],
                "record_count": len(result.records), "retrieved_at": result.retrieved_at.isoformat(),
                "is_synthetic": False, "upstream_capacity_proven": False}
    finally:
        await provider.aclose()


async def run_round(count, *, mode="controlled", delay_seconds=0.025, real_components=None):
    store = SQLiteDecisionEventStore(":memory:")
    runtime = ResearchRuntime()
    registry = SkillRegistry(store)
    if mode == "controlled":
        provider = ControlledProvider(count, delay_seconds)
    else:
        provider, registry = real_components or configured_real_components()
    if mode == "real" and not provider.is_configured:
        store.close()
        raise ValueError("real mode requires server-side Wencai configuration")
    facts = ResearchFactRepository(store) if mode == "real" else None
    service = LiveResearchService(provider=provider, registry=registry, runtime=runtime, facts=facts,
                                  evidence_mode="CONTROLLED_REGRESSION" if mode == "controlled" else "LIVE")
    samples = []
    loop_lag_ms = []
    stop = asyncio.Event()
    interval = 0.01

    async def sample():
        loop = asyncio.get_running_loop()
        due = loop.time()
        while not stop.is_set():
            now = loop.time()
            loop_lag_ms.append(max(0, now - due) * 1000)
            snapshot = runtime.snapshot()
            samples.append({"elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                            **{key: snapshot[key] for key in ("active", "waiting", "provider_active", "model_active")}})
            due = now + interval
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
            except TimeoutError:
                pass

    started = time.perf_counter()
    cpu_started = time.process_time()
    sampler = asyncio.create_task(sample())
    tasks = []
    try:
        if mode == "real":
            await provider.start_http()
        node = LiveResearchNode(node_id="quote", operation="MARKET_DATA", subject="600519",
                                query="贵州茅台最新价", required_fields=("price",))
        owners = [f"benchmark-owner-{index % 4}" for index in range(count)]
        submissions = [service.submit(owner, LiveResearchRequest(nodes=(node,))) for owner in owners]
        tasks = [service._tasks[run["run_id"]] for run in submissions]
        await asyncio.gather(*tasks, return_exceptions=True)
        runs = [service.get(owner, submitted["run_id"]) for owner, submitted in zip(owners, submissions)]
        elapsed_ms = (time.perf_counter() - started) * 1000
        cpu_ms = (time.process_time() - cpu_started) * 1000
        latencies = [run["elapsed_ms"] for run in runs if run["elapsed_ms"] is not None]
        states = {}
        errors = {}
        provider_statuses = {}
        for run in runs:
            states[run["status"]] = states.get(run["status"], 0) + 1
            for result in run["nodes"]:
                provider_status = result.get("provider_status", "NOT_CALLED")
                provider_statuses[provider_status] = provider_statuses.get(provider_status, 0) + 1
                for code in result.get("error_codes", []):
                    errors[code] = errors.get(code, 0) + 1
        actual_observations = sum(len(result.get("observations", [])) for run in runs for result in run["nodes"])
        verified_observations = sum(item.get("verification_status") == "VERIFIED" for run in runs for result in run["nodes"]
                                    for item in result.get("observations", []))
        memory_current, memory_peak = tracemalloc.get_traced_memory()
        return {"task_count": count, "pipeline": "LiveResearchService -> ResearchRuntime -> Provider -> normalization",
                "mode": "CONTROLLED_REGRESSION" if mode == "controlled" else "REAL_PROVIDER",
                "is_synthetic": mode == "controlled", "runtime": runtime.snapshot(), "run_states": states,
                "provider_statuses": provider_statuses, "error_codes": errors,
                "completed_rate": states.get("COMPLETED", 0) / count,
                "wall_ms": round(elapsed_ms, 3), "cpu_ms": round(cpu_ms, 3),
                "p50_ms": percentile(latencies, .5), "p95_ms": percentile(latencies, .95), "p99_ms": percentile(latencies, .99),
                "event_loop_lag_p95_ms": percentile(loop_lag_ms, .95),
                "python_allocated_bytes": memory_current, "python_peak_allocated_bytes": memory_peak,
                "memory_scope": "TRACEMALLOC_PYTHON_ALLOCATIONS_NOT_PROCESS_RSS",
                "observations": actual_observations, "verified_observations": verified_observations,
                "fact_storage_exercised": facts is not None,
                "upstream_capacity_proven": False, "upstream_quota_verified": False,
                "controlled_provider_delay_ms": delay_seconds * 1000 if mode == "controlled" else None,
                "samples": samples,
                "runs": [{"run_id": run["run_id"], "status": run["status"], "created_at": run["created_at"],
                          "finished_at": run["finished_at"], "elapsed_ms": run["elapsed_ms"],
                          "nodes": run["nodes"]} for run in runs],
                "evidence_retention": "FULL_NORMALIZED_NODES"}
    finally:
        stop.set()
        await sampler
        await service.aclose()
        await runtime.aclose()
        if mode == "real":
            await provider.aclose()
        store.close()


async def run_load_test(*, mode="controlled", delay_seconds=0.025, repeats=3):
    if type(repeats) is not int or repeats < 1:
        raise ValueError("repeats must be a positive integer")
    started_tracing = not tracemalloc.is_tracing()
    if started_tracing:
        tracemalloc.start()
    try:
        components, smoke, blocker = None, None, None
        if mode == "real":
            try:
                components = configured_real_components()
                smoke = await real_smoke(*components)
                if smoke["status"] != "PASS":
                    blocker = "REAL_PROVIDER_SMOKE_FAILED"
            except Exception:
                blocker = "REAL_PROVIDER_CONFIGURATION_UNAVAILABLE"
        rounds = []
        if blocker is None:
            for count in (25, 50, 100):
                for round_index in range(1, repeats + 1):
                    measured = await run_round(count, mode=mode, delay_seconds=delay_seconds, real_components=components)
                    measured["round_index"] = round_index
                    measured["fact_storage_scope"] = "IN_MEMORY_BENCHMARK_ONLY" if mode == "real" else "NOT_CONFIGURED"
                    rounds.append(measured)
                    if mode == "real" and any(code in measured["error_codes"] for code in ("QUOTA_EXHAUSTED", "AUTH_FAILED", "PERMISSION_DENIED")):
                        blocker = "REAL_PROVIDER_REJECTED_LOAD"
                        break
                if blocker is not None:
                    break
        return {"schema_version": "research-service-load-evidence.v1", "generated_at": datetime.now(UTC).isoformat(),
                "python": platform.python_version(), "platform": platform.platform(), "rounds": rounds,
                "runtime_support": "SUPPORTED" if platform.python_version_tuple()[:2] in {("3", "11"), ("3", "12")} else "SUPPORTED_RUNTIME_NOT_VERIFIED",
                "mode": "CONTROLLED_REGRESSION" if mode == "controlled" else "REAL_PROVIDER",
                "status": "BLOCKED" if blocker else "MEASURED", "blocker": blocker, "smoke": smoke,
                "evidence_retention": "FULL_NORMALIZED_NODES",
                "requested_rounds": [25, 50, 100],
                "requested_repeats_per_size": repeats,
                "executed_repeats_per_size": {str(count): sum(item["task_count"] == count for item in rounds) for count in (25, 50, 100)},
                "all_requested_rounds_executed": len(rounds) == 3 * repeats,
                "acceptance_boundary": "Controlled mode is a local scheduling and normalization regression. Real mode is a finite measured run; neither proves a supplier SLA or sustained upstream capacity.",
                "all_local_peaks_reached": bool(rounds) and all(item["runtime"]["peak_active"] == item["task_count"] for item in rounds),
                "upstream_capacity_proven": False}
    finally:
        if started_tracing:
            tracemalloc.stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("controlled", "real"), default="controlled")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    try:
        report = asyncio.run(run_load_test(mode=args.mode, repeats=args.repeats))
    except ValueError:
        parser.error("real mode requires configured server-side credentials; no secrets were displayed")
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output.resolve()), "all_local_peaks_reached": report["all_local_peaks_reached"],
                      "status": report["status"], "blocker": report["blocker"],
                      "upstream_capacity_proven": False}, ensure_ascii=False))
    if report["status"] == "BLOCKED":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
