from decimal import Decimal

from app.market_analysis import (
    INDEX_REGISTRY,
    aggregate_monthly,
    bollinger,
    correlated_returns,
    kdj,
    macd,
    volume_summary,
)


def _bars(count: int = 70):
    return [{"time": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": Decimal(100 + i),
             "high": Decimal(102 + i), "low": Decimal(99 + i), "close": Decimal(101 + i),
             "volume": Decimal(1000 + i), "turnover": Decimal(10000 + i)} for i in range(count)]


def test_registry_contains_four_indices_per_market():
    assert {market: sum(item.market == market for item in INDEX_REGISTRY) for market in ("CN", "HK", "US")} == {"CN": 4, "HK": 4, "US": 4}


def test_monthly_ohlcv_aggregation_uses_financial_boundaries():
    result = aggregate_monthly(_bars(35))
    assert len(result) == 2
    assert result[0]["open"] == Decimal("100")
    assert result[0]["close"] == Decimal("128")
    assert result[0]["high"] == Decimal("129")
    assert result[0]["low"] == Decimal("99")
    assert result[0]["volume"] == sum(Decimal(1000 + index) for index in range(28))


def test_indicators_have_deterministic_shapes_and_defaults():
    bars = _bars()
    assert len(bollinger(bars)) == len(bars) - 19
    assert len(macd(bars)) == len(bars)
    assert len(kdj(bars)) == len(bars) - 8
    assert bollinger(bars)[0]["middle"] == 110.5
    assert macd(bars)[0] == {"time": bars[0]["time"], "diff": 0.0, "dea": 0.0, "histogram": 0.0}


def test_volume_and_correlation_keep_missing_or_short_data_unavailable():
    bars = _bars()
    summary = volume_summary(bars)
    assert summary["latest_volume"] == Decimal("1069")
    assert summary["volume_to_ma5"] == Decimal("1.0019")
    short = correlated_returns(bars[:10], [{"time": row["time"], "value": row["close"] * 2} for row in bars[:10]])
    assert short["correlation_20"] is None and short["correlation_60"] is None
    full = correlated_returns(bars, [{"time": row["time"], "value": row["close"] * 2} for row in bars])
    assert full["correlation_20"] == 1.0 and full["correlation_60"] == 1.0


def test_cn_factor_alignment_never_consumes_same_day_us_observation():
    bars = _bars(45)
    points = [{"time": row["time"], "value": row["close"] * 2} for row in bars]
    us = correlated_returns(bars, points, market="US")
    cn = correlated_returns(bars, points, market="CN")
    assert us["sample_size"] == 44
    assert cn["sample_size"] == 43
    assert cn["correlation_20"] == 1.0
