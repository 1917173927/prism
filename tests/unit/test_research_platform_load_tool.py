import asyncio

from tools.research_platform_load_test import run_load_test


def test_local_load_evidence_uses_service_and_separates_upstream_claims():
    report = asyncio.run(run_load_test(delay_seconds=0.01))
    assert report["all_local_peaks_reached"]
    assert not report["upstream_capacity_proven"]
    assert [round["task_count"] for round in report["rounds"]] == [25, 25, 25, 50, 50, 50, 100, 100, 100]
    assert report["requested_repeats_per_size"] == 3
    assert report["executed_repeats_per_size"] == {"25": 3, "50": 3, "100": 3}
    assert report["all_requested_rounds_executed"]
    for round in report["rounds"]:
        assert round["mode"] == "CONTROLLED_REGRESSION" and round["is_synthetic"]
        assert round["runtime"]["peak_active"] == round["runtime"]["provider_peak"] == round["task_count"]
        assert round["runtime"]["active"] == round["runtime"]["waiting"] == 0
        assert round["completed_rate"] == 1
        assert round["observations"] == round["task_count"]
        assert round["verified_observations"] == 0
        assert not round["fact_storage_exercised"]
        assert not round["upstream_capacity_proven"] and not round["upstream_quota_verified"]
        assert round["p50_ms"] <= round["p95_ms"] <= round["p99_ms"]
        assert len(round["runs"]) == round["task_count"]
        assert round["evidence_retention"] == "FULL_NORMALIZED_NODES"
        assert round["runs"][0]["nodes"][0]["observations"][0]["actual_source"] == "controlled-regression-data"
        assert round["runs"][0]["nodes"][0]["capability_snapshot"]["skill_id"] == "hithink-market-query"


def test_real_mode_configuration_failure_produces_blocked_evidence(monkeypatch):
    import tools.research_platform_load_test as tool

    def unavailable():
        raise ValueError("unavailable")

    monkeypatch.setattr(tool, "configured_real_components", unavailable)
    report = asyncio.run(tool.run_load_test(mode="real"))
    assert report["status"] == "BLOCKED"
    assert report["blocker"] == "REAL_PROVIDER_CONFIGURATION_UNAVAILABLE"
    assert report["rounds"] == []
    assert not report["all_local_peaks_reached"]
    assert not report["upstream_capacity_proven"]
