"""Single-process fair, bounded execution of independent research tasks."""
from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass
import time
from typing import Awaitable, Callable


class ResearchCapacityError(RuntimeError):
    pass


class ResearchRuntimeClosed(RuntimeError):
    pass


@dataclass(eq=False)
class _Waiting:
    owner_id: str
    gate: asyncio.Future
    admitted: bool = False


class ResearchRuntime:
    """Queue owner groups round-robin; count activity at actual execution entry."""

    def __init__(self, *, global_limit=100, queue_limit=400, per_owner_limit=200,
                 budget_seconds=60.0, provider_limit=100, model_limit=8):
        if any(type(value) is not int or value < 1 for value in
               (global_limit, queue_limit, per_owner_limit, provider_limit, model_limit)):
            raise ValueError("runtime limits must be positive integers")
        if not 0 < budget_seconds <= 60:
            raise ValueError("research budget must be at most sixty seconds")
        self.global_limit = global_limit
        self.queue_limit = queue_limit
        self.per_owner_limit = per_owner_limit
        self.budget_seconds = budget_seconds
        self.provider_limit = provider_limit
        self.model_limit = model_limit
        self._queues = defaultdict(deque)
        self._owners = deque()
        self._owner_counts = defaultdict(int)
        self._reserved = 0
        self._active = 0
        self._peak = 0
        self._completed = 0
        self._failed = 0
        self._partial = 0
        self._cancelled = 0
        self._timed_out = 0
        self._rejected = 0
        self._queue_wait_ms = 0.0
        self._execution_ms = 0.0
        self._closed = False
        self._tasks = set()
        self._provider = asyncio.Semaphore(provider_limit)
        self._model = asyncio.Semaphore(model_limit)
        self._calls = {"provider_active": 0, "provider_waiting": 0, "provider_peak": 0,
                       "model_active": 0, "model_waiting": 0, "model_peak": 0}

    def _waiting(self):
        return sum(len(queue) for queue in self._queues.values())

    def snapshot(self):
        return {"scope": "SINGLE_PROCESS", "global_limit": self.global_limit,
                "activity_unit": "RESEARCH_RUN", "metrics_semantics": "research-run-outcomes.v2",
                "queue_limit": self.queue_limit, "per_owner_limit": self.per_owner_limit,
                "provider_limit": self.provider_limit, "model_limit": self.model_limit,
                "upstream_quota_verified": False,
                "budget_seconds": self.budget_seconds, "active": self._active,
                "waiting": self._waiting(), "peak_active": self._peak,
                "completed": self._completed, "failed": self._failed, "partial": self._partial,
                "cancelled": self._cancelled, "timed_out": self._timed_out,
                "rejected": self._rejected, "closed": self._closed,
                "queue_wait_ms_total": round(self._queue_wait_ms, 3),
                "execution_ms_total": round(self._execution_ms, 3), **self._calls}

    def _remove_waiter(self, entry):
        queue = self._queues.get(entry.owner_id)
        if queue and entry in queue:
            queue.remove(entry)
            if not queue:
                del self._queues[entry.owner_id]
                self._owners.remove(entry.owner_id)

    def _drain(self):
        while not self._closed and self._reserved < self.global_limit and self._owners:
            owner = self._owners.popleft()
            queue = self._queues[owner]
            entry = queue.popleft()
            if queue:
                self._owners.append(owner)
            else:
                del self._queues[owner]
            if not entry.gate.done():
                entry.admitted = True
                self._reserved += 1
                entry.gate.set_result(None)

    async def run(self, owner_id: str, operation: Callable[[], Awaitable], *, budget_seconds=None):
        if not owner_id:
            raise ValueError("task owner is required")
        if self._closed:
            raise ResearchRuntimeClosed("research runtime is closed")
        budget = self.budget_seconds if budget_seconds is None else min(budget_seconds, self.budget_seconds)
        if budget <= 0:
            raise TimeoutError("research deadline expired")
        if self._owner_counts.get(owner_id, 0) >= self.per_owner_limit or (
            self._reserved >= self.global_limit and self._waiting() >= self.queue_limit
        ):
            self._rejected += 1
            raise ResearchCapacityError("research capacity is exhausted")
        self._owner_counts[owner_id] += 1
        entry = _Waiting(owner_id, asyncio.get_running_loop().create_future())
        if owner_id not in self._queues:
            self._owners.append(owner_id)
        self._queues[owner_id].append(entry)
        task = asyncio.current_task()
        self._tasks.add(task)
        entered = False
        queued_at = time.perf_counter()
        execution_at = None
        self._drain()
        try:
            async with asyncio.timeout(budget):
                await entry.gate
                entered = True
                execution_at = time.perf_counter()
                self._queue_wait_ms += (execution_at - queued_at) * 1000
                self._active += 1
                self._peak = max(self._peak, self._active)
                result = await operation()
                status = result.get("status") if isinstance(result, dict) else None
                if status == "FAILED":
                    self._failed += 1
                elif status == "PARTIAL":
                    self._partial += 1
                elif status == "TIMED_OUT":
                    self._timed_out += 1
                elif status == "CANCELLED":
                    self._cancelled += 1
                else:
                    self._completed += 1
                return result
        except TimeoutError:
            self._timed_out += 1
            raise
        except asyncio.CancelledError:
            self._cancelled += 1
            raise
        except Exception:
            self._failed += 1
            raise
        finally:
            if entered:
                self._active -= 1
                self._execution_ms += (time.perf_counter() - execution_at) * 1000
            else:
                self._queue_wait_ms += (time.perf_counter() - queued_at) * 1000
            if entry.admitted:
                self._reserved -= 1
            else:
                self._remove_waiter(entry)
            self._owner_counts[owner_id] -= 1
            if self._owner_counts[owner_id] == 0:
                del self._owner_counts[owner_id]
            self._tasks.discard(task)
            self._drain()

    @asynccontextmanager
    async def _call_slot(self, kind, semaphore):
        if self._closed:
            raise ResearchRuntimeClosed("research runtime is closed")
        self._calls[f"{kind}_waiting"] += 1
        try:
            await semaphore.acquire()
        finally:
            self._calls[f"{kind}_waiting"] -= 1
        self._calls[f"{kind}_active"] += 1
        self._calls[f"{kind}_peak"] = max(self._calls[f"{kind}_peak"], self._calls[f"{kind}_active"])
        try:
            yield
        finally:
            self._calls[f"{kind}_active"] -= 1
            semaphore.release()

    def provider_slot(self):
        return self._call_slot("provider", self._provider)

    def model_slot(self):
        return self._call_slot("model", self._model)

    async def aclose(self):
        self._closed = True
        for queue in tuple(self._queues.values()):
            for entry in queue:
                if not entry.gate.done():
                    entry.gate.set_exception(ResearchRuntimeClosed("research runtime is closed"))
        tasks = tuple(task for task in self._tasks if task is not asyncio.current_task())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
