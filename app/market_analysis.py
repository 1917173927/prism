"""Deterministic market-screen calculations and the fixed cross-market registry."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import math
from typing import Any, Iterable


@dataclass(frozen=True)
class MarketIndex:
    market: str
    index_id: str
    name: str
    symbol: str | None
    currency: str
    timezone: str
    precision: int = 2


INDEX_REGISTRY: tuple[MarketIndex, ...] = (
    MarketIndex("CN", "sse-composite", "上证指数", "000001.SH", "CNY", "Asia/Shanghai"),
    MarketIndex("CN", "szse-component", "深证成指", "399001.SZ", "CNY", "Asia/Shanghai"),
    MarketIndex("CN", "chinext", "创业板指", "399006.SZ", "CNY", "Asia/Shanghai"),
    MarketIndex("CN", "csi-300", "沪深300", "000300.SH", "CNY", "Asia/Shanghai"),
    MarketIndex("HK", "hang-seng", "恒生指数", "^HSI", "HKD", "Asia/Hong_Kong"),
    MarketIndex("HK", "hang-seng-china-enterprises", "恒生中国企业指数", "^HSCE", "HKD", "Asia/Hong_Kong"),
    MarketIndex("HK", "hang-seng-tech", "恒生科技指数", "HSTECH.HK", "HKD", "Asia/Hong_Kong"),
    # Yahoo does not expose this series; the public ET Net chart uses HSC.
    # The API keeps the source symbol explicit and never substitutes an ETF.
    MarketIndex("HK", "hang-seng-composite", "恒生综合指数", "HSC", "HKD", "Asia/Hong_Kong"),
    MarketIndex("US", "sp-500", "标普500", "^GSPC", "USD", "America/New_York"),
    MarketIndex("US", "nasdaq-composite", "纳斯达克综合指数", "^IXIC", "USD", "America/New_York"),
    MarketIndex("US", "dow-jones-industrial", "道琼斯工业指数", "^DJI", "USD", "America/New_York"),
    MarketIndex("US", "russell-2000", "罗素2000", "^RUT", "USD", "America/New_York"),
)


def find_index(market: str, index_id: str) -> MarketIndex | None:
    return next((item for item in INDEX_REGISTRY if item.market == market and item.index_id == index_id), None)


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    result = Decimal(str(value))
    return result if result.is_finite() else None


def aggregate_monthly(bars: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for bar in sorted(bars, key=lambda row: str(row["time"])):
        groups[str(bar["time"])[:7]].append(bar)
    aggregated: list[dict[str, Any]] = []
    for rows in groups.values():
        volume_values = [_decimal(row.get("volume")) for row in rows]
        turnover_values = [_decimal(row.get("turnover")) for row in rows]
        aggregated.append({
            "time": str(rows[-1]["time"]),
            "open": _decimal(rows[0]["open"]),
            "high": max(_decimal(row["high"]) for row in rows),
            "low": min(_decimal(row["low"]) for row in rows),
            "close": _decimal(rows[-1]["close"]),
            "volume": sum(volume_values, Decimal(0)) if all(value is not None for value in volume_values) else None,
            "turnover": sum(turnover_values, Decimal(0)) if all(value is not None for value in turnover_values) else None,
        })
    return aggregated


def bollinger(bars: list[dict[str, Any]], period: int = 20, multiplier: int = 2) -> list[dict[str, Any]]:
    closes = [float(bar["close"]) for bar in bars]
    output = []
    for index in range(period - 1, len(closes)):
        window = closes[index - period + 1:index + 1]
        middle = sum(window) / period
        deviation = math.sqrt(sum((value - middle) ** 2 for value in window) / period)
        output.append({"time": bars[index]["time"], "middle": round(middle, 6),
                       "upper": round(middle + multiplier * deviation, 6),
                       "lower": round(middle - multiplier * deviation, 6)})
    return output


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    alpha = 2 / (period + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append(alpha * value + (1 - alpha) * result[-1])
    return result


def macd(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    closes = [float(bar["close"]) for bar in bars]
    fast, slow = _ema(closes, 12), _ema(closes, 26)
    diff = [left - right for left, right in zip(fast, slow)]
    dea = _ema(diff, 9)
    return [{"time": bar["time"], "diff": round(diff[index], 6), "dea": round(dea[index], 6),
             "histogram": round(2 * (diff[index] - dea[index]), 6)} for index, bar in enumerate(bars)]


def kdj(bars: list[dict[str, Any]], period: int = 9) -> list[dict[str, Any]]:
    k_value = d_value = 50.0
    output = []
    for index in range(period - 1, len(bars)):
        window = bars[index - period + 1:index + 1]
        low = min(float(row["low"]) for row in window)
        high = max(float(row["high"]) for row in window)
        rsv = 50.0 if high == low else (float(bars[index]["close"]) - low) / (high - low) * 100
        k_value = 2 * k_value / 3 + rsv / 3
        d_value = 2 * d_value / 3 + k_value / 3
        output.append({"time": bars[index]["time"], "k": round(k_value, 6), "d": round(d_value, 6),
                       "j": round(3 * k_value - 2 * d_value, 6)})
    return output


def volume_summary(bars: list[dict[str, Any]]) -> dict[str, Any]:
    values = [_decimal(bar.get("volume")) for bar in bars]
    latest = values[-1] if values else None
    def ratio(period: int) -> Decimal | None:
        window = values[-period:]
        if latest is None or not window or any(value is None for value in window):
            return None
        average = sum(window, Decimal(0)) / Decimal(len(window))
        return (latest / average).quantize(Decimal("0.0001")) if average else None
    return {"latest_volume": latest, "latest_turnover": _decimal(bars[-1].get("turnover")) if bars else None,
            "volume_to_ma5": ratio(5), "volume_to_ma20": ratio(20)}


def pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean, right_mean = sum(left) / len(left), sum(right) / len(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    left_sum = sum((x - left_mean) ** 2 for x in left)
    right_sum = sum((y - right_mean) ** 2 for y in right)
    denominator = math.sqrt(left_sum * right_sum)
    return round(numerator / denominator, 6) if denominator else None


def correlated_returns(index_bars: list[dict[str, Any]], factor_points: list[dict[str, Any]], *,
                       yield_factor: bool = False, monthly: bool = False,
                       market: str = "US") -> dict[str, Any]:
    """Correlate returns without allowing later US data into CN/HK closes.

    US observations may align on the same session key.  CN/HK observations only
    consume a strictly earlier factor key, which is conservative for both daily
    and monthly series and prevents a later US close from leaking into analysis.
    """
    key = (lambda value: str(value)[:7]) if monthly else (lambda value: str(value)[:10])
    index_close = {key(row["time"]): float(row["close"]) for row in index_bars}
    factor_rows = sorted((key(row["time"]), float(row["value"])) for row in factor_points)
    factor_value: dict[str, float] = {}
    factor_source_key: dict[str, str] = {}
    factor_index = 0
    last_factor: tuple[str, float] | None = None
    strict_previous = market.upper() in {"CN", "HK"}
    for index_key in sorted(index_close):
        while factor_index < len(factor_rows):
            factor_key, value = factor_rows[factor_index]
            if factor_key > index_key or (strict_previous and factor_key == index_key):
                break
            last_factor = (factor_key, value)
            factor_index += 1
        if last_factor is not None:
            factor_source_key[index_key], factor_value[index_key] = last_factor
    dates = sorted(set(index_close) & set(factor_value))
    pairs: list[tuple[float, float]] = []
    for previous, current in zip(dates, dates[1:]):
        if factor_source_key[previous] == factor_source_key[current]:
            continue
        if min(index_close[previous], index_close[current], factor_value[previous], factor_value[current]) <= 0:
            continue
        index_return = math.log(index_close[current] / index_close[previous])
        factor_return = factor_value[current] - factor_value[previous] if yield_factor else math.log(factor_value[current] / factor_value[previous])
        pairs.append((index_return, factor_return))
    def calculate(period: int, minimum: int) -> float | None:
        sample = pairs[-period:]
        return pearson([row[0] for row in sample], [row[1] for row in sample]) if len(sample) >= minimum else None
    return {"correlation_20": calculate(20, 15), "correlation_60": calculate(60, 40), "sample_size": len(pairs)}


def technical_indicators(bars: list[dict[str, Any]]) -> dict[str, Any]:
    return {"boll": bollinger(bars), "macd": macd(bars), "kdj": kdj(bars),
            "parameters": {"boll": "20,2", "macd": "12,26,9", "kdj": "9,3,3"}}
