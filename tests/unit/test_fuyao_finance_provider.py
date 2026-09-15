"""Contract tests for the server-side Fuyao financial data adapter."""

from __future__ import annotations

import asyncio
from time import perf_counter

import httpx
import pytest

from app.llm.agent import CopilotAgent
from app.providers.fuyao import CAPABILITY_FAILURE_CODES, FuyaoFinanceProvider, FuyaoProviderError
from app.runtime.mode import DataMode, reset_runtime_mode_controller


def test_fuyao_quote_normalizes_snapshot_and_metadata() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/a-share/prices/snapshot":
            assert request.headers["X-api-key"] == "test-key"
            assert request.url.params["thscodes"] == "600519.SH"
            return httpx.Response(200, json={
                "code": 0,
                "data": {
                    "timestamp": 1788742800000,
                    "item": [{
                        "thscode": "600519.SH", "ticker": "600519",
                        "last_price": 1500.25, "price_change": 10.25,
                        "price_change_ratio_pct": 0.688, "open_price": 1490.0,
                        "high_price": 1510.0, "low_price": 1488.0,
                        "prev_price": 1490.0, "volume": 1234, "turnover": 1850000,
                    }],
                },
            })
        if request.url.path == "/api/meta/tickers/search":
            return httpx.Response(200, json={
                "code": 0,
                "data": {"item": [{
                    "thscode": "600519.SH", "ticker": "600519", "name": "贵州茅台"
                }]},
            })
        raise AssertionError(f"unexpected path: {request.url.path}")

    async def run() -> None:
        provider = FuyaoFinanceProvider(
            api_key="test-key", transport=httpx.MockTransport(handler)
        )
        quote = await provider.get_quote("600519")
        assert quote is not None
        assert quote["symbol"] == "600519.SH"
        assert quote["name"] == "贵州茅台"
        assert quote["price_cny"] == 1500.25
        assert quote["change_pct"] == 0.688
        assert quote["provider_tier"] == "LIVE_PRIMARY"
        assert quote["is_synthetic"] is False
        assert quote["missing_fields"] == ["pe_ttm", "pb", "roe_pct", "valuation_quantile_pct"]

    asyncio.run(run())


def test_fuyao_http_200_business_error_is_rejected() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 2003, "message": "forbidden", "data": None})

    async def run() -> None:
        provider = FuyaoFinanceProvider(
            api_key="test-key", transport=httpx.MockTransport(handler)
        )
        with pytest.raises(FuyaoProviderError) as exc_info:
            await provider.get_quote("600519")
        assert exc_info.value.code == "FUYAO_2003"
        assert "test-key" not in str(exc_info.value)

    asyncio.run(run())


def test_fuyao_quote_enforces_end_to_end_deadline() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.3)
        return httpx.Response(200, json={"code": 0, "data": {"item": []}})

    async def run() -> None:
        provider = FuyaoFinanceProvider(
            api_key="test-key",
            timeout_seconds=0.1,
            transport=httpx.MockTransport(handler),
        )
        started = perf_counter()
        with pytest.raises(FuyaoProviderError) as exc_info:
            await provider.get_quote("600519")
        elapsed = perf_counter() - started
        assert exc_info.value.code == "UPSTREAM_TIMEOUT"
        assert elapsed < 0.25

    asyncio.run(run())


def test_fuyao_rejects_invalid_suffix_without_network_request() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise AssertionError("network must not be called")

    async def run() -> None:
        provider = FuyaoFinanceProvider(
            api_key="test-key", transport=httpx.MockTransport(handler)
        )
        with pytest.raises(FuyaoProviderError) as exc_info:
            await provider.get_quote("300750.EVIL")
        assert exc_info.value.code == "INVALID_SYMBOL"
        assert calls == 0

    asyncio.run(run())


def test_fuyao_rejects_mismatched_symbol_and_missing_timestamp() -> None:
    response_mode = "mismatch"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/meta/tickers/search":
            return httpx.Response(200, json={"code": 0, "data": {"item": []}})
        item = {
            "thscode": "000001.SZ" if response_mode == "mismatch" else "300750.SZ",
            "ticker": "000001" if response_mode == "mismatch" else "300750",
            "last_price": 12.3,
        }
        data = {"item": [item]}
        if response_mode != "missing_timestamp":
            data["timestamp"] = 1788742800000
        return httpx.Response(200, json={"code": 0, "data": data})

    async def run() -> None:
        nonlocal response_mode
        provider = FuyaoFinanceProvider(
            api_key="test-key", transport=httpx.MockTransport(handler)
        )
        with pytest.raises(FuyaoProviderError) as mismatch:
            await provider.get_quote("300750")
        assert mismatch.value.code == "SYMBOL_MISMATCH"
        response_mode = "missing_timestamp"
        with pytest.raises(FuyaoProviderError) as missing_time:
            await provider.get_quote("300750")
        assert missing_time.value.code == "MISSING_TIMESTAMP"

    asyncio.run(run())


def test_fuyao_rejects_nonfinite_quote_values() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/meta/tickers/search":
            return httpx.Response(200, json={"code": 0, "data": {"item": []}})
        return httpx.Response(
            200,
            content=(
                b'{"code":0,"data":{"timestamp":1788742800000,'
                b'"item":[{"thscode":"600519.SH","ticker":"600519",'
                b'"last_price":NaN}]}}'
            ),
            headers={"content-type": "application/json"},
        )

    async def run() -> None:
        provider = FuyaoFinanceProvider(
            api_key="test-key", transport=httpx.MockTransport(handler)
        )
        with pytest.raises(FuyaoProviderError) as exc_info:
            await provider.get_quote("600519")
        assert exc_info.value.code == "INVALID_RESPONSE"

    asyncio.run(run())


def test_fuyao_fund_scope_rejects_non_exchange_fund_without_network() -> None:
    async def run() -> None:
        provider = FuyaoFinanceProvider(api_key="test-key")
        with pytest.raises(FuyaoProviderError) as exc_info:
            await provider.get_fund_lookthrough("025480.OF")
        assert exc_info.value.code == "INVALID_SYMBOL"

    asyncio.run(run())


def test_fuyao_fund_uses_latest_disclosure_and_labels_staleness() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/fund/profile/detail":
            return httpx.Response(200, json={"code": 0, "data": {"item": [{
                "thscode": "510300.SH", "fund_name": "沪深300ETF", "unit_nav": 4.12
            }]}})
        if path == "/api/fund/portfolio/holdings":
            return httpx.Response(200, json={"code": 0, "data": {
                "main_industry": "金融", "stock_ratio_pct": 82.3, "item": [
                    {
                        "thscode": "600519.SH", "stock_name": "贵州茅台",
                        "hold_ratio": 5.1, "position_capital": 1000000,
                        "investment_rank": 1, "asset_type": "stock",
                        "end_date_ms": 1759161600000,
                    },
                    {
                        "thscode": "000001.SZ", "stock_name": "旧期持仓",
                        "hold_ratio": 4.0, "position_capital": 800000,
                        "investment_rank": 2, "asset_type": "stock",
                        "end_date_ms": 1751212800000,
                    },
                ]
            }})
        raise AssertionError(f"unexpected path: {path}")

    async def run() -> None:
        provider = FuyaoFinanceProvider(
            api_key="test-key", transport=httpx.MockTransport(handler)
        )
        fund = await provider.get_fund_lookthrough("510300")
        assert fund is not None
        assert fund["fund_name"] == "沪深300ETF"
        assert fund["top_holdings"][0]["asset_id"] == "600519.SH"
        assert len(fund["top_holdings"]) == 1
        assert fund["top_holdings"][0]["name"] == "贵州茅台"
        assert fund["main_industry"] == "金融"
        assert fund["sector_exposure"] == {}
        assert fund["missing_fields"] == ["sector_exposure"]
        assert fund["holding_disclosure_as_of"].startswith("2025-09-30")
        assert fund["data_freshness_label"] == "PERIODIC_DISCLOSURE"
        assert fund["is_synthetic"] is False
        assert fund["staleness_seconds"] > 0

    asyncio.run(run())


def test_copilot_live_tools_use_injected_fuyao_provider_without_static_fallback() -> None:
    class StubFuyaoProvider:
        async def get_quote(self, symbol: str) -> dict[str, object]:
            assert symbol == "600519"
            return {
                "symbol": "600519.SH",
                "price_cny": 1500.25,
                "is_synthetic": False,
            }

        async def get_fund_lookthrough(self, fund_code: str) -> dict[str, object]:
            assert fund_code == "510300"
            return {
                "fund_code": "510300.SH",
                "top_holdings": [],
                "data_freshness_label": "PERIODIC_DISCLOSURE",
                "is_synthetic": False,
            }

    async def run() -> None:
        reset_runtime_mode_controller(mode=DataMode.LIVE)
        agent = CopilotAgent(live_finance_provider=StubFuyaoProvider())  # type: ignore[arg-type]
        quote = await agent._execute_tool("query_stock_quote", {"symbol": "600519"}, {}, None)
        fund = await agent._execute_tool(
            "query_fund_lookthrough", {"fund_code": "510300"}, {}, None
        )
        assert quote["status"] == "SUCCESS"
        assert quote["execution_context"]["provider"] == "fuyao_finance_api"
        assert quote["execution_context"]["is_synthetic"] is False
        assert fund["status"] == "SUCCESS"
        assert fund["data"]["data_freshness_label"] == "PERIODIC_DISCLOSURE"
        reset_runtime_mode_controller(mode=DataMode.MOCK)

    asyncio.run(run())


def test_copilot_live_tool_reports_provider_failure_without_mock_data() -> None:
    class FailingFuyaoProvider:
        async def get_quote(self, _: str) -> None:
            raise FuyaoProviderError("FUYAO_2003", "实时数据权限校验失败。")

    async def run() -> None:
        reset_runtime_mode_controller(mode=DataMode.LIVE)
        agent = CopilotAgent(live_finance_provider=FailingFuyaoProvider())  # type: ignore[arg-type]
        result = await agent._execute_tool(
            "query_stock_quote", {"symbol": "600519"}, {}, None
        )
        assert result["status"] == "FAILED"
        assert result["error_code"] == "FUYAO_2003"
        assert result["execution_context"]["is_synthetic"] is False
        assert "data" not in result
        reset_runtime_mode_controller(mode=DataMode.MOCK)

    asyncio.run(run())


def test_fuyao_quotes_use_one_bounded_batch_snapshot() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/a-share/prices/snapshot"
        assert request.url.params["thscodes"] == "600519.SH,300750.SZ"
        return httpx.Response(200, json={
            "code": 0,
            "data": {
                "timestamp": 1788742800000,
                "item": [
                    {"thscode": "600519.SH", "ticker": "600519", "last_price": 1500.25},
                    {"thscode": "300750.SZ", "ticker": "300750", "last_price": 338.25},
                ],
            },
        })

    async def run() -> None:
        provider = FuyaoFinanceProvider(
            api_key="test-key", transport=httpx.MockTransport(handler)
        )
        quotes = await provider.get_quotes(["600519", "300750.SZ", "600519.SH"])
        assert set(quotes) == {"600519.SH", "300750.SZ"}
        assert quotes["600519.SH"]["price_cny"] == 1500.25
        assert quotes["300750.SZ"]["price_cny"] == 338.25
        assert quotes["300750.SZ"]["is_synthetic"] is False

    asyncio.run(run())

def test_fuyao_retries_rate_limit_and_keeps_transient_error_out_of_capability_revocation() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        assert request.url.path == "/api/a-share/prices/snapshot"
        attempts += 1
        if attempts < 3:
            return httpx.Response(429, headers={"Retry-After": "0.1"})
        return httpx.Response(200, json={
            "code": 0,
            "data": {
                "timestamp": 1788742800000,
                "item": [{
                    "thscode": "600519.SH", "ticker": "600519", "last_price": 1500.25,
                }],
            },
        })

    async def run() -> None:
        provider = FuyaoFinanceProvider(
            api_key="test-key", transport=httpx.MockTransport(handler)
        )
        quote = await provider.get_quotes(["600519"])
        assert quote["600519.SH"]["price_cny"] == 1500.25
        assert attempts == 3

    asyncio.run(run())
    assert "UPSTREAM_RATE_LIMITED" not in CAPABILITY_FAILURE_CODES

def test_fuyao_probe_serializes_capability_checks_and_avoids_metadata_burst() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        paths.append(path)
        if path == "/api/a-share/prices/snapshot":
            assert request.url.params["thscodes"] == "600519.SH"
            return httpx.Response(200, json={
                "code": 0,
                "data": {
                    "timestamp": 1788742800000,
                    "item": [{
                        "thscode": "600519.SH", "ticker": "600519", "last_price": 1500.25,
                    }],
                },
            })
        if path == "/api/fund/profile/detail":
            return httpx.Response(200, json={
                "code": 0,
                "data": {"item": [{
                    "thscode": "510300.SH", "fund_name": "沪深300ETF", "unit_nav": 4.12,
                }]},
            })
        if path == "/api/fund/portfolio/holdings":
            return httpx.Response(200, json={
                "code": 0,
                "data": {"item": [{
                    "thscode": "600519.SH", "stock_name": "贵州茅台",
                    "hold_ratio": 5.1, "end_date_ms": 1759161600000,
                }]},
            })
        raise AssertionError(f"unexpected path: {path}")

    async def run() -> None:
        provider = FuyaoFinanceProvider(
            api_key="test-key", transport=httpx.MockTransport(handler)
        )
        capabilities = await provider.probe_capabilities()
        assert capabilities == {"stock_quote": True, "fund_lookthrough": True}
        assert paths[0] == "/api/a-share/prices/snapshot"
        assert paths.count("/api/a-share/prices/snapshot") == 1
        assert "/api/meta/tickers/search" not in paths
        assert set(paths[1:]) == {
            "/api/fund/profile/detail", "/api/fund/portfolio/holdings",
        }

    asyncio.run(run())
