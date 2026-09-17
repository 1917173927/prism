from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.providers import (
    ProviderOperation,
    ProviderRecord,
    ProviderRequest,
    ProviderResult,
    ProviderServingMode,
    ProviderStatus,
)
from app.providers.fingerprint import compute_request_fingerprint
from app.service.live_stock_analysis import build_live_stock_analysis


NOW = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)


class StockAnalysisProvider:
    is_configured = True

    def __init__(self, *, mismatch: bool = False) -> None:
        self.mismatch = mismatch
        self.requests: list[ProviderRequest] = []

    async def execute(self, request: ProviderRequest) -> ProviderResult:
        self.requests.append(request)
        code = "000001.SZ" if self.mismatch else "600251.SH"
        if request.operation == ProviderOperation.MARKET_DATA:
            days = next(value for value in (20, 60, 120, 250) if f"{value}个交易日" in request.subject)
            items = [{"股票代码": code, f"近{days}个交易日涨跌幅:前复权[20260101-20260916]": {20: 3.2, 60: -4.5, 120: 8.25, 250: 12.5}[days]}]
        elif request.operation == ProviderOperation.COMPANY_DATA and "年报" in request.subject:
            row = {"股票代码": code, "股票简称": "冠农股份"}
            for year, revenue, profit, cash, roe in (
                (2021, 100, 10, 8, 9),
                (2022, 120, 12, 11, 10),
                (2023, 150, 15, 14, 11),
                (2024, 180, 18, 17, 12),
                (2025, 200, 20, 24, 13),
            ):
                row.update({
                    f"营业收入[{year}-12-31]": revenue,
                    f"归属于母公司股东的净利润[{year}-12-31]": profit,
                    f"经营活动产生的现金流量净额[{year}-12-31]": cash,
                    f"净资产收益率(ROE)[{year}-12-31]": roe,
                })
            items = [row]
        elif request.operation == ProviderOperation.COMPANY_DATA and "历史分位" in request.subject:
            items = [{
                "股票代码": code,
                "股票简称": "冠农股份",
                "市盈率(TTM)": 12,
                "市净率": 1.5,
                "市盈率历史分位": 0.4,
                "市净率历史分位": 0.7,
                "所属行业市盈率平均值": 15,
                "所属行业市净率平均值": 2,
            }]
        elif request.operation == ProviderOperation.COMPANY_DATA:
            items = [{
                "股票代码": code,
                "股票简称": "冠农股份",
                "所属同花顺行业": ["农产品加工", "种植业"],
                "最新价": 10.42,
                "最新涨跌幅": -4.31,
                "总市值": 2_100_000_000,
                "最新报告期": "2026-06-30",
                "营业收入": 200,
                "归属于母公司股东的净利润": 20,
                "经营活动产生的现金流量净额": 24,
                "净资产收益率(ROE)": 13,
                "销售毛利率": 18,
                "资产负债率": 31,
                "营业收入同比": 10,
                "归母净利润同比": 11,
            }]
        else:
            channel = request.parameters.get("channel")
            items = [{
                "id": f"{channel}-1",
                "title": f"冠农股份{channel}一",
                "publish_date": "2026-09-15",
                "source_original": "测试信源",
                "url": "https://example.com/item",
                "stock_infos": [{"code": code}],
            }]
        return ProviderResult(
            request_id=request.request_id,
            request_fingerprint=compute_request_fingerprint(request),
            provider="wencai-test",
            status=ProviderStatus.SUCCESS,
            retrieved_at=NOW,
            records=(ProviderRecord(source="wencai-test", fields={"items": items}),),
            serving_mode=ProviderServingMode.DIRECT,
        )


class StructuredFinanceProvider:
    is_configured = True

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def get_stock_research(self, symbol: str) -> dict[str, object]:
        self.calls.append(symbol)
        return {
            "symbol": symbol,
            "name": "冠农股份",
            "price_cny": 10.42,
            "change_pct": -4.31,
            "pe_ttm": 13.0,
            "pb": 1.6,
            "roe_pct": 13.5,
            "gross_margin_pct": 18.5,
            "debt_ratio_pct": 31.5,
            "financial_report_period": "2026-2",
            "observed_at": NOW.isoformat(),
            "retrieved_at": NOW.isoformat(),
            "provider_tier": "LIVE_PRIMARY",
        }


def test_live_stock_analysis_builds_deterministic_sections_without_fixtures() -> None:
    provider = StockAnalysisProvider()
    structured = StructuredFinanceProvider()
    result = asyncio.run(build_live_stock_analysis(
        "600251.SH",
        lookback_years=5,
        provider=provider,
        structured_provider=structured,
        portfolio_data=None,
        profile=None,
        generated_at=NOW,
    ))

    assert result.schema_version == "copilot-stock-analysis.v1"
    assert result.security.symbol == "600251.SH"
    assert result.security.name == "冠农股份"
    assert len(result.sections["fundamentals"].data["annual"]) == 5
    latest = result.sections["fundamentals"].data["latest"]
    assert str(latest["net_margin_pct"]) == "10.00"
    assert str(latest["cash_conversion_pct"]) == "120.00"
    assert str(result.sections["performance"].data["return_60d_pct"]) == "-4.50"
    assert str(result.sections["performance"].data["latest_price_cny"]) == "10.42"
    valuation = result.sections["valuation"].data
    assert str(valuation["pe_historical_percentile_pct"]) == "40.00"
    assert str(valuation["pe_premium_to_industry_pct"]) == "-13.33"
    assert result.sections["evidence"].data["announcements"][0]["url"].startswith("https://")
    assert result.sections["portfolio_fit"].missing_fields == (
        "confirmed_portfolio",
        "confirmed_profile",
    )
    assert len(provider.requests) == 10
    assert structured.calls == ["600251.SH"]
    assert any(
        source.provider == "fuyao_finance_api"
        for source in result.sections["fundamentals"].sources
    )
    assert all(request.operation != "FIXTURE" for request in provider.requests)


def test_live_stock_analysis_rejects_mismatched_security_rows() -> None:
    result = asyncio.run(build_live_stock_analysis(
        "600251.SH",
        lookback_years=5,
        provider=StockAnalysisProvider(mismatch=True),
        portfolio_data=None,
        profile=None,
        generated_at=NOW,
    ))

    assert result.security.symbol == "600251.SH"
    assert result.security.name == "600251.SH"
    assert result.sections["performance"].status.value == "UNAVAILABLE"
    assert result.sections["fundamentals"].status.value == "UNAVAILABLE"
    assert result.sections["valuation"].status.value == "UNAVAILABLE"


def test_fuyao_failure_preserves_wencai_sections_as_partial() -> None:
    class FailedStructuredProvider:
        is_configured = True

        async def get_stock_research(self, _: str) -> dict[str, object]:
            error = RuntimeError("private upstream detail")
            error.code = "UPSTREAM_TIMEOUT"
            error.safe_message = "扶摇数据接口响应超时。"
            raise error

    result = asyncio.run(build_live_stock_analysis(
        "600251.SH",
        lookback_years=5,
        provider=StockAnalysisProvider(),
        structured_provider=FailedStructuredProvider(),
        portfolio_data=None,
        profile=None,
        generated_at=NOW,
    ))

    assert result.status.value == "PARTIAL"
    assert result.sections["performance"].data["latest_price_cny"] is not None
    assert result.sections["fundamentals"].data["annual"]
    assert any(issue.code == "UPSTREAM_TIMEOUT" for issue in result.issues)


def test_evidence_links_allow_only_http_and_https() -> None:
    class UnsafeLinkProvider(StockAnalysisProvider):
        async def execute(self, request: ProviderRequest) -> ProviderResult:
            result = await super().execute(request)
            if request.operation in {ProviderOperation.SEARCH_NEWS, ProviderOperation.SEARCH_REPORTS}:
                item = dict(result.records[0].fields["items"][0])
                item["url"] = "javascript:alert(1)"
                item["stock_infos"] = [dict(value) for value in item["stock_infos"]]
                return result.model_copy(update={
                    "records": (ProviderRecord(source="wencai-test", fields={"items": [item]}),),
                })
            return result

    result = asyncio.run(build_live_stock_analysis(
        "600251.SH",
        lookback_years=5,
        provider=UnsafeLinkProvider(),
        portfolio_data=None,
        profile=None,
        generated_at=NOW,
    ))
    assert result.sections["evidence"].data["news"][0]["url"] is None


def test_stock_analysis_endpoint_is_owner_scoped_and_returns_versioned_contract() -> None:
    from fastapi.testclient import TestClient

    from app.api.main import create_app
    from app.runtime import DataMode
    from app.runtime.mode import reset_runtime_mode_controller

    reset_runtime_mode_controller(mode=DataMode.LIVE)
    try:
        client = TestClient(create_app(wencai_provider=StockAnalysisProvider()))
        response = client.get(
            "/api/v1/copilot/stock-analysis",
            params={"symbol": "600251", "lookback_years": 5, "owner": "forged-owner"},
            headers={"X-Owner-ID": "authorized-owner"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["schema_version"] == "copilot-stock-analysis.v1"
        assert body["security"]["symbol"] == "600251.SH"
        assert set(body["sections"]) == {
            "performance", "fundamentals", "valuation", "evidence", "portfolio_fit"
        }
        assert body["sections"]["portfolio_fit"]["missing_fields"] == [
            "confirmed_portfolio", "confirmed_profile"
        ]
        assert "owner" not in body
    finally:
        reset_runtime_mode_controller(mode=DataMode.MOCK)
