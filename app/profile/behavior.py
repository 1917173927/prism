"""Deterministic behaviour-backed investor profile contracts and calculation."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum
from hashlib import sha256
import json
from statistics import median
from typing import Literal, Self

from pydantic import Field, model_validator

from app.contracts.evidence import ContractModel, NonEmptyStr
from app.portfolio import AssetType, PortfolioImportBundle
from app.profile.contracts import ExperienceLevel, RiskLevel, RiskProfile
from app.profile.scoring import risk_level_for_score


RULESET_VERSION = "behavior-profile-rules.v1"
SUITABILITY_SCORE_BANDS: tuple[tuple[Decimal, Decimal, "SuitabilityLevel"], ...]
DISPLAY_POLICY_THRESHOLDS = {"audit_expanded_max": 34, "conclusion_first_min": 65}


class BehaviorEventType(StrEnum):
    TRADE = "TRADE"
    POSITION_SNAPSHOT = "POSITION_SNAPSHOT"


class TradeSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class BehaviorEvidenceStatus(StrEnum):
    CALCULATED = "CALCULATED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class DimensionSource(StrEnum):
    CALCULATED = "CALCULATED"
    QUESTIONNAIRE = "QUESTIONNAIRE"
    EXPLICIT = "EXPLICIT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class SuitabilityLevel(StrEnum):
    C1 = "C1"
    C2 = "C2"
    C3 = "C3"
    C4 = "C4"
    C5 = "C5"


SUITABILITY_SCORE_BANDS = (
    (Decimal("0"), Decimal("24"), SuitabilityLevel.C1),
    (Decimal("25"), Decimal("44"), SuitabilityLevel.C2),
    (Decimal("45"), Decimal("64"), SuitabilityLevel.C3),
    (Decimal("65"), Decimal("81"), SuitabilityLevel.C4),
    (Decimal("82"), Decimal("100"), SuitabilityLevel.C5),
)


class DisplayMode(StrEnum):
    AUDIT_EXPANDED = "AUDIT_EXPANDED"
    STANDARD = "STANDARD"
    CONCLUSION_FIRST = "CONCLUSION_FIRST"


class DisplayPolicySource(StrEnum):
    DEFAULT = "DEFAULT"
    QUESTIONNAIRE = "QUESTIONNAIRE"
    EXPLICIT = "EXPLICIT"


class BehaviorEvent(ContractModel):
    """One append-only trade or aggregate position-snapshot observation."""

    schema_version: Literal["behavior-event.v1"] = "behavior-event.v1"
    event_id: NonEmptyStr
    owner_id: NonEmptyStr
    event_type: BehaviorEventType
    occurred_at: datetime
    source: NonEmptyStr
    asset_id: NonEmptyStr | None = None
    asset_type: AssetType | None = None
    sector: NonEmptyStr | None = None
    side: TradeSide | None = None
    quantity: Decimal | None = Field(default=None, gt=0)
    price_cny: Decimal | None = Field(default=None, gt=0)
    portfolio_value_cny: Decimal | None = Field(default=None, gt=0)
    equity_weight_pct: Decimal | None = Field(default=None, ge=0, le=100)
    max_position_weight_pct: Decimal | None = Field(default=None, ge=0, le=100)
    max_sector_weight_pct: Decimal | None = Field(default=None, ge=0, le=100)
    drawdown_pct: Decimal | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def validate_event(self) -> Self:
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        trade_fields = (self.asset_id, self.asset_type, self.side, self.quantity, self.price_cny)
        if self.event_type == BehaviorEventType.TRADE:
            if any(value is None for value in trade_fields):
                raise ValueError("TRADE requires asset, side, quantity and price")
        elif any(value is not None for value in (self.side, self.quantity, self.price_cny)):
            raise ValueError("POSITION_SNAPSHOT must not contain trade fields")
        if self.event_type == BehaviorEventType.POSITION_SNAPSHOT and (
            self.portfolio_value_cny is None
            or self.equity_weight_pct is None
            or self.max_position_weight_pct is None
            or self.max_sector_weight_pct is None
        ):
            raise ValueError("POSITION_SNAPSHOT requires portfolio and concentration metrics")
        return self


class BehaviorEvidence(ContractModel):
    evidence_id: NonEmptyStr
    metric: NonEmptyStr
    value: Decimal
    unit: NonEmptyStr
    observed_at: datetime
    source_event_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_evidence(self) -> Self:
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        if len(set(self.source_event_ids)) != len(self.source_event_ids):
            raise ValueError("source_event_ids must be unique")
        return self


class BehaviorDimension(ContractModel):
    key: Literal["risk", "exp", "act", "res", "inf", "ai", "per", "aid"]
    score: Decimal | None = Field(default=None, ge=0, le=100)
    source: DimensionSource

    @model_validator(mode="after")
    def validate_score(self) -> Self:
        if self.source == DimensionSource.INSUFFICIENT_DATA and self.score is not None:
            raise ValueError("insufficient dimension must not contain a score")
        if self.source != DimensionSource.INSUFFICIENT_DATA and self.score is None:
            raise ValueError("calculated dimension requires a score")
        return self


class DisplayPolicy(ContractModel):
    schema_version: Literal["display-policy.v1"] = "display-policy.v1"
    owner_id: NonEmptyStr
    trust_score: int = Field(ge=0, le=100)
    mode: DisplayMode
    source: DisplayPolicySource
    updated_at: datetime

    @model_validator(mode="after")
    def validate_policy(self) -> Self:
        if self.updated_at.tzinfo is None or self.updated_at.utcoffset() is None:
            raise ValueError("updated_at must be timezone-aware")
        if self.mode != display_mode_for_trust(self.trust_score):
            raise ValueError("display mode does not match trust score")
        return self


class BehaviorMetrics(ContractModel):
    event_count: int = Field(ge=0)
    trade_count_90d: int = Field(ge=0)
    turnover_90d_pct: Decimal | None = Field(default=None, ge=0)
    median_holding_days: Decimal | None = Field(default=None, ge=0)
    max_position_weight_pct: Decimal | None = Field(default=None, ge=0, le=100)
    max_sector_weight_pct: Decimal | None = Field(default=None, ge=0, le=100)
    equity_weight_pct: Decimal | None = Field(default=None, ge=0, le=100)
    max_drawdown_pct: Decimal | None = Field(default=None, ge=0, le=100)
    observed_span_days: Decimal | None = Field(default=None, ge=0)
    traded_asset_type_count: int = Field(default=0, ge=0)


class BehaviorProfile(ContractModel):
    schema_version: Literal["behavior-profile.v1"] = "behavior-profile.v1"
    behavior_profile_id: NonEmptyStr
    owner_id: NonEmptyStr
    profile_version: int = Field(ge=1)
    calculated_at: datetime
    ruleset_version: Literal["behavior-profile-rules.v1"] = RULESET_VERSION
    evidence_status: BehaviorEvidenceStatus
    questionnaire_profile_id: NonEmptyStr
    questionnaire_risk_score: Decimal = Field(ge=0, le=100)
    behavior_risk_score: Decimal | None = Field(default=None, ge=0, le=100)
    effective_risk_score: Decimal = Field(ge=0, le=100)
    effective_risk_level: RiskLevel
    suitability_level: SuitabilityLevel
    metrics: BehaviorMetrics
    dimensions: tuple[BehaviorDimension, ...] = Field(min_length=8, max_length=8)
    persona: NonEmptyStr
    tags: tuple[NonEmptyStr, ...]
    confidence: Decimal = Field(ge=0, le=1)
    evidence: tuple[BehaviorEvidence, ...]
    display_policy: DisplayPolicy

    @model_validator(mode="after")
    def validate_profile(self) -> Self:
        if self.calculated_at.tzinfo is None or self.calculated_at.utcoffset() is None:
            raise ValueError("calculated_at must be timezone-aware")
        keys = [item.key for item in self.dimensions]
        if set(keys) != {"risk", "exp", "act", "res", "inf", "ai", "per", "aid"}:
            raise ValueError("dimensions must contain the complete eight-dimension set")
        if len(set(keys)) != len(keys):
            raise ValueError("dimensions must be unique")
        if self.effective_risk_level != risk_level_for_score(self.effective_risk_score):
            raise ValueError("effective risk level does not match score")
        if self.suitability_level != suitability_for_score(self.effective_risk_score):
            raise ValueError("suitability level does not match score")
        if self.display_policy.owner_id != self.owner_id:
            raise ValueError("display policy owner does not match profile")
        if self.evidence_status == BehaviorEvidenceStatus.INSUFFICIENT_DATA:
            if self.behavior_risk_score is not None or self.evidence:
                raise ValueError("insufficient profile must not claim behaviour evidence")
        return self


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def display_mode_for_trust(trust_score: int) -> DisplayMode:
    if trust_score <= DISPLAY_POLICY_THRESHOLDS["audit_expanded_max"]:
        return DisplayMode.AUDIT_EXPANDED
    if trust_score >= DISPLAY_POLICY_THRESHOLDS["conclusion_first_min"]:
        return DisplayMode.CONCLUSION_FIRST
    return DisplayMode.STANDARD


def build_display_policy(
    owner_id: str,
    trust_score: int,
    *,
    updated_at: datetime,
    source: DisplayPolicySource = DisplayPolicySource.EXPLICIT,
) -> DisplayPolicy:
    return DisplayPolicy(
        owner_id=owner_id,
        trust_score=trust_score,
        mode=display_mode_for_trust(trust_score),
        source=source,
        updated_at=updated_at,
    )


def suitability_for_score(score: Decimal) -> SuitabilityLevel:
    for lower, upper, level in SUITABILITY_SCORE_BANDS:
        if lower <= score <= upper:
            return level
    raise ValueError("suitability score must be between 0 and 100")


def _experience_score(level: ExperienceLevel) -> Decimal:
    return {
        ExperienceLevel.NOVICE: Decimal("20"),
        ExperienceLevel.INTERMEDIATE: Decimal("60"),
        ExperienceLevel.EXPERIENCED: Decimal("90"),
    }[level]


def _historical_max_drawdown(snapshots: tuple[BehaviorEvent, ...]) -> Decimal | None:
    peak: Decimal | None = None
    calculated: Decimal | None = None
    for snapshot in snapshots:
        value = snapshot.portfolio_value_cny
        if value is None:
            continue
        peak = value if peak is None else max(peak, value)
        drawdown = _q((peak - value) / peak * Decimal("100"))
        calculated = drawdown if calculated is None else max(calculated, drawdown)
    reported = max(
        (item.drawdown_pct for item in snapshots if item.drawdown_pct is not None),
        default=None,
    )
    candidates = tuple(item for item in (calculated, reported) if item is not None)
    return max(candidates) if candidates else None


def calculate_behavior_profile(
    questionnaire_profile: RiskProfile,
    events: tuple[BehaviorEvent, ...],
    *,
    calculated_at: datetime,
    display_policy: DisplayPolicy | None = None,
    profile_version: int = 1,
) -> BehaviorProfile:
    """Fuse deterministic behaviour metrics with the questionnaire conservatively."""
    if calculated_at.tzinfo is None or calculated_at.utcoffset() is None:
        raise ValueError("calculated_at must be timezone-aware")
    if any(event.owner_id != questionnaire_profile.owner_id for event in events):
        raise ValueError("behaviour events must share profile owner scope")
    ordered = tuple(sorted(events, key=lambda item: (item.occurred_at, item.event_id)))
    if len({item.event_id for item in ordered}) != len(ordered):
        raise ValueError("behaviour events must not contain duplicate event IDs")
    policy = display_policy or build_display_policy(
        questionnaire_profile.owner_id,
        50,
        updated_at=calculated_at,
        source=DisplayPolicySource.DEFAULT,
    )
    if policy.owner_id != questionnaire_profile.owner_id:
        raise ValueError("display policy must share profile owner scope")

    window_start = calculated_at - timedelta(days=90)
    all_trades = tuple(
        item for item in ordered
        if item.event_type == BehaviorEventType.TRADE and item.occurred_at <= calculated_at
    )
    trades = tuple(
        item for item in all_trades if window_start <= item.occurred_at
    )
    snapshots = tuple(
        item for item in ordered
        if item.event_type == BehaviorEventType.POSITION_SNAPSHOT and item.occurred_at <= calculated_at
    )
    observations = tuple(sorted((*trades, *snapshots), key=lambda item: (item.occurred_at, item.event_id)))
    trade_span_days = Decimal("0")
    if len(all_trades) >= 2:
        trade_span_days = Decimal(str((all_trades[-1].occurred_at - all_trades[0].occurred_at).total_seconds() / 86400))
    # Preserve the legacy behavior-event API while applying the stricter
    # evidence boundary to user-imported historical trades.
    has_historical_import = any(item.source.startswith("confirmed historical trade batch ") for item in all_trades)
    sufficient = (
        len(all_trades) >= 20 and trade_span_days >= Decimal("90") and len(snapshots) >= 2
        if has_historical_import
        else len(trades) >= 3 and len(snapshots) >= 2
    )
    portfolio_values = [item.portfolio_value_cny for item in (*trades, *snapshots) if item.portfolio_value_cny]
    mean_portfolio = (
        sum(portfolio_values, Decimal("0")) / Decimal(len(portfolio_values))
        if portfolio_values else None
    )
    trade_value = sum(
        ((item.quantity or Decimal("0")) * (item.price_cny or Decimal("0")) for item in trades),
        Decimal("0"),
    )
    turnover = _q(trade_value / mean_portfolio * Decimal("100")) if mean_portfolio else None
    max_position = max((item.max_position_weight_pct for item in snapshots if item.max_position_weight_pct is not None), default=None)
    max_sector = max((item.max_sector_weight_pct for item in snapshots if item.max_sector_weight_pct is not None), default=None)
    equity_weight = snapshots[-1].equity_weight_pct if snapshots else None
    max_drawdown = _historical_max_drawdown(snapshots)
    observed_span_days = None
    if len(observations) >= 2:
        observed_span_days = _q(Decimal(str((observations[-1].occurred_at - observations[0].occurred_at).total_seconds() / 86400)))
    traded_asset_type_count = len({item.asset_type for item in trades if item.asset_type is not None})

    buys: dict[str, list[datetime]] = defaultdict(list)
    holding_days: list[Decimal] = []
    for item in trades:
        if item.asset_id is None or item.side is None:
            continue
        if item.side == TradeSide.BUY:
            buys[item.asset_id].append(item.occurred_at)
        elif buys[item.asset_id]:
            started = buys[item.asset_id].pop(0)
            holding_days.append(Decimal(str((item.occurred_at - started).total_seconds() / 86400)))
    median_days = _q(Decimal(str(median(holding_days)))) if holding_days else None

    metrics = BehaviorMetrics(
        event_count=len(ordered),
        trade_count_90d=len(trades),
        turnover_90d_pct=turnover,
        median_holding_days=median_days,
        max_position_weight_pct=max_position,
        max_sector_weight_pct=max_sector,
        equity_weight_pct=equity_weight,
        max_drawdown_pct=max_drawdown,
        observed_span_days=observed_span_days,
        traded_asset_type_count=traded_asset_type_count,
    )
    evidence: list[BehaviorEvidence] = []
    if sufficient:
        def add_evidence(metric: str, value: Decimal | None, unit: str, sources: tuple[BehaviorEvent, ...]) -> None:
            if value is None or not sources:
                return
            evidence.append(BehaviorEvidence(
                evidence_id=f"behavior:{metric}:{len(evidence) + 1}",
                metric=metric,
                value=value,
                unit=unit,
                observed_at=max(item.occurred_at for item in sources),
                source_event_ids=tuple(item.event_id for item in sources),
            ))
        add_evidence("turnover_90d_pct", turnover, "PERCENT", trades)
        add_evidence("max_position_weight_pct", max_position, "PERCENT", snapshots)
        add_evidence("max_sector_weight_pct", max_sector, "PERCENT", snapshots)
        add_evidence("equity_weight_pct", equity_weight, "PERCENT", snapshots[-1:] if snapshots else ())
        add_evidence("max_drawdown_pct", max_drawdown, "PERCENT", snapshots)
        add_evidence("observed_span_days", observed_span_days, "DAYS", observations)
        if traded_asset_type_count:
            add_evidence(
                "traded_asset_type_count",
                Decimal(traded_asset_type_count),
                "COUNT",
                trades,
            )

    questionnaire_score = questionnaire_profile.risk_score
    behavior_score: Decimal | None = None
    if sufficient and equity_weight is not None and max_position is not None and turnover is not None:
        drawdown_component = min((max_drawdown or Decimal("0")) / Decimal("35"), Decimal("1")) * Decimal("100")
        concentration_component = min(max_position / Decimal("35"), Decimal("1")) * Decimal("100")
        turnover_component = min(turnover / Decimal("200"), Decimal("1")) * Decimal("100")
        behavior_score = _q(
            drawdown_component * Decimal("0.40")
            + equity_weight * Decimal("0.30")
            + concentration_component * Decimal("0.15")
            + turnover_component * Decimal("0.15")
        )
    effective = min(questionnaire_score, behavior_score) if behavior_score is not None else questionnaire_score
    activity_score = None
    if sufficient and turnover is not None:
        activity_score = _q(
            min(turnover / Decimal("200"), Decimal("1")) * Decimal("70")
            + min(Decimal(len(trades)) / Decimal("20"), Decimal("1")) * Decimal("30")
        )
    questionnaire_experience_score = _experience_score(questionnaire_profile.experience_level)
    behavior_experience_score = None
    if sufficient and observed_span_days is not None and traded_asset_type_count:
        behavior_experience_score = _q(
            Decimal("20")
            + min(observed_span_days / Decimal("730"), Decimal("1")) * Decimal("50")
            + min(Decimal(traded_asset_type_count) / Decimal("4"), Decimal("1")) * Decimal("30")
        )
    experience_score = behavior_experience_score or questionnaire_experience_score

    if policy.source == DisplayPolicySource.DEFAULT:
        ai_dimension = BehaviorDimension(key="ai", source=DimensionSource.INSUFFICIENT_DATA)
    else:
        ai_dimension = BehaviorDimension(
            key="ai",
            score=Decimal(policy.trust_score),
            source=(
                DimensionSource.EXPLICIT
                if policy.source == DisplayPolicySource.EXPLICIT
                else DimensionSource.QUESTIONNAIRE
            ),
        )

    dimensions = (
        BehaviorDimension(key="risk", score=effective, source=DimensionSource.CALCULATED if behavior_score is not None else DimensionSource.QUESTIONNAIRE),
        BehaviorDimension(key="exp", score=experience_score, source=DimensionSource.CALCULATED if behavior_experience_score is not None else DimensionSource.QUESTIONNAIRE),
        BehaviorDimension(key="act", score=activity_score, source=DimensionSource.CALCULATED if activity_score is not None else DimensionSource.INSUFFICIENT_DATA),
        BehaviorDimension(key="res", source=DimensionSource.INSUFFICIENT_DATA),
        BehaviorDimension(key="inf", source=DimensionSource.INSUFFICIENT_DATA),
        ai_dimension,
        BehaviorDimension(key="per", source=DimensionSource.INSUFFICIENT_DATA),
        BehaviorDimension(key="aid", source=DimensionSource.INSUFFICIENT_DATA),
    )
    if activity_score is not None and activity_score >= Decimal("66") and effective >= Decimal("58"):
        persona = "主动交易型"
    elif experience_score < Decimal("42"):
        persona = "起步护航型"
    else:
        persona = "稳健成长型"
    tags = [
        "本金敏感" if effective < Decimal("45") else "中等风险偏好" if effective < Decimal("70") else "高风险偏好",
        "投资新手" if experience_score < Decimal("40") else "有一定经验" if experience_score < Decimal("70") else "资深投资者",
    ]
    if activity_score is not None:
        tags.append("高频盯盘" if activity_score >= Decimal("68") else "低频长线" if activity_score < Decimal("35") else "适度活跃")
    tags.append("对 AI 谨慎" if policy.trust_score < 35 else "AI 高信任" if policy.trust_score >= 65 else "AI 标准信任")
    confidence = Decimal("0") if not sufficient else min(Decimal("1"), Decimal(len(trades) + len(snapshots) * 2) / Decimal("20"))
    identity_payload = json.dumps(
        {
            "owner": questionnaire_profile.owner_id,
            "profile": questionnaire_profile.profile_id,
            "version": profile_version,
            "rules": RULESET_VERSION,
            "events": [item.event_id for item in ordered],
            "at": calculated_at.isoformat(),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    behavior_profile_id = "behavior-profile:" + sha256(identity_payload).hexdigest()[:32]
    return BehaviorProfile(
        behavior_profile_id=behavior_profile_id,
        owner_id=questionnaire_profile.owner_id,
        profile_version=profile_version,
        calculated_at=calculated_at,
        evidence_status=BehaviorEvidenceStatus.CALCULATED if behavior_score is not None else BehaviorEvidenceStatus.INSUFFICIENT_DATA,
        questionnaire_profile_id=questionnaire_profile.profile_id,
        questionnaire_risk_score=questionnaire_score,
        behavior_risk_score=behavior_score,
        effective_risk_score=effective,
        effective_risk_level=risk_level_for_score(effective),
        suitability_level=suitability_for_score(effective),
        metrics=metrics,
        dimensions=dimensions,
        persona=persona,
        tags=tuple(tags),
        confidence=_q(confidence),
        evidence=tuple(evidence if behavior_score is not None else ()),
        display_policy=policy,
    )


def effective_risk_profile(questionnaire_profile: RiskProfile, behavior_profile: BehaviorProfile) -> RiskProfile:
    """Return a standard RiskProfile that existing deterministic gates can consume."""
    if questionnaire_profile.owner_id != behavior_profile.owner_id:
        raise ValueError("profile owners must match")
    return questionnaire_profile.model_copy(update={
        "profile_id": behavior_profile.behavior_profile_id,
        "profile_version": behavior_profile.profile_version,
        "created_at": behavior_profile.calculated_at,
        "risk_score": behavior_profile.effective_risk_score,
        "risk_level": behavior_profile.effective_risk_level,
        "confidence": min(questionnaire_profile.confidence, behavior_profile.confidence) if behavior_profile.evidence_status == BehaviorEvidenceStatus.CALCULATED else questionnaire_profile.confidence,
    })


def behavior_event_from_portfolio(
    portfolio: PortfolioImportBundle,
    *,
    source: str = "user-confirmed portfolio snapshot",
) -> BehaviorEvent:
    """Convert one confirmed portfolio into an aggregate behaviour observation."""
    positions = portfolio.position_snapshot.positions
    total = sum((item.market_value for item in positions), Decimal("0"))
    if total <= 0:
        raise ValueError("portfolio value must be positive")
    invested = tuple(item for item in positions if item.asset_type != AssetType.CASH)
    equity_types = {AssetType.STOCK, AssetType.ETF, AssetType.MUTUAL_FUND}
    equity_value = sum(
        (item.market_value for item in positions if item.asset_type in equity_types),
        Decimal("0"),
    )
    max_position = max(
        (item.market_value / total * Decimal("100") for item in invested),
        default=Decimal("0"),
    )
    sectors: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for item in invested:
        sectors[item.sector or "UNCLASSIFIED"] += item.market_value
    max_sector = max(
        (value / total * Decimal("100") for value in sectors.values()),
        default=Decimal("0"),
    )
    return BehaviorEvent(
        event_id=f"portfolio-snapshot:{portfolio.position_snapshot.snapshot_id}",
        owner_id=portfolio.owner_id,
        event_type=BehaviorEventType.POSITION_SNAPSHOT,
        occurred_at=portfolio.position_snapshot.as_of,
        source=source,
        portfolio_value_cny=_q(total),
        equity_weight_pct=_q(equity_value / total * Decimal("100")),
        max_position_weight_pct=_q(max_position),
        max_sector_weight_pct=_q(max_sector),
    )


__all__ = [
    "RULESET_VERSION",
    "DISPLAY_POLICY_THRESHOLDS",
    "SUITABILITY_SCORE_BANDS",
    "BehaviorDimension",
    "BehaviorEvent",
    "BehaviorEventType",
    "BehaviorEvidence",
    "BehaviorEvidenceStatus",
    "BehaviorMetrics",
    "BehaviorProfile",
    "DimensionSource",
    "DisplayMode",
    "DisplayPolicy",
    "DisplayPolicySource",
    "SuitabilityLevel",
    "TradeSide",
    "build_display_policy",
    "behavior_event_from_portfolio",
    "calculate_behavior_profile",
    "display_mode_for_trust",
    "effective_risk_profile",
    "suitability_for_score",
]
