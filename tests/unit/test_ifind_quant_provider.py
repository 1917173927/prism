import asyncio
from datetime import date

import httpx

from app.providers.ifind_quant import IFindQuantProvider


def test_ifind_quant_refreshes_token_without_disclosing_it_and_parses_ohlcv():
    requests = []

    def respond(request):
        requests.append(request)
        if request.url.path.endswith("get_access_token"):
            assert request.headers["refresh_token"] == "private-refresh"
            return httpx.Response(200, json={"data": {"access_token": "private-access"}})
        assert request.headers["access_token"] == "private-access"
        return httpx.Response(200, json={"errorcode": 0, "tables": [{
            "thscode": "TEST.GI", "time": ["2026-09-11", "2026-09-14"],
            "table": {"open": [100, 102], "high": [103, 104], "low": [99, 101],
                      "close": [102, 103], "volume": [1000, 1200], "amount": [10000, 13000]},
        }]})

    provider = IFindQuantProvider("private-refresh", transport=httpx.MockTransport(respond))
    bars = asyncio.run(provider.get_index_history("TEST.GI", date(2026, 9, 1), date(2026, 9, 14)))
    assert len(requests) == 2
    assert bars[-1]["close"] == 103
    assert bars[-1]["volume"] == 1200
    assert bars[-1]["turnover"] == 13000


def test_ifind_edb_accepts_indicator_named_value_column(monkeypatch):
    monkeypatch.setenv("IFIND_US10Y_EDB_ID", "M0000612")

    def respond(request):
        if request.url.path.endswith("get_access_token"):
            return httpx.Response(200, json={"data": {"access_token": "access"}})
        return httpx.Response(200, json={"errorcode": 0, "tables": [{
            "time": ["2026-09-11", "2026-09-14"], "table": {"M0000612": [3.65, 3.68]},
        }]})

    provider = IFindQuantProvider("refresh", transport=httpx.MockTransport(respond))
    points = asyncio.run(provider.get_factor_history("us10y", date(2026, 9, 1), date(2026, 9, 14)))
    assert [str(point["value"]) for point in points] == ["3.65", "3.68"]
