"""Private, versioned research skills composed from reviewed data adapters.

Agents have bounded duties: acquire normalized facts, calculate a declared
indicator graph, and explain threshold observations. No generated code runs.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal, DecimalException, localcontext
from hashlib import sha256
import json
import re
import time
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.providers.contracts import ProviderOperation, ProviderRequest
from app.providers.runtime import execute_with_budget
from app.service.live_research import LiveResearchNode, normalize_live_observations
from app.service.research_runtime import ResearchCapacityError, ResearchRuntimeClosed
from app.service.skill_registry import SkillUnavailable
from app.store.sqlite import StoreConflictError


class PersonalResearchNotFound(ValueError):
    pass


class PersonalResearchInvalid(ValueError):
    pass


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


_ID = r"^[a-z][a-z0-9_-]{0,39}$"
SYSTEM_ID = r"^[a-z0-9][a-z0-9-]{0,79}$"
_FIELDS = {"MARKET_DATA": ("price", "pe"), "COMPANY_DATA": ("revenue", "net_profit", "pe"),
           "FUND_DATA": ("nav",)}
_QUERIES = {"price": "最新价", "pe": "市盈率", "revenue": "营业收入", "net_profit": "净利润", "nav": "单位净值"}
_ROLES = [{"role": "DATA", "name": "数据助手", "responsibility": "调用已启用的数据工具，保留标的、单位、时点和来源。"},
          {"role": "INDICATOR", "name": "指标助手", "responsibility": "按保存的公式计算个人指标，缺少条件时停止计算。"},
          {"role": "OBSERVER", "name": "观察助手", "responsibility": "检查自定义观察条件，形成可复用的研究结论。"}]
_REASONS = {
    "INPUT_UNAVAILABLE": "指标需要的输入尚未取得。", "AMBIGUOUS_PERIOD": "存在多个报告期，请明确选择研究报告期。",
    "MISSING_UNIT": "输入缺少明确单位。", "UNIT_MISMATCH": "输入单位不一致，不能直接计算。",
    "SUBJECT_MISMATCH": "输入不属于同一标的。", "PERIOD_MISMATCH": "输入报告期不一致。",
    "MISSING_PERIOD": "财务输入缺少明确报告期。", "MISSING_OBSERVATION_TIME": "输入缺少资料公开或观测时间。",
    "FUTURE_OBSERVATION": "输入晚于本次研究截止时间。", "STALE_SOURCE": "输入来自过期缓存。",
    "FUTURE_REPORTING_PERIOD": "输入报告期晚于本次研究截止时间。",
    "NON_MONETARY_UNIT": "营业收入与净利润必须使用明确的货币单位。",
    "UNSUPPORTED_UNIT": "输入单位不符合该字段的已支持口径，暂不能计算。",
    "INVALID_PERIOD": "输入报告期格式无效，需明确有效的财务报告期。",
    "ZERO_DENOMINATOR": "分母为零，无法计算比率。", "NUMERIC_RANGE": "数值超出可计算范围。",
    "AMBIGUOUS_INPUT": "同一指标存在不一致的输入，需先核实来源。", "SKILL_UNAVAILABLE": "指定版本的数据工具已停用或不可用。",
}


class DataAgent(_Model):
    agent_id: str = Field(pattern=_ID)
    name: str = Field(min_length=1, max_length=80)
    skill_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,99}$")
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    fields: tuple[str, ...] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def field_names(self):
        if len(set(self.fields)) != len(self.fields) or any(field not in _QUERIES for field in self.fields):
            raise ValueError("data fields must be unique reviewed scalar fields")
        return self


class PersonalIndicator(_Model):
    indicator_id: str = Field(pattern=_ID)
    name: str = Field(min_length=1, max_length=80)
    operator: Literal["ratio_pct", "difference", "weighted_mean"]
    inputs: tuple[str, ...] = Field(min_length=2, max_length=8)
    weights: tuple[Decimal, ...] | None = Field(default=None, max_length=8)

    @model_validator(mode="after")
    def operands(self):
        if self.operator != "weighted_mean" and (len(self.inputs) != 2 or self.weights is not None):
            raise ValueError("ratio and difference require exactly two inputs and no weights")
        if self.operator == "weighted_mean":
            if self.weights is None or len(self.weights) != len(self.inputs) or any(w < 0 for w in self.weights) or sum(self.weights) <= 0:
                raise ValueError("weighted mean requires nonnegative matching weights with positive sum")
        if any(not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}(?:\.[a-z][a-z0-9_]{0,39})?", item) for item in self.inputs):
            raise ValueError("indicator inputs must reference data fields or indicators")
        return self


class ObservationAgent(_Model):
    agent_id: str = Field(pattern=_ID)
    name: str = Field(min_length=1, max_length=80)
    indicator_id: str = Field(pattern=_ID)
    comparison: Literal["gte", "lte"]
    threshold: Decimal
    matched_message: str = Field(default="达到当前观察条件。", min_length=1, max_length=300)
    unmatched_message: str = Field(default="尚未达到当前观察条件。", min_length=1, max_length=300)


class PersonalResearchDefinition(_Model):
    schema_version: Literal["personal-research-definition.v1"] = "personal-research-definition.v1"
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    data_agents: tuple[DataAgent, ...] = Field(min_length=1, max_length=16)
    indicators: tuple[PersonalIndicator, ...] = Field(min_length=1, max_length=16)
    observers: tuple[ObservationAgent, ...] = Field(default=(), max_length=16)

    @model_validator(mode="after")
    def graph(self):
        names = [a.agent_id for a in self.data_agents] + [i.indicator_id for i in self.indicators] + [a.agent_id for a in self.observers]
        if len(names) > 32 or len(set(names)) != len(names):
            raise ValueError("a research system requires at most 32 uniquely named nodes")
        available = {f"{agent.agent_id}.{field}" for agent in self.data_agents for field in agent.fields}
        remaining = list(self.indicators)
        while remaining:
            ready = [item for item in remaining if set(item.inputs) <= available]
            if not ready:
                raise ValueError("indicator inputs contain an unknown reference or a cycle")
            for item in ready:
                available.add(item.indicator_id)
                remaining.remove(item)
        if any(agent.indicator_id not in {i.indicator_id for i in self.indicators} for agent in self.observers):
            raise ValueError("observation agents must reference a defined indicator")
        return self


class PersonalResearchSave(_Model):
    definition: PersonalResearchDefinition
    expected_revision: int = Field(ge=0)


class PersonalResearchRun(_Model):
    expected_revision: int = Field(ge=1)
    subject: str = Field(pattern=r"^\d{6}(?:\.(?:SH|SZ|BJ))?$", max_length=9)
    period: str | None = Field(default=None, pattern=r"^(?:\d{4}(?:-Q[1-4]|-\d{2}(?:-\d{2})?)?|\d{8})$")
    as_of: datetime | None = None
    budget_seconds: float = Field(default=60, gt=0, le=60)

    @model_validator(mode="after")
    def timezone(self):
        if self.as_of is not None and (self.as_of.tzinfo is None or self.as_of.utcoffset() is None):
            raise ValueError("research cutoff requires a timezone")
        return self


class PersonalResearchFactRun(PersonalResearchRun):
    fact_ids: dict[str, tuple[str, ...]] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def count(self):
        if sum(len(items) for items in self.fact_ids.values()) > 128 or any(not items for items in self.fact_ids.values()):
            raise ValueError("stored fact inputs require 1 to 128 references")
        return self


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _period(value):
    if value is None:
        return None
    text = str(value)
    if re.fullmatch(r"\d{8}", text):
        text = text[:4] + "-" + text[4:6] + "-" + text[6:]
    if re.fullmatch(r"\d{4}-Q[1-4]", text):
        text = text[:4] + "-" + {"1": "03-31", "2": "06-30", "3": "09-30", "4": "12-31"}[text[-1]]
    if re.fullmatch(r"\d{4}", text):
        text += "-12-31"
    if re.fullmatch(r"\d{4}-\d{2}", text):
        from calendar import monthrange
        try:
            year, month = map(int, text.split("-"))
            text = f"{text}-{monthrange(year, month)[1]:02d}"
        except ValueError:
            raise PersonalResearchInvalid("invalid reporting period") from None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        from datetime import date
        try:
            date.fromisoformat(text)
        except ValueError:
            raise PersonalResearchInvalid("invalid reporting period") from None
        return text
    raise PersonalResearchInvalid("unsupported reporting period")


def _unit(field, unit):
    """A field's meaning and explicit unit jointly determine its dimension.

    Raw units are never passed through. Monetary totals, security prices,
    per-unit fund NAVs and valuation multiples remain distinct dimensions.
    """
    if not isinstance(unit, str):
        return None
    unit = unit.strip()
    if field in {"revenue", "net_profit"}:
        currencies = {"CNY": 1, "元": 1, "人民币元": 1, "万元": 10000, "亿元": 100000000}
        return ("CNY", Decimal(currencies[unit])) if unit in currencies else None
    if field == "price" and unit in {"CNY", "元", "人民币元", "元/股", "元每股", "CNY/share"}:
        return "元/股", Decimal(1)
    if field == "nav" and unit in {"CNY", "元", "人民币元", "元/份", "元每份", "人民币元/份", "CNY/unit"}:
        return "元/份", Decimal(1)
    if field == "pe" and unit in {"倍", "倍数", "ratio"}:
        return "倍", Decimal(1)
    return None


def _unavailable(indicator, reason, **extra):
    return {"indicator_id": indicator.indicator_id, "name": indicator.name, "operator": indicator.operator,
            "inputs": list(indicator.inputs), "status": "UNAVAILABLE", "value": None, "unit": None,
            "reason": reason, "reason_message": _REASONS[reason], "method_version": "personal-indicator.v1", **extra}


def calculate_personal_indicators(definition, data_agents, *, subject, period=None, as_of):
    """Evaluate references with explicit units, one subject and one financial period."""
    values = {}
    failures = {}
    requested_period = _period(period)
    for agent in definition.data_agents:
        data = next((item for item in data_agents if item["agent_id"] == agent.agent_id), {})
        financial = data.get("operation") == "COMPANY_DATA"
        for field in agent.fields:
            ref = f"{agent.agent_id}.{field}"
            candidates = [item for item in data.get("observations", []) if item.get("metric") == field]
            try:
                for item in candidates:
                    _period(item.get("period"))
            except PersonalResearchInvalid:
                failures[ref] = "INVALID_PERIOD"
                continue
            if requested_period is not None and financial:
                candidates = [item for item in candidates if _period(item.get("period")) == requested_period]
            if not candidates:
                failures[ref] = "SKILL_UNAVAILABLE" if "PERMISSION_DENIED" in data.get("error_codes", ()) else "INPUT_UNAVAILABLE"
                continue
            periods = {_period(item.get("period")) for item in candidates}
            if len(periods) > 1:
                failures[ref] = "AMBIGUOUS_PERIOD"
                continue
            canonical = []
            reason = None
            for item in candidates:
                if item.get("subject", "").split(".")[0] != subject.split(".")[0]:
                    reason = "SUBJECT_MISMATCH"
                elif not item.get("unit"):
                    reason = "MISSING_UNIT"
                elif not item.get("observed_at"):
                    reason = "MISSING_OBSERVATION_TIME"
                elif (observed_at := datetime.fromisoformat(item["observed_at"])).tzinfo is None or observed_at.utcoffset() is None:
                    reason = "MISSING_OBSERVATION_TIME"
                elif observed_at > as_of:
                    reason = "FUTURE_OBSERVATION"
                elif item.get("provider_serving_mode") == "CACHE_STALE_FALLBACK":
                    reason = "STALE_SOURCE"
                elif financial and item.get("period") is None:
                    reason = "MISSING_PERIOD"
                elif item.get("period") is not None and _period(item["period"]) > as_of.date().isoformat():
                    reason = "FUTURE_REPORTING_PERIOD"
                elif _unit(field, item["unit"]) is None:
                    reason = "NON_MONETARY_UNIT" if field in {"revenue", "net_profit"} else "UNSUPPORTED_UNIT"
                if reason:
                    break
                unit, multiplier = _unit(field, item["unit"])
                canonical.append({"value": Decimal(item["value"]) * multiplier, "unit": unit,
                                  "subject": subject, "period": _period(item.get("period")),
                                  "observed_at": item["observed_at"], "evidence_refs": [item.get("fact_id") or item["evidence_id"]],
                                  "source": item.get("actual_source"), "raw_unit": item["unit"]})
            if reason:
                failures[ref] = reason
            elif len({(item["value"], item["unit"], item["period"]) for item in canonical}) > 1:
                failures[ref] = "AMBIGUOUS_INPUT"
            else:
                values[ref] = {**canonical[0], "evidence_refs": sorted({ref for item in canonical for ref in item["evidence_refs"]})}
    remaining = list(definition.indicators)
    results = {}
    while remaining:
        ready = [item for item in remaining if all(ref in values or ref in failures for ref in item.inputs)]
        for indicator in ready:
            remaining.remove(indicator)
            reason = next((failures[ref] for ref in indicator.inputs if ref in failures), None)
            inputs = [values[ref] for ref in indicator.inputs if ref in values]
            if reason is None and len({item["unit"] for item in inputs}) != 1:
                reason = "UNIT_MISMATCH"
            if reason is None and len({item["subject"] for item in inputs}) != 1:
                reason = "SUBJECT_MISMATCH"
            if reason is None and len({item["period"] for item in inputs}) != 1:
                reason = "PERIOD_MISMATCH"
            if reason is None and indicator.operator == "ratio_pct" and inputs[1]["value"] == 0:
                reason = "ZERO_DENOMINATOR"
            if reason is None:
                try:
                    with localcontext() as context:
                        context.prec = 40
                        numbers = [item["value"] for item in inputs]
                        if indicator.operator == "ratio_pct":
                            value, unit = numbers[0] / numbers[1] * 100, "%"
                        elif indicator.operator == "difference":
                            value, unit = numbers[0] - numbers[1], inputs[0]["unit"]
                        else:
                            value = sum(v * w for v, w in zip(numbers, indicator.weights)) / sum(indicator.weights)
                            unit = inputs[0]["unit"]
                        if not value.is_finite() or abs(value) > Decimal("1e50"):
                            raise ArithmeticError("numeric range")
                        value = value.quantize(Decimal("0.0000000001"))
                except (DecimalException, ArithmeticError):
                    reason = "NUMERIC_RANGE"
            if reason is not None:
                failures[indicator.indicator_id] = reason
                results[indicator.indicator_id] = _unavailable(indicator, reason)
                continue
            evidence = sorted({ref for item in inputs for ref in item["evidence_refs"]})
            values[indicator.indicator_id] = {"value": value, "unit": unit, "subject": subject,
                "period": inputs[0]["period"], "observed_at": max(item["observed_at"] for item in inputs), "evidence_refs": evidence}
            results[indicator.indicator_id] = {"indicator_id": indicator.indicator_id, "name": indicator.name,
                "operator": indicator.operator, "inputs": list(indicator.inputs), "weights": [str(w) for w in indicator.weights] if indicator.weights else None,
                "status": "CALCULATED", "value": str(value), "unit": unit, "subject": subject, "period": inputs[0]["period"],
                "evidence_refs": evidence, "input_values": [{"ref": ref, "value": str(item["value"]), "unit": item["unit"], "period": item["period"]} for ref, item in zip(indicator.inputs, inputs)],
                "reason": None, "method_version": "personal-indicator.v1", "verification_status": "DERIVED_FROM_SINGLE_SOURCE_UNVERIFIED"}
    indicators = [results[item.indicator_id] for item in definition.indicators]
    observers = []
    for agent in definition.observers:
        result = results[agent.indicator_id]
        matched = None
        if result["status"] == "CALCULATED":
            value = Decimal(result["value"])
            matched = value >= agent.threshold if agent.comparison == "gte" else value <= agent.threshold
        observers.append({"agent_id": agent.agent_id, "name": agent.name, "indicator_id": agent.indicator_id,
            "comparison": agent.comparison, "threshold": str(agent.threshold), "matched": matched,
            "status": "OBSERVED" if matched is not None else "UNAVAILABLE",
            "message": (agent.matched_message if matched else agent.unmatched_message) if matched is not None else "输入不足，暂不能判断观察条件。",
            "unit": result.get("unit"), "evidence_refs": result.get("evidence_refs", [])})
    return indicators, observers


def profitability_template():
    return PersonalResearchDefinition(name="盈利质量观察", description="组合财务工具与研究助手，生成自定义净利率及阈值观察。",
        data_agents=(DataAgent(agent_id="finance", name="财务资料助手", skill_id="hithink-finance-query", version="1.0.0", fields=("net_profit", "revenue")),),
        indicators=(PersonalIndicator(indicator_id="margin", name="我的盈利质量指标", operator="ratio_pct", inputs=("finance.net_profit", "finance.revenue")),),
        observers=(ObservationAgent(agent_id="profitability", name="盈利观察助手", indicator_id="margin", comparison="gte", threshold=Decimal("15"),
            matched_message="净利率达到 15% 的研究观察条件，可继续比较历史盈利稳定性。", unmatched_message="净利率未达到 15% 的研究观察条件，需进一步了解成本与利润变化。"),))


class PersonalResearchService:
    def __init__(self, *, store, provider, registry, runtime, clock=None, facts=None, evidence_mode="LIVE", max_runs=500):
        if evidence_mode not in {"LIVE", "CONTROLLED_REGRESSION"} or (facts is not None and evidence_mode != "LIVE"):
            raise ValueError("invalid personal research evidence configuration")
        self.store, self.provider, self.registry, self.runtime = store, provider, registry, runtime
        self.clock = clock or (lambda: datetime.now(UTC))
        self.facts, self.evidence_mode, self.max_runs = facts, evidence_mode, max_runs
        self._tasks = {}
        self._closed = False
        # A single-worker service cannot resume provider coroutines after a
        # process restart. Retain their inputs and report interruption plainly.
        with self.store._lock:
            rows = self.store._connection.execute("SELECT owner_id,result_json FROM personal_research_runs WHERE status IN ('QUEUED','RUNNING')").fetchall()
        for row in rows:
            run = json.loads(row["result_json"])
            run.update(status="FAILED", error_code="RESEARCH_INTERRUPTED", finished_at=self.clock().isoformat())
            self._persist(row["owner_id"], run)

    def catalog(self, owner_id):
        skills = [{**item, "fields": list(_FIELDS[item["operation"]])} for item in self.registry.list(owner_id) if item["operation"] in _FIELDS]
        template = profitability_template().model_dump(mode="json")
        return {"skills": skills, "agent_roles": deepcopy(_ROLES), "operators": [
            {"operator": "ratio_pct", "label": "比率（百分比）", "arity": 2, "formula": "输入 1 ÷ 输入 2 × 100%"},
            {"operator": "difference", "label": "差值", "arity": 2, "formula": "输入 1 − 输入 2"},
            {"operator": "weighted_mean", "label": "加权平均", "arity": None, "formula": "各输入与权重乘积之和 ÷ 权重之和"}],
            "templates": [{"template_id": "profitability.v1", "name": template["name"], "definition": template}], "max_nodes": 32}

    def _validate_skills(self, owner_id, definition, *, require_callable):
        available = {(item["skill_id"], item["version"]): item for item in self.registry.list(owner_id)}
        for agent in definition.data_agents:
            item = available.get((agent.skill_id, agent.version))
            if item is None or item["operation"] not in _FIELDS or not set(agent.fields) <= set(_FIELDS[item["operation"]]):
                raise PersonalResearchInvalid("data agent must bind a reviewed scalar capability and fields")
            if require_callable and not item["callable"]:
                raise SkillUnavailable("data agent capability version is disabled or unavailable")

    @staticmethod
    def _system(row):
        definition = json.loads(row["definition_json"])
        return {"system_id": row["system_id"], "revision": row["revision"], "name": definition["name"],
                "definition": definition, "updated_at": row["created_at"], "personal_skill_id": "personal:" + row["system_id"]}

    def list(self, owner_id):
        with self.store._lock:
            rows = self.store._connection.execute("SELECT v.* FROM personal_research_versions v WHERE v.owner_id=? AND v.revision=(SELECT MAX(p.revision) FROM personal_research_versions p WHERE p.owner_id=v.owner_id AND p.system_id=v.system_id) ORDER BY v.created_at DESC,v.system_id", (owner_id,)).fetchall()
        return [self._system(row) for row in rows]

    def get(self, owner_id, system_id, revision=None):
        with self.store._lock:
            row = self.store._connection.execute("SELECT * FROM personal_research_versions WHERE owner_id=? AND system_id=?" + (" AND revision=?" if revision is not None else " ORDER BY revision DESC LIMIT 1"), (owner_id, system_id, revision) if revision is not None else (owner_id, system_id)).fetchone()
        if row is None:
            raise PersonalResearchNotFound("personal research system is unavailable")
        return self._system(row)

    def save(self, owner_id, system_id, body: PersonalResearchSave):
        if not re.fullmatch(SYSTEM_ID, system_id):
            raise PersonalResearchInvalid("invalid personal research system identifier")
        self._validate_skills(owner_id, body.definition, require_callable=False)
        with self.store._lock:
            connection = self.store._connection
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute("SELECT MAX(revision) AS revision FROM personal_research_versions WHERE owner_id=? AND system_id=?", (owner_id, system_id)).fetchone()
                revision = row["revision"] or 0
                if revision != body.expected_revision:
                    raise StoreConflictError("personal research system revision changed")
                connection.execute("INSERT INTO personal_research_versions VALUES (?,?,?,?,?)", (owner_id, system_id, revision + 1, body.definition.model_dump_json(), self.clock().isoformat()))
                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                raise
        return self.get(owner_id, system_id, revision + 1)

    def _prepare(self, owner_id, system_id, request):
        if self._closed:
            raise ResearchCapacityError("personal research service is closed")
        record = self.get(owner_id, system_id)
        if record["revision"] != request.expected_revision:
            raise StoreConflictError("personal research system revision changed")
        if request.as_of is not None and request.as_of > self.clock():
            raise PersonalResearchInvalid("research cutoff cannot be in the future")
        _period(request.period)
        definition = PersonalResearchDefinition.model_validate(record["definition"])
        return record, definition

    def _persist(self, owner_id, run):
        with self.store._lock:
            self.store._connection.execute("UPDATE personal_research_runs SET result_json=?,status=?,updated_at=? WHERE owner_id=? AND run_id=?", (_json(run), run["status"], self.clock().isoformat(), owner_id, run["run_id"]))

    def _new_run(self, owner_id, record, request, mode):
        now = self.clock().isoformat()
        run = {"run_id": uuid4().hex, "system_id": record["system_id"], "system_revision": record["revision"],
            "name": record["name"], "personal_skill_id": record["personal_skill_id"], "status": "QUEUED", "subject": request.subject.split(".")[0],
            "period": request.period, "as_of": request.as_of.isoformat() if request.as_of is not None else None,
            "effective_as_of": (request.as_of or self.clock()).isoformat(), "data_mode": mode, "is_synthetic": mode == "CONTROLLED_REGRESSION",
            "definition_snapshot": record["definition"], "definition_sha256": sha256(_json(record["definition"]).encode()).hexdigest(),
            "created_at": now, "finished_at": None, "elapsed_ms": None, "data_agents": [], "indicators": [], "observers": [],
            "agent_roles": deepcopy(_ROLES), "verification_status": "NOT_VERIFIED", "notice": "阈值仅表达个人研究观察条件，不构成买卖指令；金融计算由确定性程序执行。"}
        with self.store._lock:
            self.store._connection.execute("INSERT INTO personal_research_runs VALUES (?,?,?,?,?,?,?,?,?)", (owner_id, run["run_id"], record["system_id"], record["revision"], request.model_dump_json(), _json(run), "QUEUED", now, now))
        return run

    def submit(self, owner_id, system_id, request: PersonalResearchRun):
        record, definition = self._prepare(owner_id, system_id, request)
        self._validate_skills(owner_id, definition, require_callable=True)
        if len(self._tasks) >= self.max_runs:
            raise ResearchCapacityError("personal research run retention is exhausted")
        run = self._new_run(owner_id, record, request, self.evidence_mode)
        task = asyncio.create_task(self._execute(owner_id, run, definition, request))
        self._tasks[run["run_id"]] = task
        task.add_done_callback(lambda task, run_id=run["run_id"]: self._finished(owner_id, run_id, task))
        return deepcopy(run)

    async def run_and_wait(self, owner_id, system_id, request: PersonalResearchRun):
        submitted = self.submit(owner_id, system_id, request)
        await self._tasks[submitted["run_id"]]
        return self.get_run(owner_id, submitted["run_id"])

    def _finished(self, owner_id, run_id, task):
        self._tasks.pop(run_id, None)
        run = self.get_run(owner_id, run_id)
        if run["status"] in {"QUEUED", "RUNNING"}:
            run.update(status="CANCELLED" if task.cancelled() else "FAILED", finished_at=self.clock().isoformat())
            self._persist(owner_id, run)
        if not task.cancelled():
            task.exception()

    async def _execute(self, owner_id, run, definition, request):
        began = time.perf_counter()
        async def operation():
            run["status"] = "RUNNING"
            self._persist(owner_id, run)
            for agent in definition.data_agents:
                skill = self.registry.get(agent.skill_id, agent.version)
                node = LiveResearchNode(node_id=agent.agent_id, operation=skill["operation"], subject=run["subject"], required_fields=agent.fields)
                query = run["subject"] + " " + " ".join(_QUERIES[field] for field in agent.fields)
                if request.period is not None and skill["operation"] == "COMPANY_DATA":
                    query += " " + request.period
                remaining = max(1, int((request.budget_seconds - (time.perf_counter() - began)) * 1000))
                provider_request = ProviderRequest(request_id=run["run_id"] + ":" + agent.agent_id, operation=skill["operation"], subject=query,
                                                   as_of=request.as_of, timeout_ms=remaining)
                scoped = self.registry.scoped_provider(self.provider, owner_id, skill_id=agent.skill_id, version=agent.version)
                async with self.runtime.provider_slot():
                    result = await execute_with_budget(scoped, provider_request)
                cutoff = request.as_of or self.clock()
                run["effective_as_of"] = cutoff.isoformat()
                normalized = normalize_live_observations(node, result, cutoff=cutoff)
                normalized.update(agent_id=agent.agent_id, name=agent.name, operation=skill["operation"], capability_snapshot=getattr(scoped, "captured_skill", None))
                if self.facts is not None:
                    references = self.facts.save_node(owner_id=owner_id, run_id=run["run_id"], node_id=agent.agent_id,
                        request_payload={"provider_request": provider_request.model_dump(mode="json"), "research_node": node.model_dump(mode="json"), "capability_snapshot": normalized["capability_snapshot"]},
                        provider_result=result, normalized=normalized, input_versions={"personal_system_id": run["system_id"], "personal_system_revision": run["system_revision"], "skill_id": agent.skill_id, "skill_version": agent.version})
                    normalized.update(references)
                run["data_agents"].append(normalized)
                self._persist(owner_id, run)
            self._calculate(run, definition)
            return run
        try:
            await self.runtime.run(owner_id, operation, budget_seconds=request.budget_seconds)
        except asyncio.CancelledError:
            run["status"] = "CANCELLED"
            raise
        except TimeoutError:
            run["status"] = "TIMED_OUT"
        except (ResearchCapacityError, ResearchRuntimeClosed):
            run.update(status="FAILED", error_code="RESEARCH_CAPACITY")
        except Exception:
            run.update(status="FAILED", error_code="RESEARCH_EXECUTION_FAILED")
        finally:
            run.update(finished_at=self.clock().isoformat(), elapsed_ms=round((time.perf_counter() - began) * 1000, 3))
            self._persist(owner_id, run)

    @staticmethod
    def _calculate(run, definition):
        run["indicators"], run["observers"] = calculate_personal_indicators(definition, run["data_agents"], subject=run["subject"], period=run["period"], as_of=datetime.fromisoformat(run["effective_as_of"]))
        run["status"] = "COMPLETED" if all(i["status"] == "CALCULATED" for i in run["indicators"]) else "PARTIAL"
        run["verification_status"] = "DERIVED_FROM_SINGLE_SOURCE_UNVERIFIED"

    async def from_facts(self, owner_id, system_id, request: PersonalResearchFactRun):
        if self.facts is None:
            raise PersonalResearchInvalid("stored research facts are unavailable")
        record, definition = self._prepare(owner_id, system_id, request)
        self._validate_skills(owner_id, definition, require_callable=True)
        if set(request.fact_ids) != {agent.agent_id for agent in definition.data_agents}:
            raise PersonalResearchInvalid("stored facts must bind every defined data agent")
        if len(self._tasks) >= self.max_runs:
            raise ResearchCapacityError("personal research run retention is exhausted")
        began = time.perf_counter()
        run = self._new_run(owner_id, record, request, "STORED_FACTS")
        self._tasks[run["run_id"]] = asyncio.current_task()

        def checkpoint():
            # asyncio.timeout cannot interrupt bounded synchronous database
            # reads or arithmetic until the loop yields. Enforce their elapsed
            # budget explicitly, including any earlier queue wait.
            if time.perf_counter() - began >= request.budget_seconds:
                raise TimeoutError("stored-fact research deadline expired")

        async def operation():
            checkpoint()
            self._validate_skills(owner_id, definition, require_callable=True)
            run["status"] = "RUNNING"
            self._persist(owner_id, run)
            for agent in definition.data_agents:
                checkpoint()
                skill = self.registry.get(agent.skill_id, agent.version)
                facts = []
                for fact_id in request.fact_ids[agent.agent_id]:
                    facts.append(self.facts.get(owner_id, fact_id))
                    checkpoint()
                    await asyncio.sleep(0)
                if any(fact.get("input_versions", {}).get("skill_id") != agent.skill_id or fact.get("input_versions", {}).get("skill_version") != agent.version for fact in facts):
                    raise PersonalResearchInvalid("stored facts must come from the bound capability version")
                run["data_agents"].append({"agent_id": agent.agent_id, "name": agent.name, "operation": skill["operation"], "status": "SUCCESS", "observations": facts, "fact_refs": list(request.fact_ids[agent.agent_id]), "input_mode": "STORED_FACTS"})
            checkpoint()
            self._calculate(run, definition)
            checkpoint()
            return run

        try:
            await self.runtime.run(owner_id, operation, budget_seconds=request.budget_seconds)
        except asyncio.CancelledError:
            run["status"] = "CANCELLED"
            raise
        except TimeoutError:
            run["status"] = "TIMED_OUT"
        except Exception:
            run["status"] = "FAILED"
            raise
        finally:
            run.update(finished_at=self.clock().isoformat(), elapsed_ms=round((time.perf_counter() - began) * 1000, 3))
            self._persist(owner_id, run)
            self._tasks.pop(run["run_id"], None)
        return run

    def get_run(self, owner_id, run_id):
        with self.store._lock:
            row = self.store._connection.execute("SELECT result_json FROM personal_research_runs WHERE owner_id=? AND run_id=?", (owner_id, run_id)).fetchone()
        if row is None:
            raise PersonalResearchNotFound("personal research run is unavailable")
        return json.loads(row["result_json"])

    async def cancel(self, owner_id, run_id):
        self.get_run(owner_id, run_id)
        task = self._tasks.get(run_id)
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            self._finished(owner_id, run_id, task)
        return self.get_run(owner_id, run_id)

    async def aclose(self):
        self._closed = True
        tasks = tuple(self._tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
