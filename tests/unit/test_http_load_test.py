import asyncio

import httpx

from tools.http_load_test import measure, percentile


def test_failure_counts_and_sample_boundaries_are_preserved():
    counter = 0
    def reply(request):
        nonlocal counter
        counter += 1
        if counter == 1:
            raise httpx.ReadTimeout("must not leak secrets", request=request)
        return httpx.Response(503 if counter == 2 else 200)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as client:
            return await measure(client, "http://test/api/health", requests=5, concurrency=2)
    result = asyncio.run(run())
    assert result["completed"] == 3 and result["failed"] == 2
    assert result["error_counts"] == {"ReadTimeout":1, "HTTP_503":1}
    assert result["sample_success_pct"] == 60
    assert result["sla_verified"] is False
    assert "must not leak" not in str(result)
    assert percentile([10, 20], .95) == 19.5
    assert percentile([], .95) is None
