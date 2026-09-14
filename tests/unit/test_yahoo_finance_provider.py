import asyncio
from datetime import date

import httpx
import pytest

from app.providers.yahoo_finance import YahooFinanceError, YahooFinanceProvider


def _payload(symbol: str) -> dict:
    return {
        "chart": {
            "result": [{
                "meta": {"symbol": symbol},
                "timestamp": [1789084800, 1789344000],
                "indicators": {"quote": [{
                    "open": [100, 103], "high": [104, 106], "low": [99, 102],
                    "close": [103, 105], "volume": [0, 0],
                }]},
            }],
            "error": None,
        }
    }


def test_yahoo_chart_parses_ohlcv_without_credentials():
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert "authorization" not in request.headers
        assert request.headers["user-agent"].startswith("Mozilla/5.0")
        return httpx.Response(200, json=_payload("^GSPC"))

    provider = YahooFinanceProvider(transport=httpx.MockTransport(respond))
    bars = asyncio.run(provider.get_index_history("^GSPC", date(2026, 9, 1), date(2026, 9, 14)))
    quote = asyncio.run(provider.get_index_quote("^GSPC"))

    assert len(requests) == 2
    assert len(bars) == 2
    assert bars[-1]["close"] == 105
    assert bars[-1]["turnover"] is None
    assert quote["symbol"] == "^GSPC"
    assert quote["price"] == 105
    assert str(quote["change_pct"]).startswith("1.9417475728")
    assert quote["source"].startswith("Yahoo Finance非正式接口")


def test_yahoo_chart_rejects_identity_mismatch():
    def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_payload("^DJI"))

    provider = YahooFinanceProvider(transport=httpx.MockTransport(respond))
    with pytest.raises(YahooFinanceError, match="身份"):
        asyncio.run(provider.get_index_history("^GSPC", date(2026, 9, 1), date(2026, 9, 14)))


def test_yahoo_tnx_is_converted_to_percentage_points(monkeypatch):
    monkeypatch.setenv("YAHOO_US10Y_SYMBOL", "^TNX")

    def respond(_: httpx.Request) -> httpx.Response:
        payload = _payload("^TNX")
        payload["chart"]["result"][0]["indicators"]["quote"][0]["close"] = [43.5, 44.0]
        payload["chart"]["result"][0]["indicators"]["quote"][0]["open"] = [43.5, 44.0]
        payload["chart"]["result"][0]["indicators"]["quote"][0]["high"] = [43.5, 44.0]
        payload["chart"]["result"][0]["indicators"]["quote"][0]["low"] = [43.5, 44.0]
        return httpx.Response(200, json=payload)

    provider = YahooFinanceProvider(transport=httpx.MockTransport(respond))
    points = asyncio.run(provider.get_factor_history("us10y", date(2026, 9, 1), date(2026, 9, 14)))
    assert str(points[-1]["value"]) == "4.4"
