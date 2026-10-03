import asyncio
from unittest.mock import AsyncMock, patch

import httpx

from app.providers.contracts import ProviderRequest
from app.providers.skillhub import WencaiSkillHubProvider


def test_missing_sentiment_is_not_neutral_or_confident():
    async def scenario():
        provider = WencaiSkillHubProvider(api_key="test-only", base_url="https://mock.skillhub")
        response = httpx.Response(200, json={"status_code": 0, "data": [{"title": "original title"}]},
                                  request=httpx.Request("POST", "https://mock.skillhub"))
        request = ProviderRequest(request_id="missing-sentiment", operation="SEARCH_NEWS", subject="announcement",
                                  required_fields=("sentiment", "confidence"))
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=response):
            result = await provider.execute(request)
        assert result.status.value == "PARTIAL"
        assert result.records[0].fields["sentiment"] is None
        assert result.records[0].fields["confidence"] is None
        assert set(result.missing_fields) == {"sentiment", "confidence"}
    asyncio.run(scenario())
