import asyncio

import pytest

from app.service.research_runtime import ResearchCapacityError, ResearchRuntime


@pytest.mark.parametrize("count", [25, 50, 100])
def test_actual_activity_peak_reaches_capacity_and_waiters_do_not_count(count):
    async def scenario():
        runtime = ResearchRuntime(global_limit=count)
        ready = asyncio.Event()
        release = asyncio.Event()
        entered = 0

        async def work():
            nonlocal entered
            entered += 1
            if entered == count:
                ready.set()
            await release.wait()

        tasks = [asyncio.create_task(runtime.run("alice", work)) for _ in range(count)]
        await ready.wait()
        queued = asyncio.create_task(runtime.run("bob", work))
        await asyncio.sleep(0)
        assert runtime.snapshot()["active"] == count
        assert runtime.snapshot()["waiting"] == 1
        assert runtime.snapshot()["provider_active"] == 0
        release.set()
        await asyncio.gather(*tasks, queued)
        assert runtime.snapshot()["peak_active"] == count
        assert runtime.snapshot()["active"] == runtime.snapshot()["waiting"] == 0
        await runtime.aclose()
    asyncio.run(scenario())


def test_fair_round_robin_admission_and_overcapacity():
    async def scenario():
        runtime = ResearchRuntime(global_limit=1, queue_limit=3, per_owner_limit=3)
        release = asyncio.Event()
        order = []

        async def first():
            await release.wait()

        async def job(name):
            order.append(name)

        first_task = asyncio.create_task(runtime.run("first", first))
        await asyncio.sleep(0)
        tasks = [asyncio.create_task(runtime.run(owner, lambda name=name: job(name)))
                 for owner, name in [("alice", "a1"), ("alice", "a2"), ("bob", "b1")]]
        await asyncio.sleep(0)
        with pytest.raises(ResearchCapacityError):
            await runtime.run("charlie", first)
        release.set()
        await asyncio.gather(first_task, *tasks)
        assert order == ["a1", "b1", "a2"]
        assert runtime.snapshot()["rejected"] == 1
    asyncio.run(scenario())


def test_queue_timeout_execution_cancel_and_provider_slots_release():
    async def scenario():
        runtime = ResearchRuntime(global_limit=1, provider_limit=1)
        entered = asyncio.Event()
        closed = asyncio.Event()

        async def work():
            async with runtime.provider_slot():
                entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    closed.set()

        running = asyncio.create_task(runtime.run("alice", work))
        await entered.wait()
        with pytest.raises(TimeoutError):
            await runtime.run("bob", work, budget_seconds=0.01)
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running
        assert closed.is_set()
        assert runtime.snapshot()["active"] == runtime.snapshot()["waiting"] == 0
        assert runtime.snapshot()["provider_active"] == 0
        async with runtime.provider_slot():
            assert runtime.snapshot()["provider_active"] == 1
        assert runtime.snapshot()["timed_out"] == runtime.snapshot()["cancelled"] == 1
    asyncio.run(scenario())


def test_owner_limit_and_close_cancel_all_pending_and_running_work():
    async def scenario():
        runtime = ResearchRuntime(global_limit=1, per_owner_limit=2)
        release = asyncio.Event()
        tasks = [asyncio.create_task(runtime.run("alice", release.wait)) for _ in range(2)]
        await asyncio.sleep(0)
        with pytest.raises(ResearchCapacityError):
            await runtime.run("alice", release.wait)
        await runtime.aclose()
        assert all(task.done() for task in tasks)
        assert runtime.snapshot()["active"] == runtime.snapshot()["waiting"] == 0
        assert runtime.snapshot()["closed"]
    asyncio.run(scenario())


def test_terminal_business_outcomes_are_not_counted_as_successful_returns():
    async def scenario():
        runtime = ResearchRuntime(provider_limit=12, model_limit=3)

        async def outcome(status):
            return {"status": status}

        for status in ("COMPLETED", "PARTIAL", "FAILED"):
            await runtime.run("alice", lambda status=status: outcome(status))
        stats = runtime.snapshot()
        assert stats["completed"] == stats["partial"] == stats["failed"] == 1
        assert stats["provider_limit"] == 12 and stats["model_limit"] == 3
        assert stats["activity_unit"] == "RESEARCH_RUN"
        assert stats["metrics_semantics"] == "research-run-outcomes.v2"
        assert not stats["upstream_quota_verified"]
        await runtime.aclose()
    asyncio.run(scenario())
