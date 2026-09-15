"""Deterministic presentation projection for the confirmed questionnaire profile.

The questionnaire snapshot remains the source of truth.  This module only
derives the fields needed by the investor-facing result page; it does not read
trades, holdings, or model output.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, Self

from pydantic import Field, model_validator

from app.contracts.evidence import ContractModel, NonEmptyStr
from app.profile.behavior import SuitabilityLevel, suitability_for_score
from app.profile.contracts import PercentageRange, RiskLevel
from app.profile.questionnaire import (
    DIMENSION_KEYS,
    QUESTIONNAIRE_TEMPLATE,
    QuestionnaireSnapshot,
)
from app.profile.scoring import risk_level_for_score


PRESENTATION_RULESET_VERSION = "investor-profile-presentation-rules.v1"
_ALLOCATION_KEYS = ("cash", "bonds", "equity")
_DIMENSION_LABELS = {
    "risk": "风险承受能力",
    "exp": "投资经验",
    "act": "操作活跃度",
    "res": "研究习惯",
    "inf": "信息投入",
    "ai": "AI 信任度",
    "per": "个性化需求",
    "aid": "辅助需求",
}
_DIMENSION_SHORT_LABELS = {
    "risk": "风险承受",
    "exp": "投资经验",
    "act": "操作活跃",
    "res": "研究习惯",
    "inf": "信息投入",
    "ai": "AI 信任",
    "per": "个性需求",
    "aid": "辅助需求",
}
_RISK_LEVEL_LABELS = {
    RiskLevel.CONSERVATIVE: "保守型",
    RiskLevel.BALANCED: "平衡型",
    RiskLevel.GROWTH: "成长型",
}
_ARCHETYPE_LABELS = {
    SuitabilityLevel.C1: "保守稳健型",
    SuitabilityLevel.C2: "谨慎平衡型",
    SuitabilityLevel.C3: "平衡成长型",
    SuitabilityLevel.C4: "稳健成长型",
    SuitabilityLevel.C5: "积极成长型",
}

# C4 is the allocation example shown in the PRD attachment.  The surrounding
# bands are the current deterministic presentation defaults and remain easy to
# replace when the product locks the full C1-C5 allocation table.
_ALLOCATION_RULES: dict[SuitabilityLevel, tuple[tuple[str, str, Decimal], ...]] = {
    SuitabilityLevel.C1: (
        ("cash", "现金", Decimal("50")),
        ("bonds", "债券", Decimal("45")),
        ("equity", "权益", Decimal("5")),
    ),
    SuitabilityLevel.C2: (
        ("cash", "现金", Decimal("30")),
        ("bonds", "债券", Decimal("50")),
        ("equity", "权益", Decimal("20")),
    ),
    SuitabilityLevel.C3: (
        ("cash", "现金", Decimal("20")),
        ("bonds", "债券", Decimal("40")),
        ("equity", "权益", Decimal("40")),
    ),
    SuitabilityLevel.C4: (
        ("cash", "现金", Decimal("10")),
        ("bonds", "债券", Decimal("20")),
        ("equity", "权益", Decimal("70")),
    ),
    SuitabilityLevel.C5: (
        ("cash", "现金", Decimal("5")),
        ("bonds", "债券", Decimal("15")),
        ("equity", "权益", Decimal("80")),
    ),
}
_EQUITY_RANGES = {
    SuitabilityLevel.C1: (Decimal("0"), Decimal("15")),
    SuitabilityLevel.C2: (Decimal("10"), Decimal("30")),
    SuitabilityLevel.C3: (Decimal("30"), Decimal("50")),
    SuitabilityLevel.C4: (Decimal("60"), Decimal("80")),
    SuitabilityLevel.C5: (Decimal("70"), Decimal("90")),
}


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


class ProfilePresentation(ContractModel):
    """Stable, questionnaire-only payload for the profile result view."""

    schema_version: Literal["profile-presentation.v1"] = "profile-presentation.v1"
    ruleset_version: Literal["investor-profile-presentation-rules.v1"] = PRESENTATION_RULESET_VERSION
    suitability_level: SuitabilityLevel
    suitability_label: NonEmptyStr
    risk_score: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    risk_level: RiskLevel
    archetype: NonEmptyStr
    tags: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=6)
    dimensions: tuple[ProfilePresentationDimension, ...] = Field(min_length=8, max_length=8)
    key_profile: tuple[ProfileKeyFact, ...] = Field(min_length=6, max_length=6)
    service_strategy: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=4)
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
        return self


def _answer_map(snapshot: QuestionnaireSnapshot):
    return {answer.question_id: answer for answer in snapshot.answers}


def _question_map():
    return {question.question_id: question for question in QUESTIONNAIRE_TEMPLATE.questions}


def _selected_ids(snapshot: QuestionnaireSnapshot, question_id: str) -> set[str]:
    answer = _answer_map(snapshot)[question_id]
    return set(answer.selected_option_ids)


def _answer_labels(snapshot: QuestionnaireSnapshot, question_id: str) -> tuple[str, ...]:
    answers = _answer_map(snapshot)
    questions = _question_map()
    answer = answers[question_id]
    if answer.score is not None:
        return (f"{answer.score} / 5",)
    labels = {option.option_id: option.label for option in questions[question_id].options}
    return tuple(labels[item] for item in answer.selected_option_ids if item in labels)


def _experience_label(snapshot: QuestionnaireSnapshot) -> str:
    option_id = next(iter(_selected_ids(snapshot, "Q2")))
    return {
        "lt_1y": "不足 1 年",
        "y1_3": "1–3 年",
        "y3_5": "3–5 年",
        "y5_10": "5+ 年",
        "gt_10y": "10+ 年",
    }.get(option_id, _answer_labels(snapshot, "Q2")[0])


def _tag_values(snapshot: QuestionnaireSnapshot, dimensions: dict[str, Decimal]) -> tuple[str, ...]:
    risk_tag = (
        "高风险偏好"
        if dimensions["risk"] >= Decimal("65")
        else "平衡风险偏好"
        if dimensions["risk"] >= Decimal("45")
        else "稳健风险偏好"
    )
    experience_tag = (
        "经验丰富"
        if dimensions["exp"] >= Decimal("70")
        else "有一定经验"
        if dimensions["exp"] >= Decimal("40")
        else "投资入门"
    )
    ai_tag = (
        "愿意参考 AI"
        if dimensions["ai"] >= Decimal("70")
        else "谨慎使用 AI"
        if dimensions["ai"] < Decimal("50")
        else "审慎参考 AI"
    )
    pain_ids = _selected_ids(snapshot, "Q11")
    pain_count = len(pain_ids - {"none"})
    pain_tag = "多项研究痛点" if pain_count >= 3 else "有研究痛点" if pain_count else "研究路径清晰"
    return (risk_tag, experience_tag, ai_tag, pain_tag)


def _service_strategy(snapshot: QuestionnaireSnapshot, dimensions: dict[str, Decimal]) -> tuple[str, ...]:
    scenes = _selected_ids(snapshot, "Q13")
    strategy: list[str] = []
    if {"portfolio", "risk"} & scenes or dimensions["aid"] >= Decimal("60"):
        strategy.append("优先提供持仓诊断、组合风险复核与资产配置参考。")
    elif {"industry", "fund"} & scenes:
        strategy.append("优先提供行业配置、ETF 筛选与风险边界说明。")
    else:
        strategy.append("优先提供市场信息整理、研究框架与风险提示。")

    if dimensions["res"] >= Decimal("60") or dimensions["inf"] >= Decimal("60"):
        strategy.append("结论同步展示关键依据、数据口径和失效条件。")
    else:
        strategy.append("采用简洁分步说明，必要时展开数据依据。")

    if dimensions["ai"] < Decimal("50"):
        strategy.append("AI 结论默认保留来源、计算口径和人工复核提示。")
    else:
        strategy.append("AI 结论保留证据入口，支持继续追问和比较观点。")
    return tuple(strategy)


def build_profile_presentation(snapshot: QuestionnaireSnapshot) -> ProfilePresentation:
    """Build a complete result projection without any transaction dependency."""
    dimensions = {item.key: item.score for item in snapshot.dimensions}
    profile = snapshot.profile
    key_profile = (
        ProfileKeyFact(key="experience", label="投资经验", value=_experience_label(snapshot)),
        ProfileKeyFact(key="funds", label="可投资资金", value=_answer_labels(snapshot, "Q4")[0]),
        ProfileKeyFact(key="rebalance", label="调仓频率", value=_answer_labels(snapshot, "Q5")[0]),
        ProfileKeyFact(key="research_time", label="每日研究时间", value=_answer_labels(snapshot, "Q9")[0]),
        ProfileKeyFact(key="product_count", label="接触产品数", value=f"{len(_selected_ids(snapshot, 'Q3'))} 类"),
        ProfileKeyFact(key="ai_reference", label="AI 参考程度", value=_answer_labels(snapshot, "Q17")[0]),
    )
    level = snapshot.suitability_level
    allocation = tuple(
        ProfileAssetAllocation(key=key, label=label, target_pct=target)
        for key, label, target in _ALLOCATION_RULES[level]
    )
    equity_min, equity_max = _EQUITY_RANGES[level]
    return ProfilePresentation(
        suitability_level=level,
        suitability_label=f"{level.value} · {_RISK_LEVEL_LABELS[profile.risk_level]}",
        risk_score=snapshot.risk_score,
        risk_level=profile.risk_level,
        archetype=_ARCHETYPE_LABELS[level],
        tags=_tag_values(snapshot, dimensions),
        dimensions=tuple(
            ProfilePresentationDimension(
                key=item.key,
                label=_DIMENSION_LABELS[item.key],
                short_label=_DIMENSION_SHORT_LABELS[item.key],
                score=item.score,
            )
            for item in snapshot.dimensions
        ),
        key_profile=key_profile,
        service_strategy=_service_strategy(snapshot, dimensions),
        asset_allocation=allocation,
        equity_range=PercentageRange(minimum_pct=equity_min, maximum_pct=equity_max),
        risk_notice="画像结果用于适当性与服务展示参考；资产比例不构成投资建议或交易指令。",
    )


__all__ = [
    "PRESENTATION_RULESET_VERSION",
    "ProfileAssetAllocation",
    "ProfileKeyFact",
    "ProfilePresentation",
    "ProfilePresentationDimension",
    "build_profile_presentation",
]
