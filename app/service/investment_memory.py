"""Confirmed long-term preferences that constrain deterministic rebalancing.

Historical context snapshots remain read-only history. This module learns only
from the confirmed trading ledger and explicit, structured preference saves.
No text from a model, chat history or retrieved document can change a policy.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
import json
from typing import Annotated, Callable, Literal

from pydantic import Field

from app.contracts.evidence import ContractModel
from app.gates import GateStatus
from app.portfolio import AssetType
from app.rebalancing.contracts import PortfolioRebalancingRequest, PortfolioRebalancingResponse
from app.service.portfolio_rebalancing import PortfolioRebalancingService
from app.store.sqlite import StoreConflictError, StoreCorruptError, _validate_owner
from app.trading_history import calculate_trading_style, TradingStyleStatus


Percent = Annotated[Decimal, Field(ge=0, le=100, allow_inf_nan=False)]


class InvestmentPreferences(ContractModel):
    max_turnover_pct: Percent | None = None
    minimum_cash_pct: Percent | None = None
    deadband_pct: Percent | None = None


class InvestmentPolicyParameters(ContractModel):
    max_turnover_pct: Percent
    minimum_cash_pct: Percent
    deadband_pct: Percent


class PreferenceMemoryWrite(ContractModel):
    expected_revision: int = Field(ge=0)
    preferences: InvestmentPreferences


class PreferenceMemory(ContractModel):
    schema_version: Literal["investment-preference-memory.v1"] = "investment-preference-memory.v1"
    owner_id: str
    revision: int = Field(ge=1)
    preferences: InvestmentPreferences
    source: Literal["EXPLICIT_USER_SAVE"] = "EXPLICIT_USER_SAVE"
    saved_at: datetime


class InvestmentPolicyCandidate(ContractModel):
    candidate_id: str
    memory_revision: int = Field(ge=1)
    style_profile_version: int = Field(ge=0)
    source_hash: str
    primary_style: str | None
    style_status: str
    parameters: InvestmentPolicyParameters
    basis: tuple[str, ...]


class InvestmentPolicyConfirmation(ContractModel):
    candidate_id: str = Field(min_length=1, max_length=100)
    expected_memory_revision: int = Field(ge=1)
    expected_style_profile_version: int = Field(ge=0)


class ConfirmedInvestmentPolicy(InvestmentPolicyCandidate):
    schema_version: Literal["confirmed-investment-policy.v1"] = "confirmed-investment-policy.v1"
    owner_id: str
    revision: int = Field(ge=1)
    confirmed_at: datetime


class InvestmentMemoryState(ContractModel):
    schema_version: Literal["investment-memory-state.v1"] = "investment-memory-state.v1"
    memory: PreferenceMemory | None
    candidate: InvestmentPolicyCandidate | None
    policy: ConfirmedInvestmentPolicy | None
    policy_status: Literal["ACTIVE", "STALE", "UNCONFIRMED"]
    notice: str


class PersonalizedRebalancingComparison(ContractModel):
    schema_version: Literal["personalized-rebalancing-comparison.v1"] = "personalized-rebalancing-comparison.v1"
    baseline: PortfolioRebalancingResponse
    personalized: PortfolioRebalancingResponse
    policy: ConfirmedInvestmentPolicy
    source_target_weights: dict[str, Percent]
    effective_target_weights: dict[str, Percent]
    effective_parameters: InvestmentPolicyParameters
    target_adjustment_ratio: Decimal = Field(ge=0, le=1, allow_inf_nan=False)
    application_issues: tuple[str, ...]
    policy_ruleset_version: Literal["investment-style-policy.v1"]
    differences: tuple[str, ...]
    disclaimer: str


class InvestmentPolicyStale(ValueError):
    """A confirmed policy no longer describes the current source revisions."""


def _hash(value) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), default=str).encode()).hexdigest()


class InvestmentMemoryService:
    def __init__(self, store, *, clock: Callable[[], datetime] | None = None,
                 planner: PortfolioRebalancingService | None = None):
        self.store = store
        self.clock = clock or (lambda: datetime.now(UTC))
        self.planner = planner or PortfolioRebalancingService()

    def _latest(self, owner_id, table, model):
        row = self.store._connection.execute(
            f"SELECT * FROM {table} WHERE owner_id=? ORDER BY revision DESC LIMIT 1", (owner_id,)
        ).fetchone()
        if row is None:
            return None
        try:
            result = model.model_validate_json(row["payload_json"])
            if result.owner_id != owner_id or result.revision != row["revision"]:
                raise ValueError("stored owner or revision differs")
            return result
        except ValueError:
            raise StoreCorruptError("investment memory integrity check failed") from None

    def _sources(self, owner_id):
        trades = self.store.list_trade_records(owner_id)
        stored_style = self.store.get_latest_trading_style_profile(owner_id)
        questionnaire = self.store.get_latest_questionnaire_snapshot(owner_id)
        behavior = self.store.get_latest_behavior_profile(owner_id)
        style_version = stored_style.profile_version if stored_style is not None else 0
        style = calculate_trading_style(owner_id, trades, calculated_at=self.clock(),
                                        profile_version=max(1, style_version))
        # Include revisions and withdrawals, not only the active IDs used by a
        # style calculation. Corrections must invalidate an earlier confirmation.
        source_hash = _hash({
            "owner": owner_id,
            "trades": [trade.model_dump(mode="json") for trade in trades],
            "stored_style": stored_style.model_dump(mode="json") if stored_style else None,
            "questionnaire": questionnaire.model_dump(mode="json") if questionnaire else None,
            "behavior": behavior.model_dump(mode="json") if behavior else None,
            "eligible_trade_ids": style.active_trade_ids,
            "style": style.primary_style,
            "style_status": style.status,
        })
        return style, style_version, source_hash

    def _candidate(self, owner_id, memory):
        if memory is None:
            return None
        style, style_version, source_hash = self._sources(owner_id)
        values = {"max_turnover_pct": Decimal("50"), "minimum_cash_pct": Decimal("0"),
                  "deadband_pct": Decimal("0.50")}
        basis = []
        if style.status == TradingStyleStatus.CALCULATED:
            # A behavioral policy controls the execution pace; it never raises
            # suitability or duplicates observed speculative risk-taking.
            rules = {
                "低频长持型": ("10", "5", "2"),
                "稳健均衡型": ("20", "5", "1"),
                "主动波段型": ("30", "5", "0.50"),
                "高频短线型": ("10", "5", "1"),
            }
            turnover, cash, deadband = rules[style.primary_style]
            values.update(max_turnover_pct=Decimal(turnover), minimum_cash_pct=Decimal(cash),
                          deadband_pct=Decimal(deadband))
            basis.append(f"已确认交易账本：{style.metrics.trade_count} 笔、{style.metrics.observed_span_days} 天；观察风格为{style.primary_style}")
            if style.primary_style == "高频短线型":
                basis.append("高频交易历史仅用于生成减少换手的纪律约束，不放大交易频率或风险预算")
        else:
            basis.append("交易历史不足以形成稳定风格，未采用行为推导；空白项使用明确的初始候选参数")
        labels = {"max_turnover_pct": "单次调仓换手上限", "minimum_cash_pct": "最低现金比例",
                  "deadband_pct": "忽略微调幅度"}
        for key, value in memory.preferences.model_dump().items():
            if value is not None:
                # Explicit preference and observed discipline combine in the
                # stricter direction. A saved preference cannot loosen a policy.
                if style.status == TradingStyleStatus.CALCULATED:
                    values[key] = min(values[key], value) if key == "max_turnover_pct" else max(values[key], value)
                else:
                    values[key] = value
                basis.append(f"用户显式保存：{labels[key]} {value}%")
        parameters = InvestmentPolicyParameters(**values)
        identity = _hash({"memory": memory.model_dump(mode="json"), "sources": source_hash,
                          "parameters": parameters.model_dump(mode="json"), "rules": "investment-style-policy.v1"})
        return InvestmentPolicyCandidate(
            candidate_id="investment-policy:" + identity[:32], memory_revision=memory.revision,
            style_profile_version=style_version, source_hash=source_hash,
            primary_style=style.primary_style, style_status=style.status,
            parameters=parameters, basis=tuple(basis),
        )

    def state(self, owner_id):
        owner_id = _validate_owner(owner_id)
        with self.store._lock:
            memory = self._latest(owner_id, "investment_preference_memories", PreferenceMemory)
            policy = self._latest(owner_id, "investment_style_policies", ConfirmedInvestmentPolicy)
            candidate = self._candidate(owner_id, memory)
            matches = candidate is not None and policy is not None and (
                policy.model_dump(include=set(InvestmentPolicyCandidate.model_fields)) == candidate.model_dump()
            )
            status = "UNCONFIRMED" if policy is None else "ACTIVE" if matches else "STALE"
            return {"schema_version": "investment-memory-state.v1", "memory": memory,
                    "candidate": candidate, "policy": policy, "policy_status": status,
                    "notice": "偏好记忆只影响经确认的调仓参数；历史持仓快照不会恢复为当前行情。"}

    def _write(self, operation):
        with self.store._lock:
            connection = self.store._connection
            connection.execute("BEGIN IMMEDIATE")
            try:
                result = operation(connection)
                connection.execute("COMMIT")
                return result
            except BaseException:
                connection.execute("ROLLBACK")
                raise

    def save_preferences(self, owner_id, request: PreferenceMemoryWrite):
        owner_id = _validate_owner(owner_id)
        def write(connection):
            previous = self._latest(owner_id, "investment_preference_memories", PreferenceMemory)
            revision = previous.revision if previous is not None else 0
            if revision != request.expected_revision:
                raise StoreConflictError("investment preference revision conflict")
            memory = PreferenceMemory(owner_id=owner_id, revision=revision + 1,
                                      preferences=request.preferences, saved_at=self.clock())
            connection.execute("INSERT INTO investment_preference_memories VALUES (?,?,?,?)",
                               (owner_id, memory.revision, memory.model_dump_json(), memory.saved_at.isoformat()))
            return memory
        self._write(write)
        return self.state(owner_id)

    def confirm_policy(self, owner_id, request: InvestmentPolicyConfirmation):
        owner_id = _validate_owner(owner_id)
        def write(connection):
            memory = self._latest(owner_id, "investment_preference_memories", PreferenceMemory)
            candidate = self._candidate(owner_id, memory)
            if (candidate is None or candidate.candidate_id != request.candidate_id
                    or candidate.memory_revision != request.expected_memory_revision
                    or candidate.style_profile_version != request.expected_style_profile_version):
                raise InvestmentPolicyStale("candidate sources changed; generate a new candidate")
            previous = self._latest(owner_id, "investment_style_policies", ConfirmedInvestmentPolicy)
            policy = ConfirmedInvestmentPolicy(**candidate.model_dump(), owner_id=owner_id,
                                               revision=1 if previous is None else previous.revision + 1,
                                               confirmed_at=self.clock())
            connection.execute("INSERT INTO investment_style_policies VALUES (?,?,?,?)",
                               (owner_id, policy.revision, policy.model_dump_json(), policy.confirmed_at.isoformat()))
            return policy
        self._write(write)
        return self.state(owner_id)

    def resolve_policy(self, owner_id, expected_revision: int):
        state = self.state(owner_id)
        policy = state["policy"]
        if state["policy_status"] != "ACTIVE" or policy.revision != expected_revision:
            raise InvestmentPolicyStale("confirmed investment policy is unavailable or stale")
        return policy

    def apply_policy(self, request: PortfolioRebalancingRequest, policy: ConfirmedInvestmentPolicy):
        if request.owner_id != policy.owner_id:
            raise InvestmentPolicyStale("policy owner differs from rebalancing owner")
        params = policy.parameters
        effective = {
            "max_turnover_pct": min(request.max_turnover_pct, params.max_turnover_pct),
            "minimum_cash_pct": max(request.minimum_cash_pct, params.minimum_cash_pct),
            "deadband_pct": max(request.deadband_pct, params.deadband_pct),
        }
        positions = request.bundle.position_snapshot.positions
        total = sum((position.market_value for position in positions), Decimal("0"))
        if total <= 0:
            raise ValueError("portfolio value must be positive")
        current = {position.asset_id: position.market_value / total * 100 for position in positions}
        desired = dict(request.target_weights)
        cash_ids = [position.asset_id for position in positions if position.asset_type == AssetType.CASH]
        issues = []

        def preserve_cash_floor(weights):
            cash_weight = sum((weights.get(key, Decimal("0")) for key in cash_ids), Decimal("0"))
            floor = effective["minimum_cash_pct"]
            if cash_weight >= floor:
                return
            if not cash_ids:
                issues.append("当前组合缺少现金账户项，无法落实个人最低现金比例")
                return
            noncash = sum((value for key, value in weights.items() if key not in cash_ids), Decimal("0"))
            if noncash <= 0:
                return
            factor = (100 - floor) / noncash
            for key in tuple(weights):
                if key not in cash_ids:
                    weights[key] *= factor
            for key in cash_ids:
                weights[key] = weights.get(key, Decimal("0"))
            weights[cash_ids[0]] += floor - cash_weight

        preserve_cash_floor(desired)
        assets = set(current) | set(desired)
        # Match the existing planner's one-way turnover definition. Cash is a
        # settlement balance and is not counted as a buy/sell order.
        turnover = sum((abs(desired.get(key, Decimal("0")) - current.get(key, Decimal("0")))
                        for key in assets if key not in cash_ids), Decimal("0")) / 2
        ratio = min(Decimal("1"), effective["max_turnover_pct"] / turnover) if turnover else Decimal("1")
        adjusted = {key: current.get(key, Decimal("0")) + ratio * (
            desired.get(key, Decimal("0")) - current.get(key, Decimal("0"))) for key in assets}
        # Cash and risk requirements have priority. If a cash rescue needs more
        # turnover than the personal cap, the existing planner reports a conflict.
        preserve_cash_floor(adjusted)
        if adjusted:
            residual = Decimal("100") - sum(adjusted.values(), Decimal("0"))
            adjusted[max(adjusted, key=lambda key: adjusted[key])] += residual
        applied = request.model_copy(update={"target_weights": adjusted, **effective})
        applied = PortfolioRebalancingRequest.model_validate(applied.model_dump())
        details = {"policy": policy, "source_target_weights": dict(request.target_weights),
                   "effective_target_weights": adjusted, "effective_parameters": effective,
                   "target_adjustment_ratio": ratio, "application_issues": tuple(dict.fromkeys(issues)),
                   "policy_ruleset_version": "investment-style-policy.v1"}
        return applied, details

    def compare(self, request: PortfolioRebalancingRequest, expected_policy_revision: int):
        policy = self.resolve_policy(request.owner_id, expected_policy_revision)
        applied, details = self.apply_policy(request, policy)
        baseline = self.planner.plan_rebalancing(request)
        personalized = self.planner.plan_rebalancing(applied)
        issues = list(personalized.issues) + list(details["application_issues"])
        if request.confirmed_profile is None:
            issues.append("尚无已确认风险画像，个人方案需要完成适当性检查后复核")
        if issues:
            personalized = personalized.model_copy(update={"status": GateStatus.REVIEW_REQUIRED,
                                                           "issues": tuple(dict.fromkeys(issues))})
        differences = (
            f"单次调仓换手：{baseline.metrics.total_turnover_pct}% → {personalized.metrics.total_turnover_pct}%",
            f"执行步骤：{len(baseline.execution_steps)} 项 → {len(personalized.execution_steps)} 项",
            f"交易费用：{baseline.metrics.net_turnover_cost} 元 → {personalized.metrics.net_turnover_cost} 元",
            f"扣费后现金：{baseline.metrics.cash_after_cny} 元 → {personalized.metrics.cash_after_cny} 元",
        )
        return {"schema_version": "personalized-rebalancing-comparison.v1", "baseline": baseline,
                "personalized": personalized, **details, "differences": differences,
                "disclaimer": "仅提供调仓测算和个人约束对照，不自动提交交易。"}
