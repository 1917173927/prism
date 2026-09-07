"""Unit tests for RuntimeModeController, WencaiSkillHubProvider, and dual provider registry."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.providers.contracts import (
    ProviderIssueCode,
    ProviderOperation,
    ProviderRequest,
    ProviderStatus,
)
from app.providers.fixture_wencai import FixtureWencaiProvider
from app.providers.live_market import StaticMarketProvider
from app.providers.skillhub import WencaiSkillHubProvider
from app.runtime.mode import (
    DataMode,
    LiveProviderUnavailableError,
    ModeRevisionConflictError,
    RuntimeModeController,
    reset_runtime_mode_controller,
)


@pytest.fixture(autouse=True)
def clean_env():
    """Ensure clean environment variables for reproducible mode tests."""
    old_key = os.environ.get("WENCAI_SKILLHUB_API_KEY")
    old_verified = os.environ.get("WENCAI_SKILLHUB_CONTRACT_VERIFIED")
    if "WENCAI_SKILLHUB_API_KEY" in os.environ:
        del os.environ["WENCAI_SKILLHUB_API_KEY"]
    if "WENCAI_SKILLHUB_CONTRACT_VERIFIED" in os.environ:
        del os.environ["WENCAI_SKILLHUB_CONTRACT_VERIFIED"]
    yield
    if old_key is not None:
        os.environ["WENCAI_SKILLHUB_API_KEY"] = old_key
    elif "WENCAI_SKILLHUB_API_KEY" in os.environ:
        del os.environ["WENCAI_SKILLHUB_API_KEY"]
    if old_verified is not None:
        os.environ["WENCAI_SKILLHUB_CONTRACT_VERIFIED"] = old_verified
    elif "WENCAI_SKILLHUB_CONTRACT_VERIFIED" in os.environ:
        del os.environ["WENCAI_SKILLHUB_CONTRACT_VERIFIED"]


class TestRuntimeModeController:
    """Test process-level RuntimeModeController behavior and revision locks."""

    def test_default_boot_mode_is_mock_without_credentials(self):
        controller = RuntimeModeController()
        assert controller.mode == DataMode.MOCK
        assert controller.revision == 1
        assert not controller.is_live_ready
        status = controller.get_status()
        assert status["data_mode"] == "MOCK"
        assert status["revision"] == 1
        assert status["live_ready"] is False
        assert status["capabilities"]["MOCK"]["stock_quote"] is True
        assert status["capabilities"]["LIVE"]["semantic_search"] is False

    def test_default_boot_mode_is_live_with_credentials(self):
        os.environ["WENCAI_SKILLHUB_API_KEY"] = "test_official_key"
        os.environ["WENCAI_SKILLHUB_CONTRACT_VERIFIED"] = "true"
        controller = RuntimeModeController()
        assert controller.mode == DataMode.LIVE
        assert controller.is_live_ready is True
        assert controller.get_status()["capabilities"]["LIVE"]["semantic_search"] is True

    def test_switch_mode_revision_conflict(self):
        async def _run():
            controller = RuntimeModeController(initial_mode=DataMode.MOCK)
            with pytest.raises(ModeRevisionConflictError) as exc_info:
                await controller.switch_mode("MOCK", expected_revision=999)
            assert "expected revision 999, but current revision is 1" in str(exc_info.value)
        asyncio.run(_run())

    def test_switch_to_live_without_credentials_rejected(self):
        async def _run():
            controller = RuntimeModeController(initial_mode=DataMode.MOCK)
            with pytest.raises(LiveProviderUnavailableError) as exc_info:
                await controller.switch_mode("LIVE", expected_revision=1)
            assert "WENCAI_SKILLHUB_API_KEY" in str(exc_info.value)
            # Mode and revision must remain unchanged
            assert controller.mode == DataMode.MOCK
            assert controller.revision == 1
        asyncio.run(_run())

    def test_switch_to_live_with_credentials_succeeds(self):
        async def _run():
            os.environ["WENCAI_SKILLHUB_API_KEY"] = "sk_live_enterprise_token"
            os.environ["WENCAI_SKILLHUB_CONTRACT_VERIFIED"] = "true"
            controller = RuntimeModeController(initial_mode=DataMode.MOCK)
            result = await controller.switch_mode("LIVE", expected_revision=1)
            assert result["data_mode"] == "LIVE"
            assert result["revision"] == 2
            assert controller.mode == DataMode.LIVE
            assert controller.revision == 2
        asyncio.run(_run())

    def test_switch_same_mode_does_not_increment_revision(self):
        async def _run():
            controller = RuntimeModeController(initial_mode=DataMode.MOCK)
            result = await controller.switch_mode("MOCK", expected_revision=1)
            assert result["data_mode"] == "MOCK"
            assert result["revision"] == 1
        asyncio.run(_run())


class TestWencaiSkillHubProvider:
    """Test official SkillHub adapter error handling and zero-fallback invariant."""

    def test_unconfigured_provider_fails_explicitly(self):
        async def _run():
            provider = WencaiSkillHubProvider(api_key="")
            assert not provider.is_configured
            req = ProviderRequest(
                request_id="req-live-001",
                operation=ProviderOperation.SEARCH_NEWS,
                subject="宁德时代动力电池",
            )
            result = await provider.execute(req)
            assert result.status == ProviderStatus.FAILED
            assert len(result.records) == 0
            assert len(result.issues) == 1
            assert result.issues[0].code == ProviderIssueCode.AUTH_FAILED
            assert "WENCAI_SKILLHUB_API_KEY" in result.missing_fields
        asyncio.run(_run())

    def test_configured_provider_success(self):
        async def _run():
            provider = WencaiSkillHubProvider(api_key="valid_token", base_url="https://mock.skillhub")
            req = ProviderRequest(
                request_id="req-live-002",
                operation=ProviderOperation.SEARCH_NEWS,
                subject="寒武纪",
            )

            mock_resp = httpx.Response(
                200,
                json={
                    "summary": "寒武纪AI芯片产品在算力中心渗透加速",
                    "sentiment": "BULLISH",
                    "confidence": 0.98,
                    "items": [{"code": "688256.SH", "title": "寒武纪芯片供应链报告"}],
                },
                request=httpx.Request("POST", "https://mock.skillhub/semantic/search"),
            )

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_resp
                result = await provider.execute(req)
                assert result.status == ProviderStatus.SUCCESS
                assert len(result.records) == 1
                assert result.records[0].fields["summary"] == "寒武纪AI芯片产品在算力中心渗透加速"
                assert result.records[0].fields["sentiment"] == "BULLISH"
        asyncio.run(_run())

    def test_configured_provider_upstream_429_rate_limit(self):
        async def _run():
            provider = WencaiSkillHubProvider(api_key="valid_token", base_url="https://mock.skillhub")
            req = ProviderRequest(
                request_id="req-live-003",
                operation=ProviderOperation.SEARCH_NEWS,
                subject="五粮液",
            )

            mock_resp = httpx.Response(
                429,
                text="Too Many Requests",
                request=httpx.Request("POST", "https://mock.skillhub/semantic/search"),
            )

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_resp
                result = await provider.execute(req)
                assert result.status == ProviderStatus.FAILED
                assert len(result.issues) == 1
                assert result.issues[0].code == ProviderIssueCode.RATE_LIMITED
                assert result.issues[0].retriable is True
        asyncio.run(_run())

    def test_configured_provider_timeout(self):
        async def _run():
            provider = WencaiSkillHubProvider(api_key="valid_token", base_url="https://mock.skillhub", timeout_seconds=0.1)
            req = ProviderRequest(
                request_id="req-live-004",
                operation=ProviderOperation.SEARCH_NEWS,
                subject="超时测试",
            )

            with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Read timed out")):
                result = await provider.execute(req)
                assert result.status == ProviderStatus.FAILED
                assert len(result.issues) == 1
                assert result.issues[0].code == ProviderIssueCode.TIMEOUT
                assert result.issues[0].retriable is True
        asyncio.run(_run())


class TestDualRegistryProviders:
    """Test FixtureWencaiProvider and StaticMarketProvider metadata."""

    def test_fixture_wencai_provider_marks_synthetic(self):
        async def _run():
            provider = FixtureWencaiProvider()
            assert provider.is_synthetic is True
            req = ProviderRequest(
                request_id="req-fix-001",
                operation=ProviderOperation.SEARCH_NEWS,
                subject="半导体",
            )
            result = await provider.execute(req)
            assert result.status == ProviderStatus.SUCCESS
            assert len(result.records) == 1
            assert result.records[0].fields["is_synthetic"] is True
        asyncio.run(_run())

    def test_static_market_provider_marks_synthetic(self):
        async def _run():
            provider = StaticMarketProvider()
            assert provider.is_synthetic is True
            req = ProviderRequest(
                request_id="req-static-001",
                operation=ProviderOperation.MARKET_DATA,
                subject="300750",
            )
            result = await provider.execute(req)
            assert result.status == ProviderStatus.SUCCESS
            assert len(result.records) == 1
            assert result.records[0].fields["is_synthetic"] is True
        asyncio.run(_run())


class TestRuntimeModeApiEndpoints:
    """Test public runtime data mode HTTP endpoints and execution contexts."""

    def setup_method(self):
        reset_runtime_mode_controller(mode=DataMode.MOCK)

    def teardown_method(self):
        reset_runtime_mode_controller(mode=DataMode.MOCK)

    def test_get_data_mode_endpoint(self):
        from fastapi.testclient import TestClient
        from app.api.main import app

        client = TestClient(app)
        resp = client.get("/api/v1/runtime/data-mode")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "SUCCESS"
        assert data["data"]["data_mode"] == "MOCK"
        assert data["data"]["revision"] == 1

    def test_put_data_mode_revision_conflict_409(self):
        from fastapi.testclient import TestClient
        from app.api.main import app

        client = TestClient(app)
        resp = client.put(
            "/api/v1/runtime/data-mode",
            json={"target_mode": "MOCK", "expected_revision": 999},
        )
        assert resp.status_code == 409
        body = resp.json()
        assert body["status"] == "CONFLICT"
        assert body["error_code"] == "MODE_REVISION_CONFLICT"

    def test_put_data_mode_live_without_credentials_409(self):
        from fastapi.testclient import TestClient
        from app.api.main import app

        client = TestClient(app)
        resp = client.put(
            "/api/v1/runtime/data-mode",
            json={"target_mode": "LIVE", "expected_revision": 1},
        )
        assert resp.status_code == 409
        body = resp.json()
        assert body["status"] == "CONFLICT"
        assert body["error_code"] == "LIVE_PROVIDER_UNAVAILABLE"

    def test_put_data_mode_live_with_verified_credentials_succeeds(self):
        from fastapi.testclient import TestClient
        from app.api.main import app

        os.environ["WENCAI_SKILLHUB_API_KEY"] = "sk_live_enterprise_token"
        os.environ["WENCAI_SKILLHUB_CONTRACT_VERIFIED"] = "true"
        client = TestClient(app)

        # 1. Switch to LIVE mode
        put_resp = client.put(
            "/api/v1/runtime/data-mode",
            json={"target_mode": "LIVE", "expected_revision": 1},
        )
        assert put_resp.status_code == 200
        assert put_resp.json()["data"]["data_mode"] == "LIVE"
        assert put_resp.json()["data"]["revision"] == 2

        # 2. Switch back to MOCK mode
        mock_resp = client.put(
            "/api/v1/runtime/data-mode",
            json={"target_mode": "MOCK", "expected_revision": 2},
        )
        assert mock_resp.status_code == 200
        assert mock_resp.json()["data"]["data_mode"] == "MOCK"

        # 3. In MOCK mode, stock quote endpoint returns 200 with execution_context
        mock_quote = client.get("/api/v1/copilot/live-quote?symbol=300750")
        assert mock_quote.status_code == 200
        mock_body = mock_quote.json()
        assert mock_body["status"] == "SUCCESS"
        assert mock_body["execution_context"]["data_mode"] == "MOCK"
        assert mock_body["execution_context"]["is_synthetic"] is True

    def test_security_auto_index_and_dependency_completion(self):
        from fastapi.testclient import TestClient
        from app.api.main import app

        client = TestClient(app)

        # 1. 601998 (China CITIC Bank) is pre-registered in A_SHARE_DATABASE
        citic_resp = client.get("/api/v1/copilot/live-quote?symbol=601998")
        assert citic_resp.status_code == 200
        citic_data = citic_resp.json()
        assert citic_data["status"] == "SUCCESS"
        assert citic_data["data"]["name"] == "中信银行"
        assert citic_data["data"]["sector"] == "Finance"
        assert citic_data["data"]["pe_ttm"] > 0
        assert citic_data["data"]["pb"] > 0

        # 2. auto-index endpoint with invalid code returns 400
        invalid_resp = client.post("/api/v1/copilot/auto-index-security?symbol=114514")
        assert invalid_resp.status_code == 400
        assert invalid_resp.json()["error_code"] == "INVALID_SECURITY_CODE"

        # 3. auto-index endpoint with valid unindexed code (e.g. 600000) auto-completes
        index_resp = client.post("/api/v1/copilot/auto-index-security?symbol=600000")
        assert index_resp.status_code == 200
        index_data = index_resp.json()
        assert index_data["status"] == "SUCCESS"
        assert index_data["auto_completed"] is True
        assert "data" in index_data
        assert index_data["data"]["symbol"].startswith("600000")

        # 4. Querying live-quote with auto_complete_dependency=true
        auto_quote = client.get("/api/v1/copilot/live-quote?symbol=600016&auto_complete_dependency=true")
        assert auto_quote.status_code == 200
        assert auto_quote.json()["status"] == "SUCCESS"
        assert auto_quote.json()["data"]["symbol"].startswith("600016")
