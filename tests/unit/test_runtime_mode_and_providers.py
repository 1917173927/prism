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
from app.providers.fuyao import FuyaoProviderError
from app.providers.live_market import StaticMarketProvider
from app.providers.skillhub import WencaiSkillHubProvider
from app.runtime.mode import (
    DataMode,
    LiveProviderUnavailableError,
    ModeRevisionConflictError,
    RuntimeModeController,
    get_runtime_mode_controller,
    reset_runtime_mode_controller,
)


@pytest.fixture(autouse=True)
def clean_env():
    """Ensure clean environment variables for reproducible mode tests."""
    names = (
        "WENCAI_SKILLHUB_API_KEY",
        "WENCAI_SKILLHUB_BASE_URL",
        "WENCAI_SKILLHUB_CONTRACT_VERIFIED",
        "IWENCAI_API_KEY",
        "IWENCAI_BASE_URL",
        "HITHINK_FINANCE_API_KEY",
    )
    old_values = {name: os.environ.get(name) for name in names}
    for name in names:
        os.environ.pop(name, None)
    yield
    for name, value in old_values.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


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

    def test_default_boot_mode_requires_real_probe_before_live(self):
        os.environ["HITHINK_FINANCE_API_KEY"] = "test_fuyao_key"
        controller = RuntimeModeController()
        assert controller.mode == DataMode.MOCK
        assert controller.is_live_ready is False
        assert controller.needs_initial_probe is True
        asyncio.run(controller.apply_fuyao_probe(
            {"stock_quote": True, "fund_lookthrough": True}, auto_activate=True
        ))
        assert controller.mode == DataMode.LIVE
        assert controller.is_live_ready is True
        capabilities = controller.get_status()["capabilities"]["LIVE"]
        assert capabilities["stock_quote"] is True
        assert capabilities["fund_lookthrough"] is True
        assert capabilities["semantic_search"] is False
        assert capabilities["portfolio_refresh"] is False

    def test_wencai_capabilities_can_coexist_without_fuyao(self):
        os.environ["WENCAI_SKILLHUB_API_KEY"] = "test_official_key"
        os.environ["WENCAI_SKILLHUB_CONTRACT_VERIFIED"] = "true"
        controller = RuntimeModeController()
        status = controller.get_status()
        assert status["data_mode"] == "LIVE"
        assert status["live_ready"] is True
        assert status["wencai_ready"] is True
        assert status["capabilities"]["LIVE"]["stock_quote"] is False
        assert status["capabilities"]["LIVE"]["fund_lookthrough"] is False
        assert status["capabilities"]["LIVE"]["semantic_search"] is True
        assert status["capabilities"]["LIVE"]["portfolio_refresh"] is False

    def test_fuyao_and_wencai_capabilities_coexist(self):
        async def _run():
            os.environ["HITHINK_FINANCE_API_KEY"] = "test_fuyao_key"
            os.environ["WENCAI_SKILLHUB_API_KEY"] = "test_official_key"
            os.environ["WENCAI_SKILLHUB_CONTRACT_VERIFIED"] = "true"
            controller = RuntimeModeController()
            await controller.apply_fuyao_probe(
                {"stock_quote": True, "fund_lookthrough": True},
                auto_activate=True,
            )
            capabilities = controller.get_status()["capabilities"]["LIVE"]
            assert controller.mode == DataMode.LIVE
            assert capabilities["stock_quote"] is True
            assert capabilities["fund_lookthrough"] is True
            assert capabilities["semantic_search"] is True
            assert capabilities["portfolio_refresh"] is True

        asyncio.run(_run())

    def test_iwencai_alias_enables_live_capabilities(self, monkeypatch):
        monkeypatch.setenv("IWENCAI_API_KEY", "official-test-key")
        monkeypatch.setenv("WENCAI_SKILLHUB_CONTRACT_VERIFIED", "true")
        controller = RuntimeModeController()
        assert controller.is_wencai_ready is True
        assert controller.get_status()["capabilities"]["LIVE"]["semantic_search"] is True

    def test_wencai_runtime_failure_revokes_only_wencai_capabilities(self):
        async def _run():
            os.environ["HITHINK_FINANCE_API_KEY"] = "test_fuyao_key"
            os.environ["WENCAI_SKILLHUB_API_KEY"] = "test_official_key"
            os.environ["WENCAI_SKILLHUB_CONTRACT_VERIFIED"] = "true"
            controller = RuntimeModeController()
            await controller.apply_fuyao_probe(
                {"stock_quote": True, "fund_lookthrough": True},
                auto_activate=True,
            )

            await controller.record_wencai_failure("AUTH_FAILED")

            status = controller.get_status()
            capabilities = status["capabilities"]["LIVE"]
            assert status["data_mode"] == "LIVE"
            assert status["wencai_ready"] is False
            assert status["wencai_capability_status"]["last_error_code"] == "AUTH_FAILED"
            assert capabilities["semantic_search"] is False
            assert capabilities["portfolio_refresh"] is True
            assert capabilities["stock_quote"] is True
            assert capabilities["fund_lookthrough"] is True

        asyncio.run(_run())

    def test_request_scoped_wencai_failure_does_not_revoke_all_tools(self):
        async def _run():
            os.environ["WENCAI_SKILLHUB_API_KEY"] = "test_official_key"
            os.environ["WENCAI_SKILLHUB_CONTRACT_VERIFIED"] = "true"
            controller = RuntimeModeController(initial_mode=DataMode.LIVE)

            await controller.record_wencai_failure("INVALID_RESPONSE")

            status = controller.get_status()
            assert status["wencai_ready"] is True
            assert status["contract_verified"] is True
            assert status["wencai_capability_status"]["last_error_code"] == "INVALID_RESPONSE"
            assert status["capabilities"]["LIVE"]["market_data"] is True
            assert status["capabilities"]["LIVE"]["fund_data"] is True
            assert status["capabilities"]["LIVE"]["convertible_bond_data"] is True

        asyncio.run(_run())

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
            assert "HITHINK_FINANCE_API_KEY" in str(exc_info.value)
            # Mode and revision must remain unchanged
            assert controller.mode == DataMode.MOCK
            assert controller.revision == 1
        asyncio.run(_run())

    def test_switch_to_live_with_credentials_succeeds(self):
        async def _run():
            os.environ["HITHINK_FINANCE_API_KEY"] = "test_fuyao_key"
            controller = RuntimeModeController(initial_mode=DataMode.MOCK)
            await controller.apply_fuyao_probe(
                {"stock_quote": True, "fund_lookthrough": True}
            )
            result = await controller.switch_mode("LIVE", expected_revision=1)
            assert result["data_mode"] == "LIVE"
            assert result["revision"] == 2
            assert controller.mode == DataMode.LIVE
            assert controller.revision == 2
        asyncio.run(_run())

    def test_runtime_failure_invalidates_capability_and_keeps_live_fail_closed(self):
        async def _run():
            os.environ["HITHINK_FINANCE_API_KEY"] = "test_fuyao_key"
            controller = RuntimeModeController(initial_mode=DataMode.MOCK)
            await controller.apply_fuyao_probe(
                {"stock_quote": True, "fund_lookthrough": True}
            )
            await controller.switch_mode("LIVE", expected_revision=1)
            await controller.record_fuyao_capability_failure("stock_quote", "FUYAO_2003")
            status = controller.get_status()
            assert status["data_mode"] == "LIVE"
            assert status["live_verification"] == "DEGRADED"
            assert status["live_capability_status"]["stock_quote"]["available"] is False
            assert status["live_capability_status"]["stock_quote"]["last_error_code"] == "FUYAO_2003"
            await controller.record_fuyao_capability_failure(
                "fund_lookthrough", "UPSTREAM_TIMEOUT"
            )
            status = controller.get_status()
            assert status["data_mode"] == "LIVE"
            assert status["live_ready"] is False
            assert status["live_verification"] == "FAILED"

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

    def test_project_manifest_installs_all_official_skill_routes(self):
        provider = WencaiSkillHubProvider(api_key="test")
        routes = {
            (skill["operation"], skill.get("channel")): skill["skill_id"]
            for skill in provider.installed_skills
        }
        assert len(provider.installed_skills) == 9
        assert len({skill["skill_id"] for skill in provider.installed_skills}) == 9
        assert routes[("SEARCH_NEWS", "announcement")] == "announcement-search"
        assert routes[("SEARCH_NEWS", "news")] == "news-search"
        assert routes[("SEARCH_REPORTS", "report")] == "report-search"
        assert routes[("MARKET_DATA", None)] == "hithink-market-query"
        assert routes[("COMPANY_DATA", None)] == "hithink-finance-query"
        assert routes[("INDUSTRY_DATA", None)] == "hithink-industry-query"
        assert routes[("MACRO_DATA", None)] == "hithink-macro-query"
        assert routes[("FUND_DATA", None)] == "hithink-fund-query"
        assert routes[("CONVERTIBLE_BOND_DATA", None)] == "hithink-cb-selector"

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

    def test_configured_provider_success(self, monkeypatch):
        async def _run():
            monkeypatch.setenv("WENCAI_SKILL_ID", "prism-investment-agent")
            provider = WencaiSkillHubProvider(api_key="valid_token", base_url="https://mock.skillhub")
            req = ProviderRequest(
                request_id="req-live-002",
                operation=ProviderOperation.SEARCH_NEWS,
                subject="寒武纪",
            )

            mock_resp = httpx.Response(
                200,
                json={
                    "status_code": 0,
                    "summary": "寒武纪AI芯片产品在算力中心渗透加速",
                    "sentiment": "BULLISH",
                    "confidence": 0.98,
                    "data": [{"code": "688256.SH", "title": "寒武纪芯片供应链报告"}],
                },
                request=httpx.Request("POST", "https://mock.skillhub/v1/comprehensive/search"),
            )

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_resp
                result = await provider.execute(req)
                assert result.status == ProviderStatus.SUCCESS
                assert len(result.records) == 1
                assert result.records[0].fields["summary"] == "寒武纪AI芯片产品在算力中心渗透加速"
                assert result.records[0].fields["sentiment"] == "BULLISH"
                assert mock_post.call_args.args[0] == "https://mock.skillhub/v1/comprehensive/search"
                headers = mock_post.call_args.kwargs["headers"]
                assert headers["X-Claw-Skill-Id"] == "announcement-search"
                assert headers["X-Claw-Plugin-Id"] == "none"
                assert mock_post.call_args.kwargs["json"] == {
                    "query": "寒武纪",
                    "channels": ["announcement"],
                    "app_id": "AIME_SKILL",
                    "size": 10,
                }
        asyncio.run(_run())

    def test_announcement_search_requires_status_code(self):
        async def _run():
            provider = WencaiSkillHubProvider(api_key="valid_token", base_url="https://mock.skillhub")
            req = ProviderRequest(
                request_id="req-live-missing-status",
                operation=ProviderOperation.SEARCH_NEWS,
                subject="公告查询",
            )
            mock_resp = httpx.Response(
                200,
                json={"error": "upstream contract changed"},
                request=httpx.Request("POST", "https://mock.skillhub/v1/comprehensive/search"),
            )
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_resp
                result = await provider.execute(req)
            assert result.status == ProviderStatus.FAILED
            assert result.issues[0].code == ProviderIssueCode.INVALID_RESPONSE

        asyncio.run(_run())

    def test_announcement_search_rejects_nonzero_upstream_status(self):
        async def _run():
            provider = WencaiSkillHubProvider(api_key="valid_token", base_url="https://mock.skillhub")
            req = ProviderRequest(
                request_id="req-live-rejected",
                operation=ProviderOperation.SEARCH_NEWS,
                subject="无效公告查询",
            )
            mock_resp = httpx.Response(
                200,
                json={"status_code": 1001, "status_msg": "invalid request", "data": []},
                request=httpx.Request("POST", "https://mock.skillhub/v1/comprehensive/search"),
            )
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_resp
                result = await provider.execute(req)
            assert result.status == ProviderStatus.FAILED
            assert result.records == ()
            assert result.issues[0].code == ProviderIssueCode.INVALID_RESPONSE

        asyncio.run(_run())

    def test_announcement_search_normalizes_invalid_limit(self):
        async def _run():
            provider = WencaiSkillHubProvider(api_key="valid_token", base_url="https://mock.skillhub")
            req = ProviderRequest(
                request_id="req-live-invalid-limit",
                operation=ProviderOperation.SEARCH_NEWS,
                subject="公告查询",
                parameters={"limit": "invalid"},
            )
            mock_resp = httpx.Response(
                200,
                json={"status_code": 0, "data": []},
                request=httpx.Request("POST", "https://mock.skillhub/v1/comprehensive/search"),
            )
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_resp
                result = await provider.execute(req)
            assert result.status == ProviderStatus.EMPTY
            assert mock_post.call_args.kwargs["json"]["size"] == 10

        asyncio.run(_run())

    def test_official_iwencai_alias_and_query_contract(self, monkeypatch):
        async def _run():
            monkeypatch.setenv("IWENCAI_API_KEY", "official-test-key")
            monkeypatch.setenv("IWENCAI_BASE_URL", "https://openapi.iwencai.com")
            provider = WencaiSkillHubProvider()
            req = ProviderRequest(
                request_id="req-iwencai-001",
                operation=ProviderOperation.MARKET_DATA,
                subject="今日涨幅最大的5只A股",
            )
            mock_resp = httpx.Response(
                200,
                json={
                    "status_code": 0,
                    "query": req.subject,
                    "columns": [{"key": "股票代码", "label": "code"}],
                    "datas": [{"股票代码": "300750.SZ", "股票简称": "宁德时代"}],
                    "row_count": 1,
                    "code_count": 1,
                    "chunks_info": [],
                },
                request=httpx.Request("POST", "https://openapi.iwencai.com/v1/query2data"),
            )
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_resp
                result = await provider.execute(req)
                assert result.status == ProviderStatus.SUCCESS
                assert result.records[0].fields["items"][0]["股票代码"] == "300750.SZ"
                called_url = mock_post.call_args.args[0]
                assert called_url == "https://openapi.iwencai.com/v1/query2data"
                headers = mock_post.call_args.kwargs["headers"]
                assert headers["Authorization"] == "Bearer official-test-key"
                assert headers["X-Claw-Skill-Id"] == "hithink-market-query"
                assert headers["X-Claw-Skill-Version"] == "1.0.0"
                assert headers["X-Claw-Plugin-Id"] == "none"
                assert headers["X-Claw-Plugin-Version"] == "none"
                assert mock_post.call_args.kwargs["json"] == {
                    "query": req.subject,
                    "page": "1",
                    "limit": "10",
                    "is_cache": "1",
                    "expand_index": "true",
                }

        asyncio.run(_run())

    def test_report_search_uses_official_skill_contract(self, monkeypatch):
        async def _run():
            monkeypatch.setenv("WENCAI_SKILL_ID", "prism-investment-agent")
            provider = WencaiSkillHubProvider(api_key="valid_token", base_url="https://mock.skillhub")
            req = ProviderRequest(
                request_id="req-report-001",
                operation=ProviderOperation.SEARCH_REPORTS,
                subject="新能源行业研报",
            )
            mock_resp = httpx.Response(
                200,
                json={"status_code": 0, "data": [{"title": "新能源行业研究"}]},
                request=httpx.Request("POST", "https://mock.skillhub/v1/comprehensive/search"),
            )
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_resp
                result = await provider.execute(req)
            assert result.status == ProviderStatus.SUCCESS
            headers = mock_post.call_args.kwargs["headers"]
            assert headers["X-Claw-Skill-Id"] == "report-search"
            assert headers["X-Claw-Plugin-Id"] == "none"
            assert mock_post.call_args.kwargs["json"] == {
                "query": "新能源行业研报",
                "channels": ["report"],
                "app_id": "AIME_SKILL",
                "size": 10,
            }

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

    def test_concurrent_initial_gets_commit_only_one_capability_probe(self):
        import httpx
        from app.api.main import create_app

        class SequencedProbeProvider:
            is_configured = True

            def __init__(self) -> None:
                self.calls = 0

            async def probe_capabilities(self):
                self.calls += 1
                await asyncio.sleep(0.02)
                return (
                    {"stock_quote": True, "fund_lookthrough": True}
                    if self.calls == 1
                    else {"stock_quote": False, "fund_lookthrough": False}
                )

        async def _run():
            os.environ["HITHINK_FINANCE_API_KEY"] = "test_fuyao_key"
            reset_runtime_mode_controller()
            provider = SequencedProbeProvider()
            api = create_app(live_finance_provider=provider)  # type: ignore[arg-type]
            transport = httpx.ASGITransport(app=api)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                first, second = await asyncio.gather(
                    client.get("/api/v1/runtime/data-mode"),
                    client.get("/api/v1/runtime/data-mode"),
                )
            assert first.status_code == second.status_code == 200
            assert provider.calls == 1
            status = get_runtime_mode_controller().get_status()
            assert status["data_mode"] == "LIVE"
            assert status["live_ready"] is True
            assert status["live_verification"] == "VERIFIED"

        asyncio.run(_run())

    def test_runtime_status_retries_stale_incomplete_fuyao_probe(self):
        import httpx
        from datetime import UTC, datetime, timedelta
        from app.api.main import create_app

        class RecoveringProbeProvider:
            is_configured = True
            last_probe_errors = {}

            def __init__(self) -> None:
                self.calls = 0

            async def probe_capabilities(self):
                self.calls += 1
                return (
                    {"stock_quote": False, "fund_lookthrough": True}
                    if self.calls == 1
                    else {"stock_quote": True, "fund_lookthrough": True}
                )

        async def _run():
            os.environ["HITHINK_FINANCE_API_KEY"] = "test_fuyao_key"
            controller = reset_runtime_mode_controller()
            provider = RecoveringProbeProvider()
            api = create_app(live_finance_provider=provider)  # type: ignore[arg-type]
            transport = httpx.ASGITransport(app=api)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                first = await client.get("/api/v1/runtime/data-mode")
                assert first.status_code == 200
                assert first.json()["data"]["capabilities"]["LIVE"]["stock_quote"] is False
                assert provider.calls == 1

                # A refresh inside the cooldown does not hammer the provider.
                await client.get("/api/v1/runtime/data-mode")
                assert provider.calls == 1

                stale = datetime.now(UTC) - timedelta(seconds=31)
                controller._fuyao_capability_checked_at = {
                    "stock_quote": stale,
                    "fund_lookthrough": stale,
                }
                recovered = await client.get("/api/v1/runtime/data-mode")

            assert recovered.status_code == 200
            assert provider.calls == 2
            status = recovered.json()["data"]
            assert status["capabilities"]["LIVE"]["stock_quote"] is True
            assert status["capabilities"]["LIVE"]["fund_lookthrough"] is True

        asyncio.run(_run())

    def test_concurrent_live_switches_probe_once_and_keep_consistent_state(self):
        import httpx
        from app.api.main import create_app

        class ProbeProvider:
            is_configured = True

            def __init__(self) -> None:
                self.calls = 0

            async def probe_capabilities(self):
                self.calls += 1
                await asyncio.sleep(0.02)
                return {"stock_quote": True, "fund_lookthrough": True}

        async def _run():
            os.environ["HITHINK_FINANCE_API_KEY"] = "test_fuyao_key"
            reset_runtime_mode_controller(mode=DataMode.MOCK)
            provider = ProbeProvider()
            api = create_app(live_finance_provider=provider)  # type: ignore[arg-type]
            transport = httpx.ASGITransport(app=api)
            request = {"target_mode": "LIVE", "expected_revision": 1}
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                first, second = await asyncio.gather(
                    client.put("/api/v1/runtime/data-mode", json=request),
                    client.put("/api/v1/runtime/data-mode", json=request),
                )
            assert sorted((first.status_code, second.status_code)) == [200, 409]
            assert provider.calls == 1
            status = get_runtime_mode_controller().get_status()
            assert status["data_mode"] == "LIVE"
            assert status["live_ready"] is True

        asyncio.run(_run())

    def test_live_endpoint_failure_updates_capability_matrix(self):
        from fastapi.testclient import TestClient
        from app.api.main import create_app

        class FailingQuoteProvider:
            is_configured = True

            async def get_quote(self, _: str):
                raise FuyaoProviderError("FUYAO_2003", "当前接口权限不可用。")

        async def prepare_controller():
            controller = reset_runtime_mode_controller(mode=DataMode.MOCK)
            await controller.apply_fuyao_probe(
                {"stock_quote": True, "fund_lookthrough": True}
            )
            await controller.switch_mode("LIVE", expected_revision=1)

        asyncio.run(prepare_controller())
        api = create_app(live_finance_provider=FailingQuoteProvider())  # type: ignore[arg-type]
        response = TestClient(api).get("/api/v1/copilot/live-quote?symbol=600519")
        assert response.status_code == 503
        status = get_runtime_mode_controller().get_status()
        assert status["data_mode"] == "LIVE"
        assert status["live_verification"] == "DEGRADED"
        assert status["capabilities"]["LIVE"]["stock_quote"] is False
        assert status["capabilities"]["LIVE"]["fund_lookthrough"] is True
        assert status["live_capability_status"]["stock_quote"]["last_error_code"] == "FUYAO_2003"

    def setup_method(self):
        reset_runtime_mode_controller(mode=DataMode.MOCK)

    def teardown_method(self):
        reset_runtime_mode_controller(mode=DataMode.MOCK)

    def test_get_data_mode_endpoint(self):
        from fastapi.testclient import TestClient
        from app.api.main import create_app
        app = create_app()

        client = TestClient(app)
        resp = client.get("/api/v1/runtime/data-mode")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "SUCCESS"
        assert data["data"]["data_mode"] == "MOCK"
        assert data["data"]["revision"] == 1

    def test_put_data_mode_revision_conflict_409(self):
        from fastapi.testclient import TestClient
        from app.api.main import create_app
        app = create_app()

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
        from app.api.main import create_app
        app = create_app()

        client = TestClient(app)
        resp = client.put(
            "/api/v1/runtime/data-mode",
            json={"target_mode": "LIVE", "expected_revision": 1},
        )
        assert resp.status_code == 409
        body = resp.json()
        assert body["status"] == "CONFLICT"
        assert body["error_code"] == "LIVE_PROVIDER_UNAVAILABLE"

    def test_put_data_mode_live_with_credentials_serves_fuyao_quote(self):
        from fastapi.testclient import TestClient
        from app.api.main import create_app
        app = create_app()

        os.environ["HITHINK_FINANCE_API_KEY"] = "test_fuyao_key"
        client = TestClient(app)

        # 1. Switch to LIVE mode
        with patch(
            "app.providers.fuyao.FuyaoFinanceProvider.probe_capabilities",
            new_callable=AsyncMock,
        ) as probe:
            probe.return_value = {"stock_quote": True, "fund_lookthrough": True}
            put_resp = client.put(
                "/api/v1/runtime/data-mode",
                json={"target_mode": "LIVE", "expected_revision": 1},
            )
        assert put_resp.status_code == 200
        assert put_resp.json()["data"]["data_mode"] == "LIVE"
        assert put_resp.json()["data"]["revision"] == 2

        # 2. In LIVE mode, stock quote endpoint uses the server-side Fuyao adapter.
        live_quote = {
            "symbol": "300750.SZ", "name": "宁德时代", "price_cny": 260.0,
            "provider_tier": "LIVE_PRIMARY", "retrieved_at": "2026-09-07T00:00:00+00:00",
            "observed_at": "2026-09-07T00:00:00+00:00", "quote_latency_ms": 12.5,
            "staleness_seconds": 0.0, "missing_fields": [], "is_synthetic": False,
        }
        with patch("app.providers.fuyao.FuyaoFinanceProvider.get_quote", new_callable=AsyncMock) as get_quote:
            get_quote.return_value = live_quote
            quote_resp = client.get("/api/v1/copilot/live-quote?symbol=300750")
        assert quote_resp.status_code == 200
        quote_body = quote_resp.json()
        assert quote_body["status"] == "SUCCESS"
        assert quote_body["data"]["price_cny"] == 260.0
        assert quote_body["execution_context"]["provider"] == "fuyao_finance_api"
        assert quote_body["execution_context"]["data_mode"] == "LIVE"
        assert quote_body["execution_context"]["is_synthetic"] is False

        invalid_live_quote = client.get("/api/v1/copilot/live-quote?symbol=XYZ123")
        assert invalid_live_quote.status_code == 400
        assert invalid_live_quote.json()["error_code"] == "INVALID_SECURITY_CODE"

        evil_suffix = client.get("/api/v1/copilot/live-quote?symbol=300750.EVIL")
        assert evil_suffix.status_code == 400

        from app.providers.live_market import A_SHARE_DATABASE
        A_SHARE_DATABASE.pop("600016", None)
        live_unindexed = dict(live_quote, symbol="600016.SH", name="民生银行")
        with patch("app.providers.fuyao.FuyaoFinanceProvider.get_quote", new_callable=AsyncMock) as get_quote:
            get_quote.return_value = live_unindexed
            index_response = client.post(
                "/api/v1/copilot/auto-index-security?symbol=600016"
            )
        assert index_response.status_code == 200
        assert index_response.json()["data"]["is_synthetic"] is False
        assert index_response.json()["auto_completed"] is False
        assert "600016" not in A_SHARE_DATABASE

        # 3. Switch back to MOCK mode
        mock_resp = client.put(
            "/api/v1/runtime/data-mode",
            json={"target_mode": "MOCK", "expected_revision": 2},
        )
        assert mock_resp.status_code == 200
        assert mock_resp.json()["data"]["data_mode"] == "MOCK"

        # 4. In MOCK mode, stock quote endpoint returns 200 with execution_context
        mock_quote = client.get("/api/v1/copilot/live-quote?symbol=300750")
        assert mock_quote.status_code == 200
        mock_body = mock_quote.json()
        assert mock_body["status"] == "SUCCESS"
        assert mock_body["execution_context"]["data_mode"] == "MOCK"
        assert mock_body["execution_context"]["is_synthetic"] is True

    def test_security_auto_index_and_dependency_completion(self):
        from fastapi.testclient import TestClient
        from app.api.main import create_app
        app = create_app()

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
