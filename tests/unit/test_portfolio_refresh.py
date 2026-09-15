from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.portfolio.contracts import AssetType, PortfolioImportBundle, Position, PositionSnapshot
from app.portfolio.refresh import LivePortfolioProviderAdapter, PortfolioRefreshRequest, refresh_portfolio_live
from app.providers.contracts import (
    ProviderIssue,
    ProviderIssueCode,
    ProviderOperation,
    ProviderRecord,
    ProviderRequest,
    ProviderResult,
    ProviderServingMode,
    ProviderStatus,
)
from app.providers.fingerprint import compute_request_fingerprint
from app.runtime.mode import DataMode, reset_runtime_mode_controller
from app.service import FixturePortfolioOptimizationService


class _LivePortfolioProvider:
    name = "test_iwencai_provider"

    async def execute(self, request: ProviderRequest) -> ProviderResult:
        if request.operation.value == "FUND_DATA":
            return ProviderResult(
                request_id=request.request_id,
                request_fingerprint=compute_request_fingerprint(request),
                provider=self.name,
                status=ProviderStatus.PARTIAL,
                serving_mode=ProviderServingMode.DIRECT,
                retrieved_at=datetime.now(UTC),
                records=(
                    ProviderRecord(
                        source=self.name,
                        fields={
                            "price_cny": "1.25",
                            "observed_at": "2026-09-07T10:00:00+08:00",
                            "sector": "Technology",
                            "name": "测试 ETF",
                        },
                    ),
                ),
                missing_fields=("top_holdings",),
                issues=(),
            )
        return ProviderResult(
            request_id=request.request_id,
            request_fingerprint=compute_request_fingerprint(request),
            provider=self.name,
            status=ProviderStatus.SUCCESS,
            serving_mode=ProviderServingMode.DIRECT,
            retrieved_at=datetime.now(UTC),
            records=(
                ProviderRecord(
                    source=self.name,
                    fields={
                        "price_cny": "12.00",
                        "observed_at": "2026-09-07T10:00:00+08:00",
                        "sector": "Technology",
                        "name": "测试股票",
                    },
                ),
            ),
        )


class _FailedPortfolioProvider:
    name = "failed_iwencai_provider"

    async def execute(self, request: ProviderRequest) -> ProviderResult:
        return ProviderResult(
            request_id=request.request_id,
            request_fingerprint=compute_request_fingerprint(request),
            provider=self.name,
            status=ProviderStatus.FAILED,
            serving_mode=ProviderServingMode.DIRECT,
            retrieved_at=datetime.now(UTC),
            records=(),
            issues=(
                ProviderIssue(
                    code=ProviderIssueCode.AUTH_FAILED,
                    stage="execute",
                    safe_message="test authentication failure",
                    retriable=False,
                ),
            ),
        )


class _RawWencaiPortfolioProvider:
    name = "wencai_skillhub_provider"
    is_configured = True

    def __init__(self, *, industry: object | None = None) -> None:
        self.industry = industry or ["电力设备", "电池", "锂电池"]
        self.requests: list[ProviderRequest] = []

    async def execute(self, request: ProviderRequest) -> ProviderResult:
        self.requests.append(request)
        return ProviderResult(
            request_id=request.request_id,
            request_fingerprint=compute_request_fingerprint(request),
            provider=self.name,
            status=ProviderStatus.SUCCESS,
            serving_mode=ProviderServingMode.DIRECT,
            retrieved_at=datetime.now(UTC),
            records=(ProviderRecord(
                source=self.name,
                fields={
                    "items": [{
                        "股票代码": "300750.SZ",
                        "股票简称": "宁德时代",
                        "最新价": "337.11",
                        "所属同花顺行业": self.industry,
                        "收盘价[20260914]": 337.11,
                    }],
                    "columns": [{
                        "key": "收盘价[20260914]",
                        "timestamp": "20260914",
                        "unit": "元",
                    }],
                },
            ),),
        )


class _LiveFuyaoFinanceProvider:
    async def get_quote(self, code: str):
        return {
            "symbol": code,
            "name": "宁德时代",
            "price_cny": 338.25,
            "observed_at": "2026-09-15T10:30:00+08:00",
            "source": "Fuyao structured financial data API",
            "is_synthetic": False,
        }

    async def get_fund_lookthrough(self, code: str):
        return None


class _SyntheticFuyaoFinanceProvider(_LiveFuyaoFinanceProvider):
    async def get_quote(self, code: str):
        quote = await super().get_quote(code)
        quote["is_synthetic"] = True
        return quote


def _portfolio(asset_type: AssetType = AssetType.STOCK) -> PortfolioImportBundle:
    now = datetime(2026, 9, 7, 9, 0, tzinfo=UTC)
    position = Position(
        position_id="p-1",
        owner_id="refresh-owner",
        asset_id="300750.SZ",
        asset_type=asset_type,
        asset_name="原始名称",
        sector="Industrials",
        quantity=100,
        market_value=1000,
        currency="CNY",
        as_of=now,
        source="user-import",
    )
    cash = Position(
        position_id="cash",
        owner_id="refresh-owner",
        asset_id="CASH-CNY",
        asset_type=AssetType.CASH,
        asset_name="现金",
        quantity=500,
        market_value=500,
        currency="CNY",
        as_of=now,
        source="user-import",
    )
    return PortfolioImportBundle(
        bundle_id="refresh-bundle",
        owner_id="refresh-owner",
        created_at=now,
        position_snapshot=PositionSnapshot(
            snapshot_id="refresh-snapshot",
            owner_id="refresh-owner",
            as_of=now,
            base_currency="CNY",
            source="user-import",
            positions=(position, cash),
        ),
    )


def _request(portfolio: PortfolioImportBundle) -> dict:
    return {
        "schema_version": "portfolio-refresh-request.v1",
        "request_id": "refresh-test",
        "owner_id": portfolio.owner_id,
        "as_of": "2026-09-07T10:01:00+08:00",
        "portfolio": portfolio.model_dump(mode="json"),
    }


def test_live_refresh_recalculates_market_value_without_synthetic_fallback(monkeypatch):
    monkeypatch.setenv("WENCAI_SKILLHUB_API_KEY", "test-key")
    monkeypatch.setenv("WENCAI_SKILLHUB_CONTRACT_VERIFIED", "true")
    reset_runtime_mode_controller(mode=DataMode.LIVE)
    client = TestClient(create_app(wencai_provider=_LivePortfolioProvider()))

    response = client.post(
        "/api/v1/advisor/portfolio/refresh",
        headers={"X-Owner-ID": "refresh-owner"},
        json=_request(_portfolio()),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "COMPLETE"
    assert body["is_synthetic"] is False
    refreshed = body["portfolio"]["position_snapshot"]["positions"][0]
    assert refreshed["market_value"] == "1200.00"
    assert refreshed["source"] == "test_iwencai_provider"


def test_live_refresh_does_not_bind_wencai_latest_price_to_unrelated_column_date(monkeypatch):
    monkeypatch.setenv("WENCAI_SKILLHUB_API_KEY", "test-key")
    monkeypatch.setenv("WENCAI_SKILLHUB_CONTRACT_VERIFIED", "true")
    reset_runtime_mode_controller(mode=DataMode.LIVE)
    provider = _RawWencaiPortfolioProvider()
    client = TestClient(create_app(wencai_provider=provider))

    response = client.post(
        "/api/v1/advisor/portfolio/refresh",
        headers={"X-Owner-ID": "refresh-owner"},
        json=_request(_portfolio()),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "REVIEW_REQUIRED"
    row = next(item for item in body["positions"] if item["asset_id"] == "300750.SZ")
    assert row["observed_at"] is None
    assert body["portfolio"] is None
    assert "observed_at is missing" in body["issues"]
    assert provider.requests[0].subject == "300750.SZ 最新价 所属同花顺行业"
    assert provider.requests[0].required_fields == ()


def test_live_refresh_keeps_fuyao_quote_in_review_without_real_sector_source():
    portfolio = _portfolio()
    request = PortfolioRefreshRequest.model_validate(_request(portfolio))
    adapter = LivePortfolioProviderAdapter(
        _LiveFuyaoFinanceProvider(),
        stock_quote_available=True,
        wencai_available=False,
    )

    body = asyncio.run(refresh_portfolio_live(request, adapter))

    assert body.status == "REVIEW_REQUIRED"
    assert body.is_synthetic is False
    assert body.portfolio is not None
    stock = body.portfolio.position_snapshot.positions[0]
    assert stock.sector == "Unclassified"
    quote = next(row for row in body.positions if row.asset_id == stock.asset_id)
    assert stock.market_value == quote.price_cny * stock.quantity
    assert "sector" in body.missing_fields


def test_live_refresh_combines_fuyao_quote_with_real_wencai_industry():
    portfolio = _portfolio()
    request = PortfolioRefreshRequest.model_validate(_request(portfolio))
    adapter = LivePortfolioProviderAdapter(
        _LiveFuyaoFinanceProvider(),
        stock_quote_available=True,
        wencai_provider=_RawWencaiPortfolioProvider(),
        wencai_available=True,
    )

    body = asyncio.run(refresh_portfolio_live(request, adapter))

    assert body.status == "COMPLETE"
    assert adapter.wencai_metadata_succeeded is True
    refreshed = body.portfolio.position_snapshot.positions[0]
    assert refreshed.market_value == Decimal("33825.00")
    assert refreshed.sector == "Industrials"
    assert "Fuyao structured financial data API" in refreshed.source
    assert "wencai_skillhub_provider" in refreshed.source


def test_fuyao_refresh_records_failed_wencai_industry_capability(monkeypatch):
    monkeypatch.setenv("WENCAI_SKILLHUB_API_KEY", "test-key")
    monkeypatch.setenv("WENCAI_SKILLHUB_CONTRACT_VERIFIED", "true")
    controller = reset_runtime_mode_controller(mode=DataMode.LIVE)
    asyncio.run(controller.apply_fuyao_probe(
        {"stock_quote": True, "fund_lookthrough": False}
    ))
    client = TestClient(create_app(
        wencai_provider=_FailedPortfolioProvider(),
        live_finance_provider=_LiveFuyaoFinanceProvider(),
    ))

    response = client.post(
        "/api/v1/advisor/portfolio/refresh",
        headers={"X-Owner-ID": "refresh-owner"},
        json=_request(_portfolio()),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "REVIEW_REQUIRED"
    assert "test authentication failure" in body["issues"]
    status = client.get("/api/v1/runtime/data-mode").json()["data"]
    assert status["data_mode"] == "LIVE"
    assert status["portfolio_metadata_ready"] is False
    assert status["capabilities"]["LIVE"]["portfolio_refresh"] is False
    assert status["wencai_capability_status"]["last_error_code"] == "AUTH_FAILED"


def test_live_refresh_rejects_synthetic_result_from_structured_provider():
    portfolio = _portfolio()
    request = PortfolioRefreshRequest.model_validate(_request(portfolio))
    adapter = LivePortfolioProviderAdapter(
        _SyntheticFuyaoFinanceProvider(),
        stock_quote_available=True,
    )

    body = asyncio.run(refresh_portfolio_live(request, adapter))

    assert body.status == "REVIEW_REQUIRED"
    assert adapter.wencai_metadata_succeeded is False
    assert body.portfolio is None
    assert any("ValueError" in issue for issue in body.issues)


def test_live_refresh_endpoint_closes_fuyao_price_wencai_sector_and_rebalancing():
    controller = reset_runtime_mode_controller(mode=DataMode.LIVE)
    asyncio.run(controller.apply_fuyao_probe(
        {"stock_quote": True, "fund_lookthrough": False}
    ))
    client = TestClient(create_app(
        wencai_provider=_RawWencaiPortfolioProvider(),
        live_finance_provider=_LiveFuyaoFinanceProvider(),
    ))

    response = client.post(
        "/api/v1/advisor/portfolio/refresh",
        headers={"X-Owner-ID": "refresh-owner"},
        json=_request(_portfolio()),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "COMPLETE"
    stock_row = next(
        row for row in response.json()["positions"] if row["asset_id"] == "300750.SZ"
    )
    assert stock_row["provider"] == "fuyao_finance_api"
    assert controller.is_wencai_ready is False

    refreshed = response.json()["portfolio"]
    questionnaire = FixturePortfolioOptimizationService().template(
        "refresh-owner"
    ).questionnaire.model_dump(mode="json")
    optimization = client.post(
        "/api/v1/advisor/portfolio-optimization-runs",
        headers={"X-Owner-ID": "refresh-owner"},
        json={
            "request_id": "live-optimization-after-refresh",
            "owner_id": "refresh-owner",
            "generated_at": "2026-09-15T10:31:00+08:00",
            "questionnaire": questionnaire,
            "portfolio": refreshed,
            "scenario_id": "BASELINE_READY",
        },
    )
    assert optimization.status_code == 200

    rebalancing = client.post(
        "/api/v1/advisor/rebalancing-runs",
        headers={"X-Owner-ID": "refresh-owner"},
        json={
            "request_id": "live-rebalance-after-refresh",
            "owner_id": "refresh-owner",
            "generated_at": "2026-09-15T10:32:00+08:00",
            "bundle": refreshed,
            "target_weights": {"300750.SZ": "80.00", "CASH-CNY": "20.00"},
            "deadband_pct": "0.50",
            "max_turnover_pct": "100.00",
        },
    )
    assert rebalancing.status_code == 200
    assert rebalancing.json()["schema_version"] == "portfolio-rebalancing-response.v1"


def test_live_refresh_keeps_unknown_wencai_industry_in_review(monkeypatch):
    monkeypatch.setenv("WENCAI_SKILLHUB_API_KEY", "test-key")
    monkeypatch.setenv("WENCAI_SKILLHUB_CONTRACT_VERIFIED", "true")
    reset_runtime_mode_controller(mode=DataMode.LIVE)
    client = TestClient(create_app(
        wencai_provider=_RawWencaiPortfolioProvider(industry=["未知行业"])
    ))

    response = client.post(
        "/api/v1/advisor/portfolio/refresh",
        headers={"X-Owner-ID": "refresh-owner"},
        json=_request(_portfolio()),
    )

    body = response.json()
    assert body["status"] == "REVIEW_REQUIRED"
    assert body["portfolio"] is None
    assert "sector is missing" in body["issues"]


def test_live_refresh_blocks_incomplete_fund_lookthrough(monkeypatch):
    monkeypatch.setenv("WENCAI_SKILLHUB_API_KEY", "test-key")
    monkeypatch.setenv("WENCAI_SKILLHUB_CONTRACT_VERIFIED", "true")
    reset_runtime_mode_controller(mode=DataMode.LIVE)
    client = TestClient(create_app(wencai_provider=_LivePortfolioProvider()))

    response = client.post(
        "/api/v1/advisor/portfolio/refresh",
        headers={"X-Owner-ID": "refresh-owner"},
        json=_request(_portfolio(AssetType.ETF)),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "REVIEW_REQUIRED"
    assert body["portfolio"] is None
    assert "top_holdings" in body["missing_fields"]


def test_live_refresh_failure_revokes_wencai_runtime_capability(monkeypatch):
    monkeypatch.setenv("WENCAI_SKILLHUB_API_KEY", "test-key")
    monkeypatch.setenv("WENCAI_SKILLHUB_CONTRACT_VERIFIED", "true")
    reset_runtime_mode_controller(mode=DataMode.LIVE)
    client = TestClient(create_app(wencai_provider=_FailedPortfolioProvider()))

    response = client.post(
        "/api/v1/advisor/portfolio/refresh",
        headers={"X-Owner-ID": "refresh-owner"},
        json=_request(_portfolio()),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REVIEW_REQUIRED"
    status = client.get("/api/v1/runtime/data-mode").json()["data"]
    # A failed upstream capability must fail closed without silently switching
    # the whole workspace onto synthetic data.
    assert status["data_mode"] == "LIVE"
    assert status["wencai_ready"] is False
    assert status["wencai_ready"] is False
    assert status["capabilities"]["LIVE"]["portfolio_refresh"] is False
    assert status["wencai_capability_status"]["last_error_code"] == "PORTFOLIO_REFRESH_FAILED"


def test_mock_refresh_keeps_fixture_data_explicitly_synthetic(monkeypatch):
    monkeypatch.delenv("WENCAI_SKILLHUB_API_KEY", raising=False)
    monkeypatch.delenv("WENCAI_SKILLHUB_CONTRACT_VERIFIED", raising=False)
    reset_runtime_mode_controller(mode=DataMode.MOCK)
    client = TestClient(create_app())

    portfolio = _portfolio()
    response = client.post(
        "/api/v1/advisor/portfolio/refresh",
        headers={"X-Owner-ID": "refresh-owner"},
        json=_request(portfolio),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data_mode"] == "MOCK"
    assert body["is_synthetic"] is True
    assert body["portfolio"]["bundle_id"] == portfolio.bundle_id


class _BatchedLiveFuyaoFinanceProvider(_LiveFuyaoFinanceProvider):
    def __init__(self) -> None:
        self.batch_calls = 0
        self.single_calls = 0

    async def get_quotes(self, codes):
        self.batch_calls += 1
        return {
            "300750.SZ": {
                "symbol": "300750.SZ",
                "name": "宁德时代",
                "price_cny": 338.25,
                "observed_at": "2026-09-15T10:30:00+08:00",
                "source": "Fuyao structured financial data API",
                "is_synthetic": False,
            }
        }

    async def get_quote(self, code: str):
        self.single_calls += 1
        return await super().get_quote(code)

class _BatchTimeoutLiveFuyaoFinanceProvider(_LiveFuyaoFinanceProvider):
    def __init__(self) -> None:
        self.single_calls = 0

    async def get_quotes(self, codes):
        raise TimeoutError("batch timeout")

    async def get_quote(self, code: str):
        self.single_calls += 1
        return await super().get_quote(code)

class _LiveFundFinanceProvider:
    async def get_quote(self, code: str):
        return None

    async def get_fund_lookthrough(self, code: str):
        return {
            "fund_code": "510300.SH",
            "fund_name": "测试 ETF",
            "net_asset_value_cny": 4.2,
            "top_holdings": [{
                "asset_id": "300750.SZ",
                "name": "宁德时代",
                "weight_pct": 12.5,
                "sector": "Industrials",
            }],
            "observed_at": "2026-06-30T00:00:00+08:00",
            "is_synthetic": False,
            "source": "test fund disclosure",
        }

class _LiveFundWithoutSectorFinanceProvider(_LiveFundFinanceProvider):
    async def get_fund_lookthrough(self, code: str):
        fund = await super().get_fund_lookthrough(code)
        fund["top_holdings"][0]["sector"] = None
        return fund

def test_live_fund_adapter_serializes_derived_coverage_and_keeps_disclosure_time():
    adapter = LivePortfolioProviderAdapter(
        _LiveFundFinanceProvider(),
        fund_lookthrough_available=True,
    )
    request = ProviderRequest(
        request_id="fund-adapter-test",
        operation=ProviderOperation.FUND_DATA,
        subject="510300.SH",
        as_of=datetime(2026, 9, 7, 10, 0, tzinfo=UTC),
        parameters={"asset_id": "510300.SH", "asset_type": "ETF"},
    )

    result = asyncio.run(adapter.execute(request))

    assert result.status == ProviderStatus.SUCCESS
    fields = dict(result.records[0].fields)
    assert fields["coverage_pct"] == 12.5
    assert fields["observed_at"] == "2026-06-30T00:00:00+08:00"

def test_live_fund_refresh_reports_missing_holding_sector_without_false_top_holdings_gap():
    adapter = LivePortfolioProviderAdapter(
        _LiveFundWithoutSectorFinanceProvider(),
        fund_lookthrough_available=True,
    )
    request = PortfolioRefreshRequest.model_validate(_request(_portfolio(AssetType.ETF)))

    response = asyncio.run(refresh_portfolio_live(request, adapter))

    row = next(item for item in response.positions if item.asset_id == "300750.SZ")
    assert response.status == "REVIEW_REQUIRED"
    assert row.missing_fields == ("holding_sector",)
    assert "top_holdings" not in row.missing_fields

def test_live_refresh_uses_one_batch_quote_request_when_provider_supports_it():
    portfolio = _portfolio()
    request = PortfolioRefreshRequest.model_validate(_request(portfolio))
    finance = _BatchedLiveFuyaoFinanceProvider()
    adapter = LivePortfolioProviderAdapter(
        finance,
        stock_quote_available=True,
        wencai_available=False,
    )

    body = asyncio.run(refresh_portfolio_live(request, adapter))

    assert body.status == "REVIEW_REQUIRED"
    assert finance.batch_calls == 1
    assert finance.single_calls == 0

def test_live_refresh_retries_each_quote_after_batch_timeout():
    request = PortfolioRefreshRequest.model_validate(_request(_portfolio()))
    finance = _BatchTimeoutLiveFuyaoFinanceProvider()
    adapter = LivePortfolioProviderAdapter(finance, stock_quote_available=True)

    body = asyncio.run(refresh_portfolio_live(request, adapter))

    assert finance.single_calls == 1
    assert next(row for row in body.positions if row.asset_id == "300750.SZ").price_cny == Decimal("338.25")

def test_live_refresh_uses_real_quote_with_confirmed_sector_when_wencai_fails():
    portfolio = _portfolio()
    confirmed_position = portfolio.position_snapshot.positions[0].model_copy(
        update={"source": "user-confirmed OCR import"}
    )
    portfolio = portfolio.model_copy(update={
        "position_snapshot": portfolio.position_snapshot.model_copy(
            update={"positions": (confirmed_position,)}
        )
    })
    request = PortfolioRefreshRequest.model_validate(_request(portfolio))
    adapter = LivePortfolioProviderAdapter(
        _LiveFuyaoFinanceProvider(),
        stock_quote_available=True,
        wencai_provider=_FailedPortfolioProvider(),
        wencai_available=True,
    )

    body = asyncio.run(refresh_portfolio_live(request, adapter))

    assert body.status == "COMPLETE"
    assert body.is_synthetic is False
    assert adapter.wencai_metadata_succeeded is False
    assert ProviderIssueCode.AUTH_FAILED.value in adapter.wencai_failure_codes
    refreshed = body.portfolio.position_snapshot.positions[0]
    assert refreshed.market_value == Decimal("33825.00")
    assert refreshed.sector == "Industrials"
    assert "user-confirmed sector" in refreshed.source
    row = next(item for item in body.positions if item.asset_id == "300750.SZ")
    assert row.status == "REFRESHED"
    assert row.price_cny == Decimal("338.25")
    assert row.missing_fields == ()


def test_partial_real_quote_report_is_not_trusted_for_optimization():
    controller = reset_runtime_mode_controller(mode=DataMode.LIVE)
    asyncio.run(controller.apply_fuyao_probe({"stock_quote": True, "fund_lookthrough": False}))
    client = TestClient(create_app(live_finance_provider=_LiveFuyaoFinanceProvider()))
    response = client.post("/api/v1/advisor/portfolio/refresh",
        headers={"X-Owner-ID": "refresh-owner"}, json=_request(_portfolio()))
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "REVIEW_REQUIRED"
    assert body["portfolio"] is not None
    assert "sector" in body["missing_fields"]
    questionnaire = FixturePortfolioOptimizationService().template("refresh-owner").questionnaire.model_dump(mode="json")
    result = client.post("/api/v1/advisor/portfolio-optimization-runs",
        headers={"X-Owner-ID": "refresh-owner"}, json={
            "request_id": "incomplete-must-not-optimize", "owner_id": "refresh-owner",
            "generated_at": "2026-09-15T10:31:00+08:00", "questionnaire": questionnaire,
            "portfolio": body["portfolio"], "scenario_id": "BASELINE_READY",
        })
    assert result.status_code == 409
    assert result.json()["error_code"] == "LIVE_PORTFOLIO_REFRESH_REQUIRED"


def test_automatic_industry_completes_refresh_and_persists_only_metadata():
    from app.store import SQLiteDecisionEventStore
    class Industry:
        async def get_industry(self, asset_id):
            return {"sector": "Industrials", "industry": "Battery", "source": "Eastmoney public stock industry", "retrieved_at": "2026-09-15T00:00:00Z"}
    controller = reset_runtime_mode_controller(mode=DataMode.LIVE)
    asyncio.run(controller.apply_fuyao_probe({"stock_quote": True, "fund_lookthrough": False}))
    store = SQLiteDecisionEventStore(":memory:")
    client = TestClient(create_app(store, live_finance_provider=_LiveFuyaoFinanceProvider(), industry_provider=Industry()))
    headers = {"X-Owner-ID": "refresh-owner"}
    original = client.post("/api/v1/copilot/validate-portfolio-ocr", headers=headers, json={
        "owner_id": "refresh-owner", "cash_cny": 1000, "positions": [{"asset_id": "300750.SZ", "quantity": 100, "price": 200, "observed_at": "2026-09-15T00:00:00Z"}],
    }).json()
    response = client.post("/api/v1/advisor/portfolio/refresh", headers=headers,
        json=_request(PortfolioImportBundle.model_validate(original["portfolio"])))
    assert response.status_code == 200
    assert response.json()["status"] == "COMPLETE"
    assert response.json()["portfolio"]["position_snapshot"]["positions"][0]["sector"] == "Industrials"
    saved = store.get_current_portfolio("refresh-owner", "LIVE")
    row = saved["positions"][0]
    assert row["sector"] == "Industrials" and row["sector_source"] == "Eastmoney public stock industry"
    assert row["price"] == 200 and row["quantity"] == 100
    again = client.put("/api/v1/advisor/portfolio/current", headers=headers, json={
        "owner_id": "refresh-owner", "data_mode": "LIVE", "cash_cny": 1000, "positions": saved["positions"]})
    assert again.status_code == 200 and again.json()["positions"][0]["sector"] == "Industrials"
    assert client.patch("/api/v1/advisor/portfolio/sectors", headers=headers, json={}).status_code == 404
    store.close()
