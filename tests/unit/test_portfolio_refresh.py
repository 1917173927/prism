from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.portfolio.contracts import AssetType, PortfolioImportBundle, Position, PositionSnapshot
from app.providers.contracts import (
    ProviderIssue,
    ProviderIssueCode,
    ProviderRecord,
    ProviderRequest,
    ProviderResult,
    ProviderServingMode,
    ProviderStatus,
)
from app.providers.fingerprint import compute_request_fingerprint
from app.runtime.mode import DataMode, reset_runtime_mode_controller


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
    assert status["data_mode"] == "MOCK"
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
