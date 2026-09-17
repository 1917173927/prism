"""Deterministic guidance and market context for the trading-style page."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from .contracts import (
    HistoricalTradeRecord,
    TradeAssetType,
    TradeRecordStatus,
    TradeSecurityHistorySummary,
    TradeSecurityQuoteSnapshot,
    TradeStyleGuidanceItem,
    TradeStyleSecurityInsight,
    TradingStyleProfile,
)


_EQUITY_PREFIXES = (
    "600", "601", "603", "605", "688", "689",
    "000", "001", "002", "003", "300", "301",
    "82", "83", "87", "88", "92",
)
_QUOTE_FIELDS = (
    "change_pct", "price_change_cny", "open_price_cny", "high_price_cny",
    "low_price_cny", "previous_close_cny", "volume_shares", "turnover_cny",
)
_SHANGHAI = ZoneInfo("Asia/Shanghai")


_GUIDANCE: dict[str, tuple[TradeStyleGuidanceItem, ...]] = {
    "高频短线型": (
        TradeStyleGuidanceItem(code="FREQUENCY_BUDGET", category="DISCIPLINE", title="建立交易次数与费用预算", description="在交易前设定可接受的交易频率与费用预算，复盘实际执行偏差。"),
        TradeStyleGuidanceItem(code="DAILY_RISK_LIMIT", category="RISK_CONTROL", title="预设单日损失和退出纪律", description="在交易计划中记录单日风险边界和退出条件，避免临场扩大风险暴露。"),
        TradeStyleGuidanceItem(code="PLAN_VS_IMPULSE", category="REVIEW", title="区分计划交易与追涨杀跌", description="复盘时分别记录计划内交易与临时交易，观察冲动交易占比及其成本。"),
    ),
    "主动波段型": (
        TradeStyleGuidanceItem(code="ENTRY_EXIT_RULES", category="DISCIPLINE", title="记录入场、退出和失效条件", description="每次交易前记录计划依据、退出条件和判断失效条件，便于事后核对。"),
        TradeStyleGuidanceItem(code="CONCENTRATION_LIMIT", category="RISK_CONTROL", title="控制标的与行业集中度", description="持续检查单一标的和行业暴露，避免波段交易演变为无计划的集中持有。"),
        TradeStyleGuidanceItem(code="HOLDING_DRIFT", category="REVIEW", title="检查持有期是否偏离计划", description="定期比较计划持有周期与实际持有周期，识别过早退出或被动延长。"),
    ),
    "低频长持型": (
        TradeStyleGuidanceItem(code="THESIS_CHECKLIST", category="DISCIPLINE", title="建立投资逻辑清单", description="保存核心判断、验证指标和复核周期，避免仅凭持有时间替代持续判断。"),
        TradeStyleGuidanceItem(code="FUNDAMENTAL_EVENTS", category="REVIEW", title="关注基本面与重大事件", description="在定期复核时检查基本面、治理和重大事件是否改变原有判断。"),
        TradeStyleGuidanceItem(code="REBALANCE_LIQUIDITY", category="RISK_CONTROL", title="设置再平衡区间并保留流动性", description="预先定义组合再平衡条件，同时保留满足日常资金需求的流动性。"),
    ),
    "稳健均衡型": (
        TradeStyleGuidanceItem(code="DIVERSIFICATION", category="DIVERSIFICATION", title="维持标的与行业分散", description="持续观察标的和行业分布，避免少数交易逐步推高组合集中度。"),
        TradeStyleGuidanceItem(code="REBALANCE_CADENCE", category="DISCIPLINE", title="按固定周期执行再平衡", description="采用稳定的检查周期和一致的再平衡条件，减少临时判断造成的偏移。"),
        TradeStyleGuidanceItem(code="STYLE_DRIFT", category="REVIEW", title="监测交易风格漂移", description="跟踪交易频率、持有期与集中度变化，识别行为是否偏离既定方式。"),
    ),
}


def guidance_for_profile(profile: TradingStyleProfile) -> tuple[TradeStyleGuidanceItem, ...]:
    """Return versioned, non-LLM behavioral guidance for one computed style."""
    if profile.primary_style is None:
        return ()
    return _GUIDANCE.get(profile.primary_style, ())


def _normalize_equity_code(value: str | None) -> str | None:
    match = re.fullmatch(r"(?P<code>\d{6})(?:\.(?P<suffix>SH|SZ|BJ))?", (value or "").strip().upper())
    if match is None:
        return None
    code = match.group("code")
    if not code.startswith(_EQUITY_PREFIXES):
        return None
    expected = "SH" if code.startswith("6") else "BJ" if code.startswith(("8", "9")) else "SZ"
    supplied = match.group("suffix")
    if supplied is not None and supplied != expected:
        return None
    return f"{code}.{expected}"


def aggregate_trade_securities(
    records: tuple[HistoricalTradeRecord, ...], *, limit: int = 3
) -> tuple[TradeSecurityHistorySummary, ...]:
    """Rank current A-share equity records by confirmed gross traded amount."""
    if limit < 1:
        return ()
    aggregates: dict[str, dict[str, Any]] = {}
    for record in records:
        if record.status != TradeRecordStatus.ACTIVE:
            continue
        if record.asset_type is not None and record.asset_type != TradeAssetType.STOCK:
            continue
        code = _normalize_equity_code(record.security_code)
        if code is None:
            continue
        row = aggregates.setdefault(code, {
            "security_code": code,
            "security_name": None,
            "trade_count": 0,
            "buy_count": 0,
            "sell_count": 0,
            "gross_amount_cny": Decimal("0"),
            "last_traded_at": record.traded_at,
        })
        row["trade_count"] += 1
        row["buy_count" if record.side.value == "BUY" else "sell_count"] += 1
        row["gross_amount_cny"] += record.gross_amount_cny
        if record.traded_at >= row["last_traded_at"]:
            row["last_traded_at"] = record.traded_at
            if record.security_name:
                row["security_name"] = record.security_name

    total = sum((row["gross_amount_cny"] for row in aggregates.values()), Decimal("0"))
    ranked = sorted(
        aggregates.values(),
        key=lambda row: (-row["gross_amount_cny"], -row["last_traded_at"].timestamp(), row["security_code"]),
    )[:limit]
    return tuple(TradeSecurityHistorySummary(**{
        **row,
        "gross_amount_cny": row["gross_amount_cny"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        "gross_amount_share_pct": (row["gross_amount_cny"] / total * Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        ),
    }) for row in ranked)


def _decimal(value: object, *, positive: bool = False, nonnegative: bool = False) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not result.is_finite() or (positive and result <= 0) or (nonnegative and result < 0):
        return None
    return result


def _timestamp(value: object, fallback: datetime | None = None) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return fallback
    else:
        return fallback
    return parsed.replace(tzinfo=_SHANGHAI) if parsed.tzinfo is None else parsed


def normalize_trade_quote(
    data: Mapping[str, object] | None,
    *,
    data_mode: str,
    retrieved_at: datetime,
) -> TradeSecurityQuoteSnapshot | None:
    """Validate one provider quote and compute its deterministic day-range position."""
    if not data:
        return None
    synthetic = bool(data.get("is_synthetic"))
    if data_mode == "LIVE" and synthetic:
        return None
    price = _decimal(data.get("price_cny"), positive=True)
    observed = _timestamp(data.get("observed_at"))
    retrieved = _timestamp(data.get("retrieved_at"), retrieved_at)
    source = str(data.get("source") or "").strip()
    provider_tier = str(data.get("provider_tier") or ("STATIC_FALLBACK" if synthetic else "LIVE_FALLBACK")).strip()
    if price is None or observed is None or retrieved is None or not source or not provider_tier:
        return None

    open_price = _decimal(data.get("open_price_cny"), positive=True)
    high = _decimal(data.get("high_price_cny"), positive=True)
    low = _decimal(data.get("low_price_cny"), positive=True)
    previous = _decimal(data.get("previous_close_cny"), positive=True)
    if high is not None and low is not None and (high < low or not low <= price <= high):
        high = low = None
    if open_price is not None and high is not None and low is not None and not low <= open_price <= high:
        open_price = None

    price_change = _decimal(data.get("price_change_cny"))
    if price_change is None and previous is not None:
        price_change = price - previous
    change_pct = _decimal(data.get("change_pct"))
    if change_pct is None and previous is not None:
        change_pct = (price - previous) / previous * Decimal("100")
    day_position = None
    if high is not None and low is not None and high > low and low <= price <= high:
        day_position = ((price - low) / (high - low) * Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    values = {
        "change_pct": change_pct,
        "price_change_cny": price_change,
        "open_price_cny": open_price,
        "high_price_cny": high,
        "low_price_cny": low,
        "previous_close_cny": previous,
        "volume_shares": _decimal(data.get("volume_shares"), nonnegative=True),
        "turnover_cny": _decimal(data.get("turnover_cny"), nonnegative=True),
    }
    missing_items = [field for field in _QUOTE_FIELDS if values[field] is None]
    if day_position is None:
        missing_items.append("day_range_position_pct")
    missing = tuple(missing_items)
    return TradeSecurityQuoteSnapshot(
        price_cny=price,
        **values,
        day_range_position_pct=day_position,
        observed_at=observed,
        retrieved_at=retrieved,
        source=source,
        provider_tier=provider_tier,
        is_synthetic=synthetic,
        missing_fields=missing,
    )


def combine_security_insight(
    history: TradeSecurityHistorySummary,
    quote: TradeSecurityQuoteSnapshot | None,
    *,
    failure_message: str | None = None,
) -> TradeStyleSecurityInsight:
    if quote is None:
        return TradeStyleSecurityInsight(
            history=history,
            quote_status="UNAVAILABLE",
            message=failure_message or "当前未取得可验证行情。",
        )
    incomplete = quote.is_synthetic or bool(quote.missing_fields)
    return TradeStyleSecurityInsight(
        history=history,
        quote_status="REVIEW_REQUIRED" if incomplete else "PASS",
        quote=quote,
        message=(
            "当前展示 MOCK 示例快照，不代表实时行情。" if quote.is_synthetic
            else "部分当日行情字段未返回，已仅展示可验证字段。" if quote.missing_fields
            else None
        ),
    )


__all__ = [
    "aggregate_trade_securities",
    "combine_security_insight",
    "guidance_for_profile",
    "normalize_trade_quote",
]
