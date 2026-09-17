"""Deterministic trading-style metrics and classification."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
import json
from statistics import median

from app.portfolio import AssetType
from app.profile.behavior import BehaviorEvent, BehaviorEventType, TradeSide as BehaviorTradeSide

from .contracts import (
    HistoricalTradeRecord,
    TradeRecordStatus,
    TradeSide,
    TradingStyleMetrics,
    TradingStyleProfile,
    TradingStyleStatus,
)


def behavior_events_from_trades(records: tuple[HistoricalTradeRecord, ...]) -> tuple[BehaviorEvent, ...]:
    """Project current trade revisions into the existing behavior engine."""
    asset_types = {
        "STOCK": AssetType.STOCK,
        "ETF": AssetType.ETF,
        "MUTUAL_FUND": AssetType.MUTUAL_FUND,
        "CONVERTIBLE_BOND": AssetType.BOND,
        "OTHER": AssetType.OTHER,
    }
    events = []
    for item in records:
        if item.status != TradeRecordStatus.ACTIVE:
            continue
        events.append(BehaviorEvent(
            event_id=f"historical-trade-event:{item.trade_id}:{item.revision}",
            owner_id=item.owner_id,
            event_type=BehaviorEventType.TRADE,
            occurred_at=item.traded_at,
            source=f"confirmed historical trade batch {item.batch_id}",
            asset_id=item.security_code or item.security_name,
            asset_type=asset_types.get(item.asset_type.value if item.asset_type else "OTHER", AssetType.OTHER),
            side=BehaviorTradeSide(item.side.value),
            quantity=item.quantity,
            price_cny=item.price_cny,
            portfolio_value_cny=item.account_value_cny,
        ))
    return tuple(events)


def _q(value: Decimal, places: str = "0.01") -> Decimal:
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def _percentile(values: list[Decimal], percentile: Decimal) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = percentile * Decimal(len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - Decimal(lower)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def calculate_trading_style(
    owner_id: str,
    records: tuple[HistoricalTradeRecord, ...],
    *,
    calculated_at: datetime,
    profile_version: int = 1,
) -> TradingStyleProfile:
    if calculated_at.tzinfo is None or calculated_at.utcoffset() is None:
        raise ValueError("calculated_at must be timezone-aware")
    if any(item.owner_id != owner_id for item in records):
        raise ValueError("trade records must share owner scope")
    active = tuple(sorted(
        (item for item in records if item.status == TradeRecordStatus.ACTIVE and item.traded_at <= calculated_at),
        key=lambda item: (item.traded_at, item.trade_id),
    ))
    amounts = [item.gross_amount_cny for item in active]
    span = Decimal("0")
    if len(active) >= 2:
        span = Decimal(str((active[-1].traded_at - active[0].traded_at).total_seconds() / 86400))
    months = max(span / Decimal("30.4375"), Decimal("1"))
    trades_per_month = Decimal(len(active)) / months if active else Decimal("0")

    lots: dict[tuple[str, str], deque[list[object]]] = defaultdict(deque)
    holding_observations: list[tuple[Decimal, Decimal]] = []
    total_sell_quantity = Decimal("0")
    matched_sell_quantity = Decimal("0")
    unmatched_sell_quantity = Decimal("0")
    for item in active:
        identity = (item.account_alias, item.security_code or item.security_name or "")
        if item.side == TradeSide.BUY:
            lots[identity].append([item.quantity, item.traded_at])
            continue
        remaining = item.quantity
        total_sell_quantity += item.quantity
        while remaining > 0 and lots[identity]:
            lot_quantity, started_at = lots[identity][0]
            matched = min(remaining, lot_quantity)
            holding_observations.append((
                Decimal(str((item.traded_at - started_at).total_seconds() / 86400)), matched
            ))
            matched_sell_quantity += matched
            remaining -= matched
            lot_quantity -= matched
            if lot_quantity == 0:
                lots[identity].popleft()
            else:
                lots[identity][0][0] = lot_quantity
        unmatched_sell_quantity += remaining
    matched_coverage = (
        matched_sell_quantity / total_sell_quantity
        if total_sell_quantity > 0 else Decimal("0")
    )

    by_symbol: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for item in active:
        by_symbol[item.security_code or item.security_name or ""] += item.gross_amount_cny
    total_amount = sum(amounts, Decimal("0"))
    shares = [value / total_amount for value in by_symbol.values()] if total_amount else []
    symbol_hhi = sum((share * share for share in shares), Decimal("0")) if shares else None
    top3_share = sum(sorted(shares, reverse=True)[:3], Decimal("0")) * Decimal("100") if shares else None

    window_start = calculated_at - timedelta(days=90)
    recent = [item for item in active if window_start <= item.traded_at <= calculated_at]
    account_values = [item.account_value_cny for item in recent if item.account_value_cny is not None]
    turnover = None
    if len(account_values) >= 2:
        average_value = sum(account_values, Decimal("0")) / Decimal(len(account_values))
        if average_value > 0:
            turnover = sum((item.gross_amount_cny for item in recent), Decimal("0")) / average_value * Decimal("100")

    confidence = (
        Decimal("0.5") * min(Decimal(len(active)) / Decimal("50"), Decimal("1"))
        + Decimal("0.3") * min(span / Decimal("365"), Decimal("1"))
        + Decimal("0.2") * matched_coverage
    )
    median_holding = None
    if holding_observations:
        total_matched = sum((quantity for _, quantity in holding_observations), Decimal("0"))
        threshold = total_matched / Decimal("2")
        cumulative = Decimal("0")
        for days, quantity in sorted(holding_observations, key=lambda item: item[0]):
            cumulative += quantity
            if cumulative >= threshold:
                median_holding = days
                break
    if len(active) < 10 or span < Decimal("30"):
        status = TradingStyleStatus.INSUFFICIENT_DATA
        style = None
    else:
        status = (
            TradingStyleStatus.CALCULATED
            if len(active) >= 20 and span >= Decimal("90") and confidence >= Decimal("0.60")
            else TradingStyleStatus.PRELIMINARY
        )
        if trades_per_month >= Decimal("30") or (
            median_holding is not None and median_holding < Decimal("3") and trades_per_month >= Decimal("12")
        ):
            style = "高频短线型"
        elif trades_per_month >= Decimal("12") or (
            median_holding is not None and median_holding <= Decimal("30")
        ):
            style = "主动波段型"
        elif trades_per_month <= Decimal("4") and median_holding is not None and median_holding >= Decimal("90"):
            style = "低频长持型"
        else:
            style = "稳健均衡型"

    gaps: list[str] = []
    if len(active) < 10:
        gaps.append("有效交易少于 10 笔")
    if span < Decimal("30"):
        gaps.append("观察期少于 30 天")
    if not holding_observations:
        gaps.append("缺少可配对的买卖记录，无法计算持有期")
    if len(account_values) < 2:
        gaps.append("缺少至少两个账户资产观测值，未计算 90 日换手率")
    if unmatched_sell_quantity > 0:
        gaps.append("存在导入区间之前建仓的卖出记录，未纳入持有期")

    metrics = TradingStyleMetrics(
        trade_count=len(active),
        observed_span_days=_q(span),
        trades_per_month=_q(trades_per_month),
        median_holding_days=_q(median_holding) if median_holding is not None else None,
        matched_sell_coverage=_q(matched_coverage, "0.0001"),
        median_trade_amount_cny=_q(Decimal(str(median(amounts)))) if amounts else None,
        q1_trade_amount_cny=_q(_percentile(amounts, Decimal("0.25"))) if amounts else None,
        q3_trade_amount_cny=_q(_percentile(amounts, Decimal("0.75"))) if amounts else None,
        symbol_hhi=_q(symbol_hhi, "0.0001") if symbol_hhi is not None else None,
        top3_symbol_share_pct=_q(top3_share) if top3_share is not None else None,
        turnover_90d_pct=_q(turnover) if turnover is not None else None,
        unmatched_sell_quantity=_q(unmatched_sell_quantity, "0.0001"),
    )
    identity = json.dumps({
        "owner": owner_id,
        "version": profile_version,
        "at": calculated_at.isoformat(),
        "trades": [(item.trade_id, item.revision) for item in active],
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return TradingStyleProfile(
        profile_id="trading-style:" + sha256(identity).hexdigest()[:32],
        owner_id=owner_id,
        profile_version=profile_version,
        calculated_at=calculated_at,
        status=status,
        primary_style=style,
        confidence=_q(confidence, "0.0001"),
        metrics=metrics,
        active_trade_ids=tuple(item.trade_id for item in active),
        data_gaps=tuple(gaps),
    )
