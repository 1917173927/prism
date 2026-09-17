"""Versioned deterministic presentation rules for questionnaire profiles.

The questionnaire snapshot is the source of truth. This module derives only
investor-facing presentation, service-routing and explanation fields. It does
not read holdings, trades or model output, and it never changes suitability.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Literal, Self

from pydantic import Field, model_validator

from app.contracts.evidence import ContractModel, NonEmptyStr
from app.profile.behavior import SuitabilityLevel, suitability_for_score
from app.profile.contracts import PercentageRange, RiskLevel
from app.profile.questionnaire import DIMENSION_KEYS, QUESTIONNAIRE_TEMPLATE, QuestionnaireSnapshot
from app.profile.scoring import risk_level_for_score


LEGACY_PRESENTATION_RULESET_VERSION = "investor-profile-presentation-rules.v1"
PRESENTATION_RULESET_VERSION = "investor-profile-presentation-rules.v2"
_LEGACY_QUESTIONNAIRE_RULESET_VERSION = "investor-questionnaire-rules.v1"
_ALLOCATION_KEYS = ("cash", "bonds", "equity")
_DIMENSION_LABELS = {
    "risk": "风险承受能力", "exp": "投资经验", "act": "操作活跃度", "res": "研究习惯",
    "inf": "信息投入", "ai": "AI 信任度", "per": "个性化需求", "aid": "辅助需求",
}
_DIMENSION_SHORT_LABELS = {
    "risk": "风险承受", "exp": "投资经验", "act": "操作活跃", "res": "研究习惯",
    "inf": "信息投入", "ai": "AI 信任", "per": "个性需求", "aid": "辅助需求",
}
_RISK_LEVEL_LABELS = {
    RiskLevel.CONSERVATIVE: "保守型", RiskLevel.BALANCED: "平衡型", RiskLevel.GROWTH: "成长型",
}
_SUITABILITY_LABELS = {
    SuitabilityLevel.C1: "保守型", SuitabilityLevel.C2: "相对保守型", SuitabilityLevel.C3: "稳健型",
    SuitabilityLevel.C4: "相对积极型", SuitabilityLevel.C5: "积极型",
}
_LEGACY_ARCHETYPE_LABELS = {
    SuitabilityLevel.C1: "保守稳健型", SuitabilityLevel.C2: "谨慎平衡型", SuitabilityLevel.C3: "平衡成长型",
    SuitabilityLevel.C4: "稳健成长型", SuitabilityLevel.C5: "积极成长型",
}
_LEGACY_ALLOCATION_RULES: dict[SuitabilityLevel, tuple[tuple[str, str, Decimal], ...]] = {
    SuitabilityLevel.C1: (("cash", "现金", Decimal("50")), ("bonds", "债券", Decimal("45")), ("equity", "权益", Decimal("5"))),
    SuitabilityLevel.C2: (("cash", "现金", Decimal("30")), ("bonds", "债券", Decimal("50")), ("equity", "权益", Decimal("20"))),
    SuitabilityLevel.C3: (("cash", "现金", Decimal("20")), ("bonds", "债券", Decimal("40")), ("equity", "权益", Decimal("40"))),
    SuitabilityLevel.C4: (("cash", "现金", Decimal("10")), ("bonds", "债券", Decimal("20")), ("equity", "权益", Decimal("70"))),
    SuitabilityLevel.C5: (("cash", "现金", Decimal("5")), ("bonds", "债券", Decimal("15")), ("equity", "权益", Decimal("80"))),
}
_LEGACY_EQUITY_RANGES = {
    SuitabilityLevel.C1: (Decimal("0"), Decimal("15")), SuitabilityLevel.C2: (Decimal("10"), Decimal("30")),
    SuitabilityLevel.C3: (Decimal("30"), Decimal("50")), SuitabilityLevel.C4: (Decimal("60"), Decimal("80")),
    SuitabilityLevel.C5: (Decimal("70"), Decimal("90")),
}
_ALLOCATION_RULES: dict[SuitabilityLevel, tuple[tuple[str, str, Decimal], ...]] = {
    SuitabilityLevel.C1: (("cash", "货币类", Decimal("60")), ("bonds", "债券", Decimal("40")), ("equity", "权益", Decimal("0"))),
    SuitabilityLevel.C2: (("cash", "货币类", Decimal("30")), ("bonds", "债券", Decimal("50")), ("equity", "权益", Decimal("20"))),
    SuitabilityLevel.C3: (("cash", "货币类", Decimal("10")), ("bonds", "债券", Decimal("50")), ("equity", "权益", Decimal("40"))),
    SuitabilityLevel.C4: (("cash", "货币类", Decimal("10")), ("bonds", "债券", Decimal("20")), ("equity", "权益", Decimal("70"))),
    SuitabilityLevel.C5: (("cash", "货币类", Decimal("5")), ("bonds", "债券", Decimal("0")), ("equity", "权益", Decimal("95"))),
}
_EQUITY_RANGES = {
    SuitabilityLevel.C1: (Decimal("0"), Decimal("0")), SuitabilityLevel.C2: (Decimal("0"), Decimal("20")),
    SuitabilityLevel.C3: (Decimal("30"), Decimal("50")), SuitabilityLevel.C4: (Decimal("60"), Decimal("80")),
    SuitabilityLevel.C5: (Decimal("80"), Decimal("100")),
}
_FEAT_MAP = {
    "market": "market", "industry": "industry", "stock": "stock", "fund": "fund", "bond": "bond",
    "portfolio": "optimize", "risk": "optimize",
}
_DEFAULT_FEATS = ("market", "stock", "optimize")
_RISK_NOTICE = "仅作适当性与服务展示参考，不构成投资建议。"


class ProfilePresentationDimension(ContractModel):
    key: Literal["risk", "exp", "act", "res", "inf", "ai", "per", "aid"]
    label: NonEmptyStr
    short_label: NonEmptyStr
    score: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))


class ProfileKeyFact(ContractModel):
    key: NonEmptyStr
    label: NonEmptyStr
    value: NonEmptyStr


class ProfileAssetAllocation(ContractModel):
    key: Literal["cash", "bonds", "equity"]
    label: NonEmptyStr
    target_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))


class ProfileRuleTraceEntry(ContractModel):
    rule_id: NonEmptyStr
    label: NonEmptyStr
    evidence: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)


class ProfilePersonaTrace(ContractModel):
    rule_id: NonEmptyStr
    gates: tuple[NonEmptyStr, ...]
    raw_fit: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    conflict_penalty: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    conflict_reason: NonEmptyStr | None = None
    final_fit: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))


class ProfileFeatTrace(ContractModel):
    source_question: Literal["Q13"] = "Q13"
    selected_option_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    mappings: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    defaulted: bool


class ProfileRuleTrace(ContractModel):
    ruleset_version: Literal["investor-profile-presentation-rules.v2"] = PRESENTATION_RULESET_VERSION
    persona: ProfilePersonaTrace
    tags: tuple[ProfileRuleTraceEntry, ...] = Field(min_length=3, max_length=6)
    service_strategy: tuple[ProfileRuleTraceEntry, ...] = Field(min_length=1, max_length=10)
    feats: ProfileFeatTrace
    allocation: ProfileRuleTraceEntry


class ProfilePresentation(ContractModel):
    """Stable versioned payload for the questionnaire result view."""

    schema_version: Literal["profile-presentation.v1", "profile-presentation.v2"]
    ruleset_version: Literal["investor-profile-presentation-rules.v1", "investor-profile-presentation-rules.v2"]
    suitability_level: SuitabilityLevel
    suitability_label: NonEmptyStr
    risk_score: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    risk_level: RiskLevel
    archetype: NonEmptyStr = Field(json_schema_extra={"deprecated": True})
    persona: NonEmptyStr | None = None
    persona_fit: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("100"))
    tags: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=6)
    dimensions: tuple[ProfilePresentationDimension, ...] = Field(min_length=8, max_length=8)
    key_profile: tuple[ProfileKeyFact, ...] = Field(min_length=6, max_length=6)
    service_strategy: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=10)
    feats: tuple[Literal["market", "industry", "stock", "fund", "bond", "optimize"], ...] = Field(default_factory=tuple, max_length=3)
    rule_trace: ProfileRuleTrace | None = None
    asset_allocation: tuple[ProfileAssetAllocation, ...] = Field(min_length=3, max_length=3)
    equity_range: PercentageRange
    risk_notice: NonEmptyStr

    @model_validator(mode="after")
    def validate_projection(self) -> Self:
        if self.suitability_level != suitability_for_score(self.risk_score):
            raise ValueError("presentation suitability does not match risk_score")
        if self.risk_level != risk_level_for_score(self.risk_score):
            raise ValueError("presentation risk_level does not match risk_score")
        if tuple(item.key for item in self.dimensions) != DIMENSION_KEYS:
            raise ValueError("presentation dimensions must preserve questionnaire order")
        if tuple(item.key for item in self.asset_allocation) != _ALLOCATION_KEYS:
            raise ValueError("presentation allocation must contain cash, bonds and equity")
        if sum((item.target_pct for item in self.asset_allocation), Decimal("0")) != Decimal("100"):
            raise ValueError("presentation allocation must close to 100 percent")
        equity_target = next(item.target_pct for item in self.asset_allocation if item.key == "equity")
        if not self.equity_range.minimum_pct <= equity_target <= self.equity_range.maximum_pct:
            raise ValueError("equity target must be inside equity_range")
        if len(self.feats) != len(set(self.feats)):
            raise ValueError("presentation feats must be unique")
        if self.schema_version == "profile-presentation.v2":
            if self.ruleset_version != PRESENTATION_RULESET_VERSION:
                raise ValueError("v2 presentation requires v2 rules")
            if self.persona is None or self.persona_fit is None or self.rule_trace is None:
                raise ValueError("v2 presentation requires persona, fit and trace")
            if self.archetype != self.persona:
                raise ValueError("deprecated archetype must alias persona")
            if not 3 <= len(self.tags) <= 6:
                raise ValueError("v2 presentation requires three to six tags")
            if not self.feats:
                raise ValueError("v2 presentation requires recommended feats")
        elif self.ruleset_version != LEGACY_PRESENTATION_RULESET_VERSION:
            raise ValueError("v1 presentation requires v1 rules")
        return self


def _answer_map(snapshot: QuestionnaireSnapshot):
    return {answer.question_id: answer for answer in snapshot.answers}


def _question_map():
    return {question.question_id: question for question in QUESTIONNAIRE_TEMPLATE.questions}


def _selected_order(snapshot: QuestionnaireSnapshot, question_id: str) -> tuple[str, ...]:
    return _answer_map(snapshot)[question_id].selected_option_ids


def _selected_ids(snapshot: QuestionnaireSnapshot, question_id: str) -> set[str]:
    return set(_selected_order(snapshot, question_id))


def _answer_labels(snapshot: QuestionnaireSnapshot, question_id: str) -> tuple[str, ...]:
    answer = _answer_map(snapshot)[question_id]
    if answer.score is not None:
        return (f"{answer.score} / 5",)
    labels = {option.option_id: option.label for option in _question_map()[question_id].options}
    return tuple(labels[item] for item in answer.selected_option_ids if item in labels)


def _experience_label(snapshot: QuestionnaireSnapshot) -> str:
    option_id = _selected_order(snapshot, "Q2")[0]
    return {
        "lt_1y": "不足 1 年", "y1_3": "1–3 年", "y3_5": "3–5 年", "y5_10": "5+ 年", "gt_10y": "10+ 年",
    }.get(option_id, _answer_labels(snapshot, "Q2")[0])


def _key_profile(snapshot: QuestionnaireSnapshot) -> tuple[ProfileKeyFact, ...]:
    return (
        ProfileKeyFact(key="experience", label="投资经验", value=_experience_label(snapshot)),
        ProfileKeyFact(key="funds", label="可投资资金", value=_answer_labels(snapshot, "Q4")[0]),
        ProfileKeyFact(key="rebalance", label="调仓频率", value=_answer_labels(snapshot, "Q5")[0]),
        ProfileKeyFact(key="research_time", label="每日研究时间", value=_answer_labels(snapshot, "Q9")[0]),
        ProfileKeyFact(key="product_count", label="接触产品数", value=f"{len(_selected_ids(snapshot, 'Q3'))} 类"),
        ProfileKeyFact(key="ai_reference", label="AI 参考程度", value=_answer_labels(snapshot, "Q17")[0]),
    )


def _dimensions(snapshot: QuestionnaireSnapshot) -> tuple[ProfilePresentationDimension, ...]:
    return tuple(ProfilePresentationDimension(key=item.key, label=_DIMENSION_LABELS[item.key], short_label=_DIMENSION_SHORT_LABELS[item.key], score=item.score) for item in snapshot.dimensions)


def _allocation(level: SuitabilityLevel, *, legacy: bool) -> tuple[ProfileAssetAllocation, ...]:
    rules = _LEGACY_ALLOCATION_RULES if legacy else _ALLOCATION_RULES
    return tuple(ProfileAssetAllocation(key=key, label=label, target_pct=target) for key, label, target in rules[level])


def _legacy_tags(snapshot: QuestionnaireSnapshot, scores: dict[str, Decimal]) -> tuple[str, ...]:
    risk_tag = "高风险偏好" if scores["risk"] >= 65 else "平衡风险偏好" if scores["risk"] >= 45 else "稳健风险偏好"
    experience_tag = "经验丰富" if scores["exp"] >= 70 else "有一定经验" if scores["exp"] >= 40 else "投资入门"
    ai_tag = "愿意参考 AI" if scores["ai"] >= 70 else "谨慎使用 AI" if scores["ai"] < 50 else "审慎参考 AI"
    pain_count = len(_selected_ids(snapshot, "Q11") - {"none"})
    pain_tag = "多项研究痛点" if pain_count >= 3 else "有研究痛点" if pain_count else "研究路径清晰"
    return (risk_tag, experience_tag, ai_tag, pain_tag)


def _legacy_service_strategy(snapshot: QuestionnaireSnapshot, scores: dict[str, Decimal]) -> tuple[str, ...]:
    scenes = _selected_ids(snapshot, "Q13")
    strategy: list[str] = []
    if {"portfolio", "risk"} & scenes or scores["aid"] >= 60:
        strategy.append("优先提供持仓诊断、组合风险复核与资产配置参考。")
    elif {"industry", "fund"} & scenes:
        strategy.append("优先提供行业配置、ETF 筛选与风险边界说明。")
    else:
        strategy.append("优先提供市场信息整理、研究框架与风险提示。")
    strategy.append("结论同步展示关键依据、数据口径和失效条件。" if scores["res"] >= 60 or scores["inf"] >= 60 else "采用简洁分步说明，必要时展开数据依据。")
    strategy.append("AI 结论默认保留来源、计算口径和人工复核提示。" if scores["ai"] < 50 else "AI 结论保留证据入口，支持继续追问和比较观点。")
    return tuple(strategy)


def _decimal_fit(value: Decimal) -> Decimal:
    return max(Decimal("0"), min(Decimal("100"), value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _persona(snapshot: QuestionnaireSnapshot, scores: dict[str, Decimal]) -> tuple[str, Decimal, ProfilePersonaTrace]:
    q = lambda question_id, option_id: option_id in _selected_ids(snapshot, question_id)
    balance = max(Decimal("0"), Decimal("100") - Decimal("2") * abs(scores["risk"] - Decimal("55")))
    candidates: list[tuple[str, str, tuple[str, ...], Decimal, Decimal, str | None]] = []
    if scores["res"] >= 58 and scores["exp"] >= 48:
        penalty = Decimal("5") if q("Q7", "follow") else Decimal("0")
        candidates.append(("P01", "自主研究型", (f"res={scores['res']}≥58", f"exp={scores['exp']}≥48"), Decimal("0.60") * scores["res"] + Decimal("0.40") * scores["exp"], penalty, "Q7 选择直接跟随他人" if penalty else None))
    if scores["res"] >= 58 and scores["act"] < 52:
        penalty = Decimal("5") if q("Q10", "frequent_adjust") else Decimal("0")
        candidates.append(("P02", "深度价值型", (f"res={scores['res']}≥58", f"act={scores['act']}<52"), Decimal("0.65") * scores["res"] + Decimal("0.35") * (100 - scores["act"]), penalty, "Q10 选择频繁调整" if penalty else None))
    if scores["act"] >= 66 and scores["risk"] >= 58:
        penalty = Decimal("5") if q("Q10", "long_hold") else Decimal("0")
        candidates.append(("P03", "主动交易型", (f"act={scores['act']}≥66", f"risk={scores['risk']}≥58"), Decimal("0.65") * scores["act"] + Decimal("0.35") * scores["risk"], penalty, "Q10 选择长期持有" if penalty else None))
    if scores["ai"] >= 60 and scores["per"] >= 52:
        penalty = Decimal("5") if q("Q18", "ignore") else Decimal("0")
        candidates.append(("P04", "AI 协作成长型", (f"ai={scores['ai']}≥60", f"per={scores['per']}≥52"), Decimal("0.60") * scores["ai"] + Decimal("0.40") * scores["per"], penalty, "Q18 选择直接忽略 AI" if penalty else None))
    if Decimal("38") <= scores["risk"] <= Decimal("72") and scores["per"] >= 52 and scores["act"] < 62:
        penalty = Decimal("5") if q("Q6", "aggressive") else Decimal("0")
        candidates.append(("P05", "均衡配置型", (f"risk={scores['risk']}∈[38,72]", f"per={scores['per']}≥52", f"act={scores['act']}<62"), Decimal("0.40") * balance + Decimal("0.35") * scores["per"] + Decimal("0.25") * (100 - scores["act"]), penalty, "Q6 选择激进目标" if penalty else None))
    if scores["exp"] < 42 and scores["aid"] >= 52:
        penalty = Decimal("5") if q("Q1", "professional") else Decimal("0")
        candidates.append(("P06", "起步护航型", (f"exp={scores['exp']}<42", f"aid={scores['aid']}≥52"), Decimal("0.60") * (100 - scores["exp"]) + Decimal("0.40") * scores["aid"], penalty, "Q1 选择专业经历" if penalty else None))
    if not candidates:
        trace = ProfilePersonaTrace(rule_id="P07", gates=("无候选满足门槛",), raw_fit=0, conflict_penalty=0, final_fit=0)
        return "稳健成长型", Decimal("0.00"), trace
    ranked = []
    for order, candidate in enumerate(candidates):
        rule_id, label, gates, raw, penalty, reason = candidate
        ranked.append((_decimal_fit(raw - penalty), -order, rule_id, label, gates, _decimal_fit(raw), penalty, reason))
    final_fit, _, rule_id, label, gates, raw_fit, penalty, reason = max(ranked, key=lambda item: (item[0], item[1]))
    trace = ProfilePersonaTrace(rule_id=rule_id, gates=gates, raw_fit=raw_fit, conflict_penalty=penalty, conflict_reason=reason, final_fit=final_fit)
    return label, final_fit, trace


def _tags(scores: dict[str, Decimal]) -> tuple[tuple[str, ...], tuple[ProfileRuleTraceEntry, ...]]:
    rules: list[tuple[str, str, str]] = []
    rules.append(("T01H", "高风险偏好", f"risk={scores['risk']}≥65") if scores["risk"] >= 65 else ("T01M", "平衡风险偏好", f"risk={scores['risk']}∈[45,65)") if scores["risk"] >= 45 else ("T01L", "稳健风险偏好", f"risk={scores['risk']}<45"))
    rules.append(("T02H", "经验丰富", f"exp={scores['exp']}≥70") if scores["exp"] >= 70 else ("T02M", "有一定经验", f"exp={scores['exp']}∈[42,70)") if scores["exp"] >= 42 else ("T02L", "投资入门", f"exp={scores['exp']}<42"))
    rules.append(("T03H", "主动操作", f"act={scores['act']}≥66") if scores["act"] >= 66 else ("T03L", "低频长线", f"act={scores['act']}<35") if scores["act"] < 35 else ("T03M", "适度活跃", f"act={scores['act']}∈[35,66)"))
    rules.append(("T04R", "深度研究", f"res={scores['res']}≥58") if scores["res"] >= 58 else ("T04I", "信息密集", f"res={scores['res']}<58, inf={scores['inf']}≥60") if scores["inf"] >= 60 else ("T04S", "简洁决策", f"res={scores['res']}<58, inf={scores['inf']}<60"))
    rules.append(("T05H", "AI 协作", f"ai={scores['ai']}≥60") if scores["ai"] >= 60 else ("T05L", "谨慎使用 AI", f"ai={scores['ai']}<40") if scores["ai"] < 40 else ("T05M", "证据优先", f"ai={scores['ai']}∈[40,60)"))
    if scores["per"] >= 52:
        rules.append(("T06", "重视个性化", f"per={scores['per']}≥52"))
    return tuple(label for _, label, _ in rules), tuple(ProfileRuleTraceEntry(rule_id=rule_id, label=label, evidence=(evidence,)) for rule_id, label, evidence in rules)


def _service_strategy(snapshot: QuestionnaireSnapshot, scores: dict[str, Decimal]) -> tuple[tuple[str, ...], tuple[ProfileRuleTraceEntry, ...]]:
    definitions = (
        ("S01", scores["exp"] < 42, "提供基础概念、术语解释和分步引导。", f"exp={scores['exp']}<42"),
        ("S02", scores["aid"] >= 52, "提供检查清单、下一步任务和风险复核。", f"aid={scores['aid']}≥52"),
        ("S03", scores["res"] >= 58, "展示关键依据、数据口径和失效条件。", f"res={scores['res']}≥58"),
        ("S04", scores["inf"] >= 60, "提供信息摘要、来源分组和时间标记。", f"inf={scores['inf']}≥60"),
        ("S05", scores["act"] >= 66, "提供短周期提醒与复盘入口。", f"act={scores['act']}≥66"),
        ("S06", scores["act"] < 35, "采用低频汇总，减少短期波动噪声。", f"act={scores['act']}<35"),
        ("S07", scores["per"] >= 52, "结合持仓、目标、期限和排除偏好。", f"per={scores['per']}≥52"),
        ("S08", scores["ai"] >= 60, "支持追问、观点比较和证据展开。", f"ai={scores['ai']}≥60"),
        ("S09", scores["ai"] < 60, "强化来源、确定性计算口径和人工复核提示。", f"ai={scores['ai']}<60"),
        ("S10", bool({"portfolio", "risk"} & (_selected_ids(snapshot, "Q11") | _selected_ids(snapshot, "Q13"))), "优先提供持仓诊断、风险复核与配置参考。", "Q11/Q13 命中 portfolio 或 risk"),
    )
    matched = tuple((rule_id, label, evidence) for rule_id, condition, label, evidence in definitions if condition)
    return tuple(label for _, label, _ in matched), tuple(ProfileRuleTraceEntry(rule_id=rule_id, label=label, evidence=(evidence,)) for rule_id, label, evidence in matched)


def _feats(snapshot: QuestionnaireSnapshot) -> tuple[tuple[str, ...], ProfileFeatTrace]:
    selected = _selected_order(snapshot, "Q13")
    if not selected:
        return _DEFAULT_FEATS, ProfileFeatTrace(selected_option_ids=(), mappings=tuple(f"default→{item}" for item in _DEFAULT_FEATS), defaulted=True)
    result: list[str] = []
    mappings: list[str] = []
    for option_id in selected:
        feat = _FEAT_MAP[option_id]
        mappings.append(f"{option_id}→{feat}")
        if feat not in result:
            result.append(feat)
        if len(result) == 3:
            break
    return tuple(result), ProfileFeatTrace(selected_option_ids=selected, mappings=tuple(mappings), defaulted=False)


def _legacy_presentation(snapshot: QuestionnaireSnapshot) -> ProfilePresentation:
    scores = {item.key: item.score for item in snapshot.dimensions}
    level = snapshot.suitability_level
    equity_min, equity_max = _LEGACY_EQUITY_RANGES[level]
    return ProfilePresentation(
        schema_version="profile-presentation.v1", ruleset_version=LEGACY_PRESENTATION_RULESET_VERSION,
        suitability_level=level, suitability_label=f"{level.value} · {_RISK_LEVEL_LABELS[snapshot.profile.risk_level]}",
        risk_score=snapshot.risk_score, risk_level=snapshot.profile.risk_level, archetype=_LEGACY_ARCHETYPE_LABELS[level],
        tags=_legacy_tags(snapshot, scores), dimensions=_dimensions(snapshot), key_profile=_key_profile(snapshot),
        service_strategy=_legacy_service_strategy(snapshot, scores), asset_allocation=_allocation(level, legacy=True),
        equity_range=PercentageRange(minimum_pct=equity_min, maximum_pct=equity_max),
        risk_notice="画像结果用于适当性与服务展示参考；资产比例不构成投资建议或交易指令。",
    )


def _current_presentation(snapshot: QuestionnaireSnapshot) -> ProfilePresentation:
    scores = {item.key: item.score for item in snapshot.dimensions}
    level = snapshot.suitability_level
    persona, persona_fit, persona_trace = _persona(snapshot, scores)
    tags, tag_trace = _tags(scores)
    strategy, strategy_trace = _service_strategy(snapshot, scores)
    feats, feat_trace = _feats(snapshot)
    equity_min, equity_max = _EQUITY_RANGES[level]
    allocation_trace = ProfileRuleTraceEntry(rule_id=f"A-{level.value}", label=f"{level.value} {_SUITABILITY_LABELS[level]}", evidence=(f"risk={snapshot.risk_score}",))
    return ProfilePresentation(
        schema_version="profile-presentation.v2", ruleset_version=PRESENTATION_RULESET_VERSION,
        suitability_level=level, suitability_label=f"{level.value} · {_SUITABILITY_LABELS[level]}",
        risk_score=snapshot.risk_score, risk_level=snapshot.profile.risk_level, archetype=persona,
        persona=persona, persona_fit=persona_fit, tags=tags, dimensions=_dimensions(snapshot), key_profile=_key_profile(snapshot),
        service_strategy=strategy, feats=feats,
        rule_trace=ProfileRuleTrace(persona=persona_trace, tags=tag_trace, service_strategy=strategy_trace, feats=feat_trace, allocation=allocation_trace),
        asset_allocation=_allocation(level, legacy=False),
        equity_range=PercentageRange(minimum_pct=equity_min, maximum_pct=equity_max), risk_notice=_RISK_NOTICE,
    )


def build_profile_presentation(snapshot: QuestionnaireSnapshot) -> ProfilePresentation:
    """Build a version-matched result projection without transaction data."""
    if snapshot.ruleset_version == _LEGACY_QUESTIONNAIRE_RULESET_VERSION:
        return _legacy_presentation(snapshot)
    return _current_presentation(snapshot)


__all__ = [
    "LEGACY_PRESENTATION_RULESET_VERSION", "PRESENTATION_RULESET_VERSION", "ProfileAssetAllocation",
    "ProfileFeatTrace", "ProfileKeyFact", "ProfilePersonaTrace", "ProfilePresentation",
    "ProfilePresentationDimension", "ProfileRuleTrace", "ProfileRuleTraceEntry", "build_profile_presentation",
]
