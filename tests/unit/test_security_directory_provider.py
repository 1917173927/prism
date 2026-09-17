"""Contract tests for credential-free official security identity lookup."""

from __future__ import annotations

import asyncio

import httpx

from app.providers.security_directory import OfficialSecurityDirectoryProvider


def test_official_directory_resolves_exact_sse_and_szse_names() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.sse.com.cn":
            return httpx.Response(200, text='''
                function get_data(){var _t = new Array();
                _t.push({val:"603693",val2:"江苏新能",val3:"jsxn"});
                return _t;}
            ''')
        assert request.url.host == "www.szse.cn"
        searched = request.url.params["txtDMorJC"]
        data = []
        if searched == "华天科技":
            data = [{
                "agdm": "002185",
                "agjc": "<a href='/certificate/individual/?code=002185'><u>华天科技</u></a>",
            }]
        return httpx.Response(200, json=[{"metadata": {"tabkey": "tab1"}, "data": data}])

    async def run() -> None:
        provider = OfficialSecurityDirectoryProvider(transport=httpx.MockTransport(handler))
        assert await provider.resolve_security_identity("江苏新能") == {
            "asset_id": "603693.SH",
            "name": "江苏新能",
            "market": "SH",
            "source": "Shanghai Stock Exchange security directory",
        }
        assert await provider.resolve_security_identity("华天科技") == {
            "asset_id": "002185.SZ",
            "name": "华天科技",
            "market": "SZ",
            "source": "Shenzhen Stock Exchange A-share directory",
        }

    asyncio.run(run())


def test_official_directory_fails_closed_on_conflicting_exact_matches() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.sse.com.cn":
            return httpx.Response(
                200,
                text='_t.push({val:"603693",val2:"同名证券",val3:"tmzq"});',
            )
        return httpx.Response(200, json=[{
            "metadata": {"tabkey": "tab1"},
            "data": [{"agdm": "002185", "agjc": "<u>同名证券</u>"}],
        }])

    async def run() -> None:
        provider = OfficialSecurityDirectoryProvider(transport=httpx.MockTransport(handler))
        assert await provider.resolve_security_identity("同名证券") is None

    asyncio.run(run())


def test_official_directory_accepts_one_exchange_when_the_other_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.sse.com.cn":
            return httpx.Response(503)
        return httpx.Response(200, json=[{
            "metadata": {"tabkey": "tab1"},
            "data": [{"agdm": "002185", "agjc": "<u>华天科技</u>"}],
        }])

    async def run() -> None:
        provider = OfficialSecurityDirectoryProvider(transport=httpx.MockTransport(handler))
        identity = await provider.resolve_security_identity("华天科技")
        assert identity is not None
        assert identity["asset_id"] == "002185.SZ"

    asyncio.run(run())
