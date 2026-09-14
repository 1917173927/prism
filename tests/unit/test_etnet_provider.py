import asyncio
import json
from datetime import date

import httpx
import pytest

from app.providers.etnet import EtNetError, EtNetProvider


def _html(code: str = "HSC") -> str:
    payload = {
        "result": [
            [1789034400000, 3600, 3650, 3590, 3640, 1000],
            [1789120800000, 3640, 3680, 3620, 3670, 1200],
        ],
        "tc": "恒生综合指数",
        "sc": "恒生综合指数",
        "eng": "HS Composite",
        "type": "INDEX",
        "code": code,
    }
    return f"<script>var testData_1_Daily = {json.dumps(payload)};</script>"


def test_etnet_public_chart_parses_hk_ohlcv_without_credentials():
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert "authorization" not in request.headers
        assert request.url.params["subtype"] == "HSC"
        return httpx.Response(200, text=_html(), headers={"content-type": "text/html; charset=utf-8"})

    provider = EtNetProvider(transport=httpx.MockTransport(respond))
    bars = asyncio.run(provider.get_index_history("HSC", date(2026, 9, 8), date(2026, 9, 14)))
    quote = asyncio.run(provider.get_index_quote("HSC"))

    assert len(requests) == 2
    assert len(bars) == 2
    assert bars[-1]["close"] == 3670
    assert bars[-1]["turnover"] is None
    assert quote["symbol"] == "HSC"
    assert quote["price"] == 3670
    assert quote["source"].startswith("ET Net公开图表接口")


def test_etnet_chart_rejects_identity_mismatch():
    provider = EtNetProvider(transport=httpx.MockTransport(lambda _: httpx.Response(200, text=_html("TEH"))))
    with pytest.raises(EtNetError, match="身份"):
        asyncio.run(provider.get_index_history("HSC", date(2026, 9, 8), date(2026, 9, 14)))


def test_etnet_rejects_unregistered_symbol():
    provider = EtNetProvider(transport=httpx.MockTransport(lambda _: httpx.Response(200, text=_html())))
    with pytest.raises(EtNetError, match="未登记"):
        asyncio.run(provider.get_index_history("^GSPC", date(2026, 9, 8), date(2026, 9, 14)))
