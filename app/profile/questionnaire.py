"""Versioned 19-question investor questionnaire and deterministic scoring."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum
from hashlib import sha256
import json
from typing import Literal, Self

from pydantic import Field, model_validator

from app.contracts.evidence import ContractModel, NonEmptyStr
from app.profile.behavior import SuitabilityLevel, suitability_for_score
from app.profile.contracts import (
    ExperienceLevel,
    InvestmentHorizon,
    LiquidityNeed,
    PercentageRange,
    ReturnExpectation,
    RiskProfile,
    RiskQuestionnaire,
)
from app.profile.scoring import risk_level_for_score


QUESTIONNAIRE_VERSION = "investor-questionnaire.v1"
QUESTIONNAIRE_RULESET_VERSION = "investor-questionnaire-rules.v1"
DIMENSION_KEYS = ("risk", "exp", "act", "res", "inf", "ai", "per", "aid")


class QuestionnaireQuestionType(StrEnum):
    SINGLE = "SINGLE"
    MULTI = "MULTI"
    SCORE = "SCORE"


class QuestionnaireDimensionWeight(ContractModel):
    dimension: Literal["risk", "exp", "act", "res", "inf", "ai", "per", "aid"]
    weight: Decimal = Field(ge=Decimal("-1"), le=Decimal("1"))


class QuestionnaireOption(ContractModel):
    option_id: NonEmptyStr
    label: NonEmptyStr
    weights: tuple[QuestionnaireDimensionWeight, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_weights(self) -> Self:
        keys = [item.dimension for item in self.weights]
        if len(keys) != len(set(keys)):
            raise ValueError("questionnaire option dimensions must be unique")
        return self


class QuestionnaireQuestion(ContractModel):
    question_id: NonEmptyStr
    section_id: NonEmptyStr
    prompt: NonEmptyStr
    question_type: QuestionnaireQuestionType
    options: tuple[QuestionnaireOption, ...] = Field(default_factory=tuple)
    score_weights: tuple[QuestionnaireDimensionWeight, ...] = Field(default_factory=tuple)
    minimum_score: int | None = Field(default=None, ge=1, le=5)
    maximum_score: int | None = Field(default=None, ge=1, le=5)

    @model_validator(mode="after")
    def validate_question(self) -> Self:
        option_ids = [item.option_id for item in self.options]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("questionnaire option IDs must be unique")
        if self.question_type == QuestionnaireQuestionType.SCORE:
            if self.options or not self.score_weights:
                raise ValueError("score question requires score weights and no options")
            if self.minimum_score != 1 or self.maximum_score != 5:
                raise ValueError("score question range must be 1 through 5")
        elif not self.options or self.score_weights or self.minimum_score is not None or self.maximum_score is not None:
            raise ValueError("choice question requires options only")
        return self


class QuestionnaireSection(ContractModel):
    section_id: NonEmptyStr
    title: NonEmptyStr
    description: NonEmptyStr
    question_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)


class QuestionnaireTemplate(ContractModel):
    schema_version: Literal["questionnaire-template.v1"] = "questionnaire-template.v1"
    questionnaire_version: Literal["investor-questionnaire.v1"] = QUESTIONNAIRE_VERSION
    ruleset_version: Literal["investor-questionnaire-rules.v1"] = QUESTIONNAIRE_RULESET_VERSION
    sections: tuple[QuestionnaireSection, ...] = Field(min_length=6, max_length=6)
    questions: tuple[QuestionnaireQuestion, ...] = Field(min_length=19, max_length=19)

    @model_validator(mode="after")
    def validate_template(self) -> Self:
        question_ids = [item.question_id for item in self.questions]
        if question_ids != [f"Q{index}" for index in range(1, 20)]:
            raise ValueError("questionnaire template must contain Q1 through Q19 in order")
        section_ids = [item.section_id for item in self.sections]
        if len(section_ids) != len(set(section_ids)):
            raise ValueError("questionnaire section IDs must be unique")
        linked = tuple(question_id for section in self.sections for question_id in section.question_ids)
        if linked != tuple(question_ids):
            raise ValueError("questionnaire sections must cover every question once in order")
        return self


class QuestionnaireAnswer(ContractModel):
    question_id: NonEmptyStr
    selected_option_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    score: int | None = Field(default=None, ge=1, le=5)

    @model_validator(mode="after")
    def validate_shape(self) -> Self:
        if len(self.selected_option_ids) != len(set(self.selected_option_ids)):
            raise ValueError("selected questionnaire options must be unique")
        if bool(self.selected_option_ids) == (self.score is not None):
            raise ValueError("questionnaire answer requires choices or a score, not both")
        return self


class QuestionnaireDimensionScore(ContractModel):
    key: Literal["risk", "exp", "act", "res", "inf", "ai", "per", "aid"]
    score: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))


class QuestionnaireSnapshot(ContractModel):
    schema_version: Literal["questionnaire-snapshot.v1"] = "questionnaire-snapshot.v1"
    snapshot_id: NonEmptyStr
    owner_id: NonEmptyStr
    snapshot_version: int = Field(ge=1)
    questionnaire_version: Literal["investor-questionnaire.v1"] = QUESTIONNAIRE_VERSION
    ruleset_version: Literal["investor-questionnaire-rules.v1"] = QUESTIONNAIRE_RULESET_VERSION
    confirmed_at: datetime
    answers: tuple[QuestionnaireAnswer, ...] = Field(min_length=19, max_length=19)
    dimensions: tuple[QuestionnaireDimensionScore, ...] = Field(min_length=8, max_length=8)
    suitability_level: SuitabilityLevel
    risk_score: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    questionnaire: RiskQuestionnaire
    profile: RiskProfile

    @model_validator(mode="after")
    def validate_snapshot(self) -> Self:
        if self.confirmed_at.tzinfo is None or self.confirmed_at.utcoffset() is None:
            raise ValueError("confirmed_at must be timezone-aware")
        if self.questionnaire.owner_id != self.owner_id or self.profile.owner_id != self.owner_id:
            raise ValueError("questionnaire snapshot owners must match")
        if self.questionnaire.questionnaire_id != self.profile.questionnaire_id:
            raise ValueError("questionnaire snapshot profile must reference questionnaire")
        if self.questionnaire.answered_at != self.confirmed_at or self.profile.created_at != self.confirmed_at:
            raise ValueError("questionnaire snapshot timestamps must match")
        keys = [item.key for item in self.dimensions]
        if tuple(keys) != DIMENSION_KEYS:
            raise ValueError("questionnaire snapshot requires the ordered eight dimensions")
        risk_dimension = next(item.score for item in self.dimensions if item.key == "risk")
        if risk_dimension != self.risk_score or self.profile.risk_score != self.risk_score:
            raise ValueError("questionnaire risk scores must match")
        if suitability_for_score(self.risk_score) != self.suitability_level:
            raise ValueError("questionnaire suitability does not match risk score")
        return self


def _w(**weights: str) -> tuple[QuestionnaireDimensionWeight, ...]:
    return tuple(
        QuestionnaireDimensionWeight(dimension=dimension, weight=Decimal(value))
        for dimension, value in weights.items()
    )


def _o(option_id: str, label: str, **weights: str) -> QuestionnaireOption:
    return QuestionnaireOption(option_id=option_id, label=label, weights=_w(**weights))


QUESTIONS = (
    QuestionnaireQuestion(question_id="Q1", section_id="basic", prompt="你目前的投资状态是？", question_type="SINGLE", options=(
        _o("not_started", "尚未开始投资", exp="0"), _o("learning", "正在学习和观察", exp="0.20", aid="0.45"),
        _o("active", "已有持续投资", exp="0.65"), _o("professional", "具备专业投资或研究经历", exp="1", res="0.70"))),
    QuestionnaireQuestion(question_id="Q2", section_id="basic", prompt="你接触投资多长时间？", question_type="SINGLE", options=(
        _o("lt_1y", "不足 1 年", exp="0.15"), _o("y1_3", "1 至 3 年", exp="0.40"), _o("y3_5", "3 至 5 年", exp="0.65"),
        _o("y5_10", "5 至 10 年", exp="0.85"), _o("gt_10y", "10 年以上", exp="1"))),
    QuestionnaireQuestion(question_id="Q3", section_id="basic", prompt="你主要投资过哪些产品？", question_type="MULTI", options=(
        _o("cash", "存款或货币基金", exp="0.10", risk="0.05"), _o("bond", "债券或固收产品", exp="0.30", risk="0.20"),
        _o("fund", "公募基金或 ETF", exp="0.45", risk="0.40"), _o("stock", "股票", exp="0.65", risk="0.70"),
        _o("convertible", "可转债", exp="0.70", risk="0.65"), _o("derivative", "期权、期货等衍生品", exp="1", risk="0.95"))),
    QuestionnaireQuestion(question_id="Q4", section_id="basic", prompt="可用于投资且短期无需动用的资金规模是？", question_type="SINGLE", options=(
        _o("lt_50k", "5 万元以下", risk="0.15"), _o("k50_200", "5 万至 20 万元", risk="0.35"),
        _o("k200_500", "20 万至 50 万元", risk="0.55"), _o("k500_1000", "50 万至 100 万元", risk="0.75"),
        _o("gt_1m", "100 万元以上", risk="0.90"))),
    QuestionnaireQuestion(question_id="Q5", section_id="basic", prompt="你通常多久进行一次调仓或交易决策？", question_type="SINGLE", options=(
        _o("yearly", "每年数次或更少", act="0.10"), _o("monthly", "每月数次", act="0.35"), _o("weekly", "每周数次", act="0.65"),
        _o("daily", "几乎每天", act="0.85"), _o("intraday", "日内多次", act="1"))),
    QuestionnaireQuestion(question_id="Q6", section_id="basic", prompt="你最主要的投资目标是？", question_type="MULTI", options=(
        _o("preserve", "尽量保住本金", risk="0.10"), _o("income", "获取稳定现金流", risk="0.30", per="0.35"),
        _o("balanced_growth", "长期稳健增值", risk="0.55"), _o("capital_growth", "追求较高资本增值", risk="0.80"),
        _o("aggressive", "接受较大波动以争取高收益", risk="1"), _o("pension", "养老或长期专项资金", per="0.80", risk="0.25"),
        _o("education", "教育等明确用途资金", per="0.75", risk="0.30"))),
    QuestionnaireQuestion(question_id="Q7", section_id="decision", prompt="开始一项新投资前，你通常会做什么？", question_type="MULTI", options=(
        _o("fundamental", "研究财务和基本面", res="0.85", inf="0.55"), _o("market_data", "查看行情和量化指标", res="0.65", inf="0.70"),
        _o("reports", "阅读研报和公告", res="0.70", inf="0.85"), _o("discuss", "参考社区或熟人意见", inf="0.40"),
        _o("ai", "使用 AI 工具辅助分析", ai="0.65", inf="0.45"), _o("follow", "直接跟随他人建议", res="0.05", ai="0.25"))),
    QuestionnaireQuestion(question_id="Q8", section_id="decision", prompt="作出重要投资决策通常需要多长时间？", question_type="SINGLE", options=(
        _o("minutes", "几分钟内", res="0.10", act="0.90"), _o("hours", "数小时", res="0.35", act="0.65"),
        _o("days", "一至数天", res="0.70", act="0.35"), _o("weeks", "一周以上", res="0.95", act="0.10"))),
    QuestionnaireQuestion(question_id="Q9", section_id="decision", prompt="你每天通常投入多少时间进行投资研究？", question_type="SINGLE", options=(
        _o("lt_15m", "不足 15 分钟", inf="0.10", act="0.10"), _o("m15_60", "15 分钟至 1 小时", inf="0.40", act="0.35"),
        _o("h1_2", "1 至 2 小时", inf="0.70", act="0.60"), _o("gt_2h", "2 小时以上", inf="1", act="0.90"))),
    QuestionnaireQuestion(question_id="Q10", section_id="decision", prompt="投资后你通常会采取哪些行为？", question_type="MULTI", options=(
        _o("regular_review", "定期复盘基本面", res="0.85", inf="0.60"), _o("price_alert", "设置价格或风险提醒", act="0.65", inf="0.45"),
        _o("frequent_adjust", "根据波动频繁调整", act="0.95"), _o("long_hold", "按长期计划持有", res="0.60", act="0.10"),
        _o("news_follow", "持续跟踪新闻和公告", inf="0.90", act="0.45"), _o("no_review", "很少复盘", res="0.05", inf="0.05"))),
    QuestionnaireQuestion(question_id="Q11", section_id="pain", prompt="你在投资中经常遇到哪些困难？", question_type="MULTI", options=(
        _o("information", "信息过多，难以筛选", aid="0.60"), _o("valuation", "不会判断估值和买卖时机", aid="0.80"),
        _o("portfolio", "缺少组合和仓位管理方法", aid="0.85", per="0.45"), _o("risk", "难以识别或控制风险", aid="0.90"),
        _o("discipline", "容易受情绪影响", aid="0.75"), _o("none", "暂未遇到明显困难", aid="0"))),
    QuestionnaireQuestion(question_id="Q12", section_id="pain", prompt="这些困难对你作出投资决策的影响有多大？", question_type="SCORE", score_weights=_w(aid="1"), minimum_score=1, maximum_score=5),
    QuestionnaireQuestion(question_id="Q13", section_id="scenes", prompt="你希望系统重点帮助哪些场景？", question_type="MULTI", options=(
        _o("market", "大盘和市场走势", aid="0.45"), _o("industry", "行业和板块配置", aid="0.55", per="0.30"),
        _o("stock", "个股分析", aid="0.60"), _o("fund", "ETF 或基金筛选", aid="0.55"), _o("bond", "可转债分析", aid="0.50"),
        _o("portfolio", "持仓诊断和组合优化", aid="0.85", per="0.80"), _o("risk", "投资风险分析", aid="0.80", per="0.55"))),
    QuestionnaireQuestion(question_id="Q14", section_id="personal", prompt="投资分析是否需要结合你的个人情况？", question_type="SINGLE", options=(
        _o("no", "不需要，通用信息即可", per="0.10"), _o("sometimes", "重要决策时需要", per="0.55"), _o("always", "所有分析都应结合个人情况", per="1"))),
    QuestionnaireQuestion(question_id="Q15", section_id="personal", prompt="系统应重点考虑哪些个人因素？", question_type="MULTI", options=(
        _o("holdings", "当前持仓和成本", per="0.85"), _o("cashflow", "收入、现金流和流动性", per="0.70"),
        _o("risk_level", "风险承受能力", per="0.80"), _o("goals", "投资目标和期限", per="0.75"),
        _o("preferences", "行业、品种和排除偏好", per="0.65"), _o("history", "历史交易和操作习惯", per="0.90"))),
    QuestionnaireQuestion(question_id="Q16", section_id="ai", prompt="你使用 AI 投资工具的经历是？", question_type="SINGLE", options=(
        _o("never", "从未使用", ai="0.05"), _o("tried", "偶尔尝试", ai="0.35"), _o("regular", "经常用于辅助分析", ai="0.70"),
        _o("workflow", "已纳入日常决策流程", ai="0.95"))),
    QuestionnaireQuestion(question_id="Q17", section_id="ai", prompt="你愿意在多大程度上参考 AI 的分析？", question_type="SCORE", score_weights=_w(ai="1"), minimum_score=1, maximum_score=5),
    QuestionnaireQuestion(question_id="Q18", section_id="ai", prompt="当 AI 分析与你的判断不一致时，你通常会？", question_type="SINGLE", options=(
        _o("ignore", "直接忽略 AI", ai="0.05", res="0.55"), _o("check", "核对证据后自行决定", ai="0.55", res="0.90"),
        _o("discuss", "继续追问并比较观点", ai="0.75", res="0.70"), _o("follow", "通常采纳 AI 结论", ai="0.95", res="0.15"))),
    QuestionnaireQuestion(question_id="Q19", section_id="ai", prompt="你对 AI 投资分析的主要担忧是？", question_type="MULTI", options=(
        _o("accuracy", "信息或结论不准确", ai="-0.35"), _o("explainability", "无法解释判断依据", ai="-0.25"),
        _o("privacy", "个人数据和隐私风险", ai="-0.25"), _o("dependency", "过度依赖影响独立判断", ai="-0.20"),
        _o("compliance", "建议可能越过合规边界", ai="-0.20"), _o("none", "暂无明显担忧", ai="0.50"))),
)


QUESTIONNAIRE_TEMPLATE = QuestionnaireTemplate(
    sections=(
        QuestionnaireSection(section_id="basic", title="投资基本情况", description="了解投资经验、资金和目标。", question_ids=("Q1", "Q2", "Q3", "Q4", "Q5", "Q6")),
        QuestionnaireSection(section_id="decision", title="投资决策方式", description="了解研究投入和操作习惯。", question_ids=("Q7", "Q8", "Q9", "Q10")),
        QuestionnaireSection(section_id="pain", title="投资痛点", description="了解当前决策困难。", question_ids=("Q11", "Q12")),
        QuestionnaireSection(section_id="scenes", title="高频场景", description="确定优先提供的分析能力。", question_ids=("Q13",)),
        QuestionnaireSection(section_id="personal", title="个性化需求", description="确认分析需要结合的个人条件。", question_ids=("Q14", "Q15")),
        QuestionnaireSection(section_id="ai", title="AI 辅助与信任", description="决定解释深度，不改变风险等级。", question_ids=("Q16", "Q17", "Q18", "Q19")),
    ),
    questions=QUESTIONS,
)


def validate_answers(answers: tuple[QuestionnaireAnswer, ...]) -> tuple[QuestionnaireAnswer, ...]:
    if len(answers) != 19:
        raise ValueError("all 19 questionnaire answers are required")
    by_id = {answer.question_id: answer for answer in answers}
    if len(by_id) != len(answers):
        raise ValueError("questionnaire answers must not contain duplicate question IDs")
    expected = {question.question_id for question in QUESTIONNAIRE_TEMPLATE.questions}
    if set(by_id) != expected:
        raise ValueError("questionnaire answers must contain Q1 through Q19")
    normalized: list[QuestionnaireAnswer] = []
    for question in QUESTIONNAIRE_TEMPLATE.questions:
        answer = by_id[question.question_id]
        if question.question_type == QuestionnaireQuestionType.SCORE:
            if answer.score is None or answer.selected_option_ids:
                raise ValueError(f"{question.question_id} requires a score")
        else:
            if answer.score is not None or not answer.selected_option_ids:
                raise ValueError(f"{question.question_id} requires option selections")
            if question.question_type == QuestionnaireQuestionType.SINGLE and len(answer.selected_option_ids) != 1:
                raise ValueError(f"{question.question_id} requires exactly one option")
            allowed = {option.option_id for option in question.options}
            if not set(answer.selected_option_ids).issubset(allowed):
                raise ValueError(f"{question.question_id} contains an invalid option")
            if "none" in answer.selected_option_ids and len(answer.selected_option_ids) > 1:
                raise ValueError(f"{question.question_id} none option is exclusive")
        normalized.append(answer)
    return tuple(normalized)


def score_answers(answers: tuple[QuestionnaireAnswer, ...]) -> tuple[QuestionnaireDimensionScore, ...]:
    normalized = validate_answers(answers)
    by_id = {answer.question_id: answer for answer in normalized}
    accumulated = {key: Decimal("0") for key in DIMENSION_KEYS}
    measured = {key: 0 for key in DIMENSION_KEYS}
    for question in QUESTIONNAIRE_TEMPLATE.questions:
        answer = by_id[question.question_id]
        measurable = {
            item.dimension
            for option in question.options
            for item in option.weights
        } | {item.dimension for item in question.score_weights}
        for dimension in measurable:
            measured[dimension] += 1
        if question.question_type == QuestionnaireQuestionType.SCORE:
            factor = (Decimal(answer.score or 1) - Decimal("1")) / Decimal("4")
            contribution = {item.dimension: factor * item.weight for item in question.score_weights}
        else:
            selected = {item for item in answer.selected_option_ids}
            contribution: dict[str, Decimal] = {}
            for option in question.options:
                if option.option_id not in selected:
                    continue
                for item in option.weights:
                    contribution[item.dimension] = contribution.get(item.dimension, Decimal("0")) + item.weight
            contribution = {
                key: max(Decimal("-1"), min(Decimal("1"), value))
                for key, value in contribution.items()
            }
        for dimension, value in contribution.items():
            accumulated[dimension] += value
    scores = []
    for key in DIMENSION_KEYS:
        denominator = Decimal(measured[key] or 1)
        normalized_score = max(Decimal("0"), min(Decimal("1"), accumulated[key] / denominator))
        scores.append(QuestionnaireDimensionScore(
            key=key,
            score=(normalized_score * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        ))
    return tuple(scores)


def _single_choice(answers: tuple[QuestionnaireAnswer, ...], question_id: str) -> str:
    answer = next(item for item in answers if item.question_id == question_id)
    return answer.selected_option_ids[0]


def _legacy_questionnaire(
    owner_id: str,
    questionnaire_id: str,
    confirmed_at: datetime,
    answers: tuple[QuestionnaireAnswer, ...],
    dimensions: tuple[QuestionnaireDimensionScore, ...],
) -> RiskQuestionnaire:
    scores = {item.key: item.score for item in dimensions}
    risk = scores["risk"]
    suitability = suitability_for_score(risk)
    loss_score = {SuitabilityLevel.C1: 1, SuitabilityLevel.C2: 2, SuitabilityLevel.C3: 3, SuitabilityLevel.C4: 4, SuitabilityLevel.C5: 5}[suitability]
    goal_choices = next(item for item in answers if item.question_id == "Q6").selected_option_ids
    horizon = InvestmentHorizon.LONG if {"pension", "education"} & set(goal_choices) else InvestmentHorizon.SHORT if "aggressive" in goal_choices else InvestmentHorizon.MEDIUM
    asset_band = _single_choice(answers, "Q4")
    liquidity = LiquidityNeed.HIGH if asset_band == "lt_50k" else LiquidityNeed.LOW if asset_band in {"k500_1000", "gt_1m"} else LiquidityNeed.MEDIUM
    experience = ExperienceLevel.NOVICE if scores["exp"] < 40 else ExperienceLevel.INTERMEDIATE if scores["exp"] < 70 else ExperienceLevel.EXPERIENCED
    return_expectation = ReturnExpectation.LOW if risk < 35 else ReturnExpectation.MODERATE if risk < 70 else ReturnExpectation.HIGH
    max_drawdown = {SuitabilityLevel.C1: "3", SuitabilityLevel.C2: "8", SuitabilityLevel.C3: "15", SuitabilityLevel.C4: "25", SuitabilityLevel.C5: "35"}[suitability]
    expected = {SuitabilityLevel.C1: ("0", "4"), SuitabilityLevel.C2: ("2", "7"), SuitabilityLevel.C3: ("4", "12"), SuitabilityLevel.C4: ("6", "18"), SuitabilityLevel.C5: ("8", "25")}[suitability]
    return RiskQuestionnaire(
        questionnaire_id=questionnaire_id,
        owner_id=owner_id,
        answered_at=confirmed_at,
        loss_tolerance_score=loss_score,
        investment_horizon=horizon,
        liquidity_need=liquidity,
        experience_level=experience,
        return_expectation=return_expectation,
        max_drawdown_tolerance_pct=Decimal(max_drawdown),
        expected_return_range=PercentageRange(minimum_pct=Decimal(expected[0]), maximum_pct=Decimal(expected[1])),
    )


def build_questionnaire_snapshot(
    owner_id: str,
    answers: tuple[QuestionnaireAnswer, ...],
    *,
    confirmed_at: datetime,
    snapshot_version: int,
) -> QuestionnaireSnapshot:
    if confirmed_at.tzinfo is None or confirmed_at.utcoffset() is None:
        raise ValueError("confirmed_at must be timezone-aware")
    normalized = validate_answers(answers)
    dimensions = score_answers(normalized)
    risk_score = next(item.score for item in dimensions if item.key == "risk")
    identity = json.dumps(
        {
            "owner_id": owner_id,
            "version": snapshot_version,
            "ruleset": QUESTIONNAIRE_RULESET_VERSION,
            "confirmed_at": confirmed_at.isoformat(),
            "answers": [item.model_dump(mode="json") for item in normalized],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = sha256(identity).hexdigest()
    snapshot_id = f"questionnaire-snapshot:{digest[:32]}"
    questionnaire_id = f"questionnaire-full:{digest[:32]}"
    questionnaire = _legacy_questionnaire(owner_id, questionnaire_id, confirmed_at, normalized, dimensions)
    profile = RiskProfile(
        profile_id=f"profile-full:{digest[:32]}",
        owner_id=owner_id,
        profile_version=snapshot_version,
        questionnaire_id=questionnaire_id,
        created_at=confirmed_at,
        risk_score=risk_score,
        risk_level=risk_level_for_score(risk_score),
        investment_horizon=questionnaire.investment_horizon,
        liquidity_need=questionnaire.liquidity_need,
        experience_level=questionnaire.experience_level,
        return_expectation=questionnaire.return_expectation,
        max_drawdown_tolerance_pct=questionnaire.max_drawdown_tolerance_pct,
        expected_return_range=questionnaire.expected_return_range,
        confidence=Decimal("1"),
    )
    return QuestionnaireSnapshot(
        snapshot_id=snapshot_id,
        owner_id=owner_id,
        snapshot_version=snapshot_version,
        confirmed_at=confirmed_at,
        answers=normalized,
        dimensions=dimensions,
        suitability_level=suitability_for_score(risk_score),
        risk_score=risk_score,
        questionnaire=questionnaire,
        profile=profile,
    )


__all__ = [
    "DIMENSION_KEYS",
    "QUESTIONNAIRE_RULESET_VERSION",
    "QUESTIONNAIRE_TEMPLATE",
    "QUESTIONNAIRE_VERSION",
    "QuestionnaireAnswer",
    "QuestionnaireDimensionScore",
    "QuestionnaireOption",
    "QuestionnaireQuestion",
    "QuestionnaireQuestionType",
    "QuestionnaireSection",
    "QuestionnaireSnapshot",
    "QuestionnaireTemplate",
    "build_questionnaire_snapshot",
    "score_answers",
    "validate_answers",
]
