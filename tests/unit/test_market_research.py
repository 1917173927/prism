from datetime import date, timedelta
import math
import pytest
from app.market_research import ResearchMetric, research_metrics


def bars(prices):
    return [{"time": (date(2026, 1, 1) + timedelta(days=i)).isoformat(), "close": p}
            for i, p in enumerate(prices)]


def test_known_returns_drawdown_and_versioned_inputs():
    result = research_metrics(bars([100, 120, 90, 110]), source="independent benchmark", subject="index")
    assert result["daily_return"].value == pytest.approx(100 * (110/90-1), abs=1e-8)
    assert result["maximum_drawdown"].value == -25
    assert result["current_drawdown"].value == pytest.approx(-100/12, abs=1e-8)
    assert result["momentum_20"].value is None
    assert result["momentum_20"].missing_reason == "INSUFFICIENT_DAILY_BARS:21"
    assert result["maximum_drawdown"].snapshot_id != research_metrics(bars([100, 120, 90, 111]), source="independent benchmark", subject="index")["maximum_drawdown"].snapshot_id


def test_twenty_returns_constant_and_geometric_prices():
    constant = research_metrics(bars([10]*21), source="benchmark")
    assert constant["realized_volatility_20"].value == 0
    exponential = research_metrics(bars([100*1.01**i for i in range(21)]), source="benchmark")
    assert exponential["momentum_20"].value == pytest.approx((1.01**20-1)*100, abs=1e-8)
    assert exponential["realized_volatility_20"].value == pytest.approx(0, abs=1e-8)


def test_sample_volatility_against_independent_closed_form():
    returns = [0.01, -0.01]*10
    prices = [100]
    for ret in returns:
        prices.append(prices[-1]*math.exp(ret))
    result = research_metrics(bars(prices), source="benchmark")
    assert result["realized_volatility_20"].value == pytest.approx(math.sqrt(0.002/19)*math.sqrt(252)*100, abs=1e-8)


@pytest.mark.parametrize("prices", [[0], [-1], [float('nan')], [float('inf')]])
def test_illegal_prices_rejected(prices):
    with pytest.raises(ValueError): research_metrics(bars(prices), source="benchmark")


def test_empty_and_invalid_chronology():
    assert all(m.status == "UNAVAILABLE" for m in research_metrics([], source="missing").values())
    for data in [bars([1, 2])[::-1], [bars([1])[0]]*2]:
        with pytest.raises(ValueError): research_metrics(data, source="bad")
    with pytest.raises(ValueError):
        ResearchMetric(value=0, status="UNAVAILABLE", sample_count=0, source="bad", snapshot_id="x")
