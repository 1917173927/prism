import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.providers.industry import EastmoneyIndustryProvider
from app.providers.skillhub import WencaiSkillHubProvider
from app.providers.contracts import ProviderOperation, ProviderRequest


def test_industry_is_exactly_matched_and_cached():
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={"success": True, "code": 0, "result": {"data": [{"SECUCODE": "600276.SH", "SECURITY_NAME_ABBR": "恒瑞医药", "EM2016": "医药生物-化学制药-化学制剂"}]}})
    provider = EastmoneyIndustryProvider(httpx.MockTransport(handle))
    async def run():
        first = await provider.get_industry("600276.SH")
        assert first["sector"] == "Consumer"
        assert first["source"] == "Eastmoney public stock industry"
        assert "retrieved_at" in first and "observed_at" not in first
        assert await provider.get_industry("600276.SH") == first
        assert len(calls) == 1
        assert await provider.get_industry("600519.SH") is None
    asyncio.run(run())


@pytest.mark.parametrize("data", [None, {"SECUCODE": "600519.SH", "EM2016": "未知行业"}, {"SECUCODE": "600519.SH", "EM2016": None}])
def test_missing_industry_is_not_invented(data):
    provider = EastmoneyIndustryProvider(httpx.MockTransport(lambda req: httpx.Response(200, json={"success": True, "code": 0, "result": {"data": [data]}})))
    assert asyncio.run(provider.get_industry("600519.SH")) is None


@pytest.mark.parametrize("body,code", [("您今天的次数已用完，建议升级权益", "QUOTA_EXHAUSTED"), ("invalid credential", "AUTH_FAILED")])
def test_daily_quota_http_401_is_distinct_from_invalid_key(body, code):
    provider = WencaiSkillHubProvider(api_key="test-key")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as post:
        post.return_value = httpx.Response(401, text=body)
        result = asyncio.run(provider.execute(ProviderRequest(request_id="quota", operation=ProviderOperation.COMPANY_DATA, subject="test")))
    assert result.issues[0].code.value == code
    if code == "QUOTA_EXHAUSTED":
        assert "无需重新填写 Key" in result.issues[0].safe_message
