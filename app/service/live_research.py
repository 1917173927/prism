"""Owner-isolated LIVE research jobs and conservative scalar observations."""
from __future__ import annotations

import asyncio
from calendar import monthrange
from copy import deepcopy
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import re
import time
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.providers.contracts import ProviderOperation, ProviderRequest, ProviderResult
from app.providers.runtime import execute_with_budget
from app.service.research_runtime import ResearchCapacityError


class ResearchRunNotFound(ValueError):
    pass


class ResearchAsOfError(ValueError):
    pass


class LiveResearchNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
    operation: ProviderOperation
    subject: str = Field(min_length=1, max_length=160)
    query: str | None = Field(default=None, min_length=1, max_length=500)
    required_fields: tuple[str, ...] = Field(min_length=1, max_length=16)
    dependencies: tuple[str, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def validate_fields(self):
        if self.operation in {ProviderOperation.SEARCH_NEWS, ProviderOperation.SEARCH_REPORTS}:
            raise ValueError("scalar research requires a structured data operation")
        if len(set(self.required_fields)) != len(self.required_fields):
            raise ValueError("research fields must be unique")
        if len(set(self.dependencies)) != len(self.dependencies):
            raise ValueError("research dependencies must be unique")
        for value in (self.subject, self.query or "", *self.required_fields):
            if any(term in value.lower() for term in ("api_key", "password", "authorization", "secret", "token")):
                raise ValueError("research inputs must not include credentials")
        if any(not field.strip() or len(field) > 160 for field in self.required_fields):
            raise ValueError("research field names are invalid")
        return self


class LiveResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nodes: tuple[LiveResearchNode, ...] = Field(min_length=1, max_length=32)
    budget_seconds: float = Field(default=60, gt=0, le=60)
    as_of: datetime | None = None

    @model_validator(mode="after")
    def unique_nodes(self):
        if self.as_of is not None and (self.as_of.tzinfo is None or self.as_of.utcoffset() is None):
            raise ValueError("research as_of must include a timezone")
        ids = {node.node_id for node in self.nodes}
        if len(ids) != len(self.nodes):
            raise ValueError("research node IDs must be unique")
        resolved = set()
        for node in self.nodes:
            if not set(node.dependencies) <= ids or node.node_id in node.dependencies:
                raise ValueError("research dependencies must reference other catalog nodes")
        while len(resolved) < len(ids):
            ready = {node.node_id for node in self.nodes if set(node.dependencies) <= resolved} - resolved
            if not ready:
                raise ValueError("research dependencies must not contain a cycle")
            resolved.update(ready)
        return self


def live_research_templates():
    return [{"template_id": "live-equity-basic.v1", "name": "A股基础研究",
             "data_mode": "LIVE", "nodes": [
                 {"node_id": "quote", "operation": "MARKET_DATA", "required_fields": ["price"], "target": "SUBJECT"},
                 {"node_id": "financials", "operation": "COMPANY_DATA", "required_fields": ["revenue", "net_profit"], "target": "SUBJECT"}]}]


def build_live_research_request(template_id, subject, *, budget_seconds=60, as_of=None):
    if template_id != "live-equity-basic.v1":
        raise ValueError("LIVE research template is unavailable")
    from app.providers.fuyao import FuyaoFinanceProvider, FuyaoProviderError
    try:
        target = FuyaoFinanceProvider._normalize_thscode(subject, FuyaoFinanceProvider.A_SHARE_PREFIXES).split(".")[0]
    except FuyaoProviderError:
        raise ValueError("LIVE equity template requires a valid A-share stock code") from None
    return LiveResearchRequest(as_of=as_of, budget_seconds=budget_seconds, nodes=(
        LiveResearchNode(node_id="quote", operation="MARKET_DATA", subject=target,
                         query=target + "最新价", required_fields=("price",)),
        LiveResearchNode(node_id="financials", operation="COMPANY_DATA", subject=target,
                         query=target + "营业收入 净利润", required_fields=("revenue", "net_profit"))))


_ALIASES = {"price": ("price", "最新价", "现价"), "revenue": ("revenue", "营业收入"),
            "net_profit": ("net_profit", "净利润"), "pe": ("pe", "市盈率"),
            "nav": ("nav", "单位净值"), "value": ("value",)}
_SYMBOL_FIELDS = ("symbol", "code", "股票代码", "证券代码", "thscode")
_OBSERVATION_FIELDS = ("observed_at", "最新价时间", "行情时间", "更新时间", "数据时间")


def _explicit_observation_time(row):
    for field in _OBSERVATION_FIELDS:
        if row.get(field) not in (None, ""):
            try:
                parsed = datetime.fromisoformat(str(row[field]).replace("Z", "+00:00"))
                return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None
            except ValueError:
                return None
    return None


def _safe_text(value):
    if value is None:
        return None
    text = str(value)
    if len(text) > 200 or any(word in text.lower() for word in
                             ("api_key", "password", "authorization", "secret", "token", "bearer")):
        return None
    return text


def _symbol(value):
    text = str(value).strip().upper()
    match = re.fullmatch(r"(?:(?:SH|SZ|BJ))?(\d{6})(?:\.(?:SH|SZ|BJ))?", text)
    return match.group(1) if match else None


def _number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = Decimal(str(value).replace(",", ""))
        return result if result.is_finite() else None
    except (ValueError, InvalidOperation):
        return None


def _period_end(period):
    if period is None:
        return None
    value = str(period).strip().upper()
    try:
        if re.fullmatch(r"\d{8}", value):
            return datetime.strptime(value, "%Y%m%d").date()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return date.fromisoformat(value)
        match = re.fullmatch(r"(\d{4})(?:-?Q([1-4])|-(\d{2}))?", value)
        if match:
            year = int(match.group(1))
            month = int(match.group(2)) * 3 if match.group(2) else int(match.group(3)) if match.group(3) else 12
            return date(year, month, monthrange(year, month)[1])
    except (ValueError, IndexError):
        return None
    return None


def normalize_live_observations(node: LiveResearchNode, result: ProviderResult, *, cutoff=None):
    """Do not infer units, observation times, source independence or zeroes."""
    observations = []
    missing = set(result.missing_fields)
    expected_symbol = _symbol(node.subject)
    matched_subject = expected_symbol is None
    present = set()
    cutoff = cutoff or datetime.now(UTC)
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("observation cutoff must include a timezone")
    temporal_errors = set()
    for record in result.records:
        columns = record.fields.get("columns")
        column_metadata = {column["key"]: column for column in columns
                           if isinstance(column, dict) and isinstance(column.get("key"), str)} if isinstance(columns, (list, tuple)) else {}
        items = record.fields.get("items")
        rows = items if isinstance(items, (list, tuple)) else (record.fields,)
        for row in rows:
            if not isinstance(row, dict):
                continue
            if expected_symbol is not None:
                actual = next((_symbol(row[field]) for field in _SYMBOL_FIELDS if row.get(field) is not None), None)
                if actual != expected_symbol:
                    continue
                matched_subject = True
            for metric in node.required_fields:
                aliases = _ALIASES.get(metric, (metric,))
                keys = [key for key in row if any(key == alias or key.startswith(alias + "[") for alias in aliases)]
                # Different periods are separate observations; never select
                # a later period silently by provider row order.
                for key in sorted(keys):
                    value = _number(row[key])
                    if value is None:
                        continue
                    unit = _safe_text(record.units.get(key) or record.units.get(metric))
                    row_units = row.get("units")
                    if unit is None and isinstance(row_units, dict):
                        unit = _safe_text(row_units.get(key) or row_units.get(metric))
                    metadata = column_metadata.get(key, {})
                    if unit is None:
                        unit = _safe_text(metadata.get("unit"))
                    period = _safe_text(record.period)
                    key_period = re.search(r"\[(\d{8})\]", key)
                    if period is None and key_period:
                        period = key_period.group(1)
                    if period is None:
                        period = _safe_text(metadata.get("period") or row.get("period") or row.get("report_period") or row.get("报告期"))
                    observed_at = record.observed_at or _explicit_observation_time(row)
                    source = _safe_text(record.source)
                    if source is None:
                        missing.add("source")
                        continue
                    if observed_at is not None and observed_at > cutoff:
                        temporal_errors.add("FUTURE_OBSERVATION")
                        missing.add(metric + ".eligible_observation")
                        continue
                    period_end = _period_end(period)
                    if period_end is not None and period_end > cutoff.date():
                        temporal_errors.add("FUTURE_REPORTING_PERIOD")
                        missing.add(metric + ".eligible_period")
                        continue
                    if node.operation == ProviderOperation.COMPANY_DATA and period is not None and period_end is None:
                        missing.add(metric + ".period_unrecognized")
                    present.add(metric)
                    if unit is None:
                        missing.add(metric + ".unit")
                    if observed_at is None:
                        missing.add(metric + ".observed_at")
                    if node.operation == ProviderOperation.COMPANY_DATA and period is None:
                        missing.add(metric + ".period")
                    identity = "\x1f".join((result.request_id, node.node_id, source,
                                             record.record_id or "", key, str(value), period or ""))
                    observations.append({
                        "evidence_id": "live:" + sha256(identity.encode()).hexdigest(),
                        "subject": node.subject, "metric": metric, "value": str(value),
                        "raw_field": key, "unit": unit, "period": period, "actual_source": source,
                        "record_id": _safe_text(record.record_id), "lineage_id": _safe_text(record.lineage_id),
                        "observed_at": observed_at.isoformat() if observed_at else None,
                        "retrieved_at": result.retrieved_at.isoformat(),
                        "provider_serving_mode": result.serving_mode.value,
                        "cache_age_ms": result.cache_age_ms,
                        "verification_status": "SINGLE_SOURCE_UNVERIFIED",
                    })
    missing.update(set(node.required_fields) - present)
    if not matched_subject:
        missing.add("subject_identity")
    unique = {item["evidence_id"]: item for item in observations}
    status = result.status.value
    if status in {"SUCCESS", "PARTIAL"} and missing:
        status = "PARTIAL"
    if temporal_errors:
        status = "FAILED"
    return {"node_id": node.node_id, "status": status,
            "observations": list(unique.values()), "missing_fields": sorted(missing),
            "provider": _safe_text(result.provider), "provider_status": result.status.value,
            "provider_serving_mode": result.serving_mode.value, "cache_age_ms": result.cache_age_ms,
            "error_codes": [issue.code.value for issue in result.issues] + sorted(temporal_errors),
            "verification_status": "SINGLE_SOURCE_UNVERIFIED" if observations else "NO_VERIFIABLE_OBSERVATION"}


class LiveResearchService:
    """Retains bounded job states in one service process; no durable job claims."""

    def __init__(self, *, provider, registry, runtime, clock=None, max_runs=500,
                 facts=None, input_versions=None, evidence_mode="LIVE"):
        if max_runs < 1:
            raise ValueError("run retention must be positive")
        self.provider = provider
        self.registry = registry
        self.runtime = runtime
        self.clock = clock or (lambda: datetime.now(UTC))
        self.max_runs = max_runs
        if evidence_mode not in {"LIVE", "CONTROLLED_REGRESSION"}:
            raise ValueError("unsupported research evidence mode")
        if facts is not None and evidence_mode != "LIVE":
            raise ValueError("controlled regression cannot write into the LIVE fact repository")
        self.facts = facts
        self.input_versions = input_versions
        self.evidence_mode = evidence_mode
        self._runs = {}
        self._tasks = {}
        self._closed = False

    def submit(self, owner_id: str, request: LiveResearchRequest):
        if request.as_of is not None and request.as_of > self.clock():
            raise ResearchAsOfError("research cutoff must not be in the future")
        if self._closed:
            raise ResearchCapacityError("research service is closed")
        while len(self._runs) >= self.max_runs:
            terminal = next((run_id for run_id in self._runs if run_id not in self._tasks), None)
            if terminal is None:
                raise ResearchCapacityError("research run retention is exhausted")
            del self._runs[terminal]
        run_id = uuid4().hex
        self._runs[run_id] = {"run_id": run_id, "owner_id": owner_id, "status": "QUEUED",
                              "data_mode": self.evidence_mode, "is_synthetic": self.evidence_mode != "LIVE", "storage_scope": "SINGLE_PROCESS",
                              "created_at": self.clock().isoformat(), "finished_at": None,
                              "nodes": [{"node_id": node.node_id, "status": "QUEUED"} for node in request.nodes],
                              "verification_status": "NOT_VERIFIED", "elapsed_ms": None}
        self._runs[run_id]["as_of"] = request.as_of.isoformat() if request.as_of else None
        task = asyncio.create_task(self._execute(run_id, request))
        self._tasks[run_id] = task
        # The callback also covers cancellation before the coroutine starts.
        task.add_done_callback(lambda finished, run_id=run_id: self._finished(run_id, finished))
        return self.get(owner_id, run_id)

    def _finished(self, run_id, task):
        self._tasks.pop(run_id, None)
        run = self._runs.get(run_id)
        if run is not None and run["status"] in {"QUEUED", "RUNNING"}:
            run["status"] = "CANCELLED" if task.cancelled() else "FAILED"
            run["finished_at"] = self.clock().isoformat()
            for node in run["nodes"]:
                if node["status"] in {"QUEUED", "RUNNING"}:
                    node["status"] = run["status"]
        if not task.cancelled():
            task.exception()  # Retrieve failures without exposing diagnostics.

    async def _execute(self, run_id, request):
        run = self._runs[run_id]
        began = time.perf_counter()
        try:
            await self.runtime.run(run["owner_id"], lambda: self._execute_workflow(run_id, request, began),
                                   budget_seconds=request.budget_seconds)
        except ResearchCapacityError:
            run["status"] = "FAILED"
            for node in run["nodes"]:
                node.update(status="FAILED", error_codes=["RESEARCH_CAPACITY"])
        except TimeoutError:
            run["status"] = "TIMED_OUT"
            for node in run["nodes"]:
                if node["status"] in {"QUEUED", "RUNNING", "CANCELLED"}:
                    node["status"] = "TIMED_OUT"
        except asyncio.CancelledError:
            run["status"] = "CANCELLED"
            for node in run["nodes"]:
                if node["status"] in {"QUEUED", "RUNNING"}:
                    node["status"] = "CANCELLED"
            raise
        finally:
            run["finished_at"] = self.clock().isoformat()
            run["elapsed_ms"] = round((time.perf_counter() - began) * 1000, 3)

    async def _execute_workflow(self, run_id, request, began):
        run = self._runs[run_id]
        run["status"] = "RUNNING"
        owner_id = run["owner_id"]
        input_versions = dict(self.input_versions(owner_id) if self.input_versions else {})
        run["input_versions"] = input_versions
        scoped = self.registry.scoped_provider(self.provider, owner_id)
        events = {node.node_id: asyncio.Event() for node in request.nodes}
        indexes = {node.node_id: index for index, node in enumerate(request.nodes)}

        async def node_job(node, index):
            async def execute():
                run["status"] = "RUNNING"
                run["nodes"][index]["status"] = "RUNNING"
                provider_started = time.perf_counter()
                remaining = max(1, int((request.budget_seconds - (time.perf_counter() - began)) * 1000))
                query = ProviderRequest(request_id=f"{run_id}:{node.node_id}", operation=node.operation,
                                        subject=node.query or node.subject, timeout_ms=remaining, as_of=request.as_of)
                async with self.runtime.provider_slot():
                    result = await execute_with_budget(scoped, query)
                now = self.clock()
                cutoff = min(now, request.as_of) if request.as_of is not None else now
                normalized = normalize_live_observations(node, result, cutoff=cutoff)
                capability = getattr(scoped, "captured_skill", None)
                normalized["capability_snapshot"] = deepcopy(capability)
                node_versions = dict(input_versions)
                if capability is not None:
                    for field in ("skill_id", "version", "package_sha256"):
                        if capability.get(field) is not None:
                            node_versions["skill_" + field if field != "skill_id" else field] = capability[field]
                normalized["provider_ms"] = round((time.perf_counter() - provider_started) * 1000, 3)
                if self.facts is not None:
                    store_started = time.perf_counter()
                    references = self.facts.save_node(owner_id=owner_id, run_id=run_id, node_id=node.node_id,
                        request_payload={"provider_request": query.model_dump(mode="json"), "research_node": node.model_dump(mode="json"),
                                         "capability_snapshot": capability},
                        provider_result=result, normalized=normalized, input_versions=node_versions)
                    normalized.update(references)
                    normalized["fact_storage_ms"] = round((time.perf_counter() - store_started) * 1000, 3)
                else:
                    normalized["fact_storage_status"] = "NOT_CONFIGURED"
                run["nodes"][index] = normalized
                return normalized
            try:
                for dependency in node.dependencies:
                    await events[dependency].wait()
                if any(run["nodes"][indexes[dependency]]["status"] != "SUCCESS" for dependency in node.dependencies):
                    run["nodes"][index] = {"node_id": node.node_id, "status": "CANCELLED", "error_codes": ["DEPENDENCY_INCOMPLETE"]}
                    return run["nodes"][index]
                return await execute()
            finally:
                events[node.node_id].set()

        tasks = [asyncio.create_task(node_job(node, index)) for index, node in enumerate(request.nodes)]
        try:
            await asyncio.gather(*tasks)
            statuses = {node["status"] for node in run["nodes"]}
            run["status"] = "FAILED" if "FAILED" in statuses else "COMPLETED" if statuses == {"SUCCESS"} else "PARTIAL"
            run["verification_status"] = "SINGLE_SOURCE_UNVERIFIED"
        except TimeoutError:
            run["status"] = "TIMED_OUT"
            for node in run["nodes"]:
                if node["status"] in {"QUEUED", "RUNNING"}:
                    node["status"] = "TIMED_OUT"
        except asyncio.CancelledError:
            run["status"] = "CANCELLED"
            for node in run["nodes"]:
                if node["status"] in {"QUEUED", "RUNNING"}:
                    node["status"] = "CANCELLED"
            raise
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            run["finished_at"] = self.clock().isoformat()
            run["elapsed_ms"] = round((time.perf_counter() - began) * 1000, 3)
        return run

    def get(self, owner_id, run_id):
        run = self._runs.get(run_id)
        if run is None or run["owner_id"] != owner_id:
            raise ResearchRunNotFound("research run is unavailable")
        return deepcopy(run)

    async def cancel(self, owner_id, run_id):
        self.get(owner_id, run_id)
        task = self._tasks.get(run_id)
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            self._finished(run_id, task)
        return self.get(owner_id, run_id)

    async def aclose(self):
        self._closed = True
        tasks = tuple(self._tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
