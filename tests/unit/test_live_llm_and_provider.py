"""Unit tests for Live Market/Wencai providers and Copilot LLM Agent ReAct streaming."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import httpx
from fastapi.testclient import TestClient

from app.api.main import create_app

app = create_app()
from app.llm.agent import CopilotAgent, CopilotMessage
from app.llm.client import AsyncLLMClient, LLMConfig
from app.providers.contracts import FrozenDict, ProviderOperation, ProviderRequest
from app.providers.live_market import LiveMarketProvider
from app.providers.live_wencai import LiveWencaiProvider
from app.runtime.mode import DataMode


def test_real_stream_assembles_fragmented_tool_call(monkeypatch) -> None:
    """OpenAI-compatible streams split tool names and JSON across deltas."""

    payload = "\n".join(
        [
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1","function":{"name":"query_","arguments":"{\\\"sym"}}]}}]}',
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"name":"stock_quote","arguments":"bol\\\":\\\"300750\\\"}"}}]}}]}',
            "data: [DONE]",
            "",
        ]
    ).encode()
    transport = httpx.MockTransport(lambda _: httpx.Response(200, content=payload))
    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        "app.llm.client.httpx.AsyncClient",
        lambda **kwargs: real_async_client(transport=transport, **kwargs),
    )

    async def _run():
        client = AsyncLLMClient(LLMConfig(api_key="test", base_url="https://example.test/v1"))
        return [event async for event in client.stream_chat([{"role": "user", "content": "300750"}], tools=[{"type": "function"}])]

    assert asyncio.run(_run()) == [
        {"type": "tool_call", "name": "query_stock_quote", "arguments": {"symbol": "300750"}}
    ]


def test_real_stream_rejects_malformed_tool_arguments_without_echoing_them(monkeypatch) -> None:
    payload = (
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"name":"query_stock_quote","arguments":"SECRET-not-json"}}]}}]}\n'
        "data: [DONE]\n"
    ).encode()
    transport = httpx.MockTransport(lambda _: httpx.Response(200, content=payload))
    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        "app.llm.client.httpx.AsyncClient",
        lambda **kwargs: real_async_client(transport=transport, **kwargs),
    )

    async def _run():
        client = AsyncLLMClient(LLMConfig(api_key="test", base_url="https://example.test/v1"))
        return [event async for event in client.stream_chat([{"role": "user", "content": "test"}], tools=[{"type": "function"}])]

    events = asyncio.run(_run())
    assert events == [{"type": "error", "message": "模型工具参数未通过校验。"}]
    assert "SECRET" not in json.dumps(events, ensure_ascii=False)


def test_agent_reports_empty_model_completion() -> None:
    class ReasoningOnlyClient:
        is_configured = True

        async def stream_chat(self, messages, tools=None):
            yield {"type": "reasoning", "delta": "private reasoning"}

    async def _run():
        agent = CopilotAgent(llm_client=ReasoningOnlyClient())
        return [event async for event in agent.stream_chat("test")]

    events = asyncio.run(_run())
    assert [event["type"] for event in events] == ["start", "thinking", "error", "done"]
    assert events[-2]["message"] == "模型未返回可用正文或完整工具调用。"


def test_live_tools_never_fall_through_to_mock(monkeypatch) -> None:
    controller = SimpleNamespace(mode=DataMode.LIVE)
    monkeypatch.setattr("app.llm.agent.get_runtime_mode_controller", lambda: controller)

    async def _run():
        agent = CopilotAgent()
        health = await agent._execute_tool("run_portfolio_health_check", {}, {}, None, DataMode.LIVE)
        unknown = await agent._execute_tool("invented_tool", {}, {}, None, DataMode.LIVE)
        secret = await agent._execute_tool(
            "query_stock_quote", {"api_key": "copied-secret"}, {}, None, DataMode.LIVE
        )
        return health, unknown, secret

    health, unknown, secret = asyncio.run(_run())
    assert health["status"] == "BLOCKED"
    for result in (health, unknown, secret):
        assert result["execution_context"]["data_mode"] == "LIVE"
        assert result["execution_context"]["is_synthetic"] is False
        assert "Fixture" not in json.dumps(result, ensure_ascii=False)
        assert "copied-secret" not in json.dumps(result, ensure_ascii=False)


def test_agent_suppresses_unverified_content_and_combines_multiple_tools() -> None:
    class MixedClient:
        is_configured = True

        async def stream_chat(self, messages, tools=None):
            yield {"type": "content", "delta": "未经核验的价格是 999 元"}
            yield {"type": "tool_call", "name": "query_stock_quote", "arguments": {"symbol": "300750"}}
            yield {"type": "tool_call", "name": "query_wencai_semantic", "arguments": {"query": "半导体"}}

    async def _run():
        agent = CopilotAgent(llm_client=MixedClient())
        agent._tokenize_stream = lambda text, chunk_size=4: [text]

        async def execute(name, args, persona, portfolio, data_mode=None):
            if name == "query_stock_quote":
                return {
                    "status": "SUCCESS",
                    "data": {"name": "宁德时代", "symbol": "300750.SZ", "price_cny": 337.11},
                    "execution_context": {"data_mode": "LIVE", "provider": "fuyao", "is_synthetic": False},
                }
            return {
                "status": "SUCCESS",
                "query": args["query"],
                "source": "iwencai.com / SkillHub",
                "summary": "半导体真实检索摘要",
                "execution_context": {"data_mode": "LIVE", "provider": "wencai", "is_synthetic": False},
            }

        agent._execute_tool = execute
        return [event async for event in agent.stream_chat("查询 300750 和半导体行业")]

    events = asyncio.run(_run())
    output = "".join(event.get("delta", "") for event in events if event["type"] == "token")
    assert sum(event["type"] == "tool_start" for event in events) == 2
    assert "337.11" in output and "半导体真实检索摘要" in output
    assert "未经核验的价格" not in output


def test_agent_rejects_content_only_answer_for_financial_query() -> None:
    class ContentOnlyClient:
        is_configured = True

        async def stream_chat(self, messages, tools=None):
            yield {"type": "content", "delta": "300750 当前价格为 999 元"}

    async def _run():
        agent = CopilotAgent(llm_client=ContentOnlyClient())
        return [event async for event in agent.stream_chat("查询 300750 最新行情")]

    events = asyncio.run(_run())
    assert not any(event["type"] == "token" for event in events)
    assert any(event.get("message") == "该问题需要真实金融工具结果，模型未完成工具调用。" for event in events)

    async def _run_named_security():
        agent = CopilotAgent(llm_client=ContentOnlyClient())
        return [event async for event in agent.stream_chat("宁德时代现在多少钱")]

    named_events = asyncio.run(_run_named_security())
    assert not any(event["type"] == "token" for event in named_events)


def test_live_market_provider_stock_quote() -> None:
    async def _run():
        provider = LiveMarketProvider()
        req = ProviderRequest(
            request_id="req-live-stock-001",
            subject="300750",
            operation=ProviderOperation.MARKET_DATA,
            parameters=FrozenDict({"symbol": "300750"}),
            timeout_ms=5000,
        )
        result = await provider.execute(req)
        assert result.status.value == "SUCCESS"
        assert len(result.records) == 1
        rec = result.records[0].fields
        assert rec["symbol"] == "300750.SZ"
        assert rec["name"] == "宁德时代"
        assert rec["price_cny"] > 0
        assert rec["pe_ttm"] > 0

    asyncio.run(_run())


def test_live_market_provider_fund_lookthrough() -> None:
    async def _run():
        provider = LiveMarketProvider()
        req = ProviderRequest(
            request_id="req-live-fund-001",
            subject="588000",
            operation=ProviderOperation.FUND_DATA,
            parameters=FrozenDict({"fund_code": "588000"}),
            timeout_ms=5000,
        )
        result = await provider.execute(req)
        assert result.status.value == "SUCCESS"
        assert len(result.records) == 1
        fund_rec = result.records[0].fields
        assert fund_rec["fund_code"] == "588000.SH"
        assert len(fund_rec["top_holdings"]) >= 3
        assert "中芯国际" in [h["name"] for h in fund_rec["top_holdings"]]

    asyncio.run(_run())


def test_live_wencai_provider() -> None:
    async def _run():
        provider = LiveWencaiProvider()
        assert not provider.is_configured

        req = ProviderRequest(
            request_id="req-live-wc-001",
            subject="半导体龙头股",
            operation=ProviderOperation.MARKET_DATA,
            parameters=FrozenDict({"query": "半导体龙头股"}),
            timeout_ms=5000,
        )
        result = await provider.execute(req)
        # Invariant: When credentials are not provided, operates in skeleton degraded mode
        assert result.status.value == "PARTIAL"
        assert len(result.records) == 1
        fields = result.records[0].fields
        assert "问财" in fields["results_summary"]
        assert fields["connection_mode"] == "SKELETON_UNAVAILABLE"
        assert fields["credential_status"] == "NOT_CONFIGURED"
        assert len(result.issues) == 1
        assert result.issues[0].code.value == "AUTH_FAILED"

        # When configured with API key
        configured_provider = LiveWencaiProvider(api_key="dummy_sk_test")
        assert configured_provider.is_configured

    asyncio.run(_run())


def test_copilot_agent_streaming_and_tool_execution() -> None:
    async def _run():
        agent = CopilotAgent()
        events: list[dict] = []
        async for event in agent.stream_chat(
            user_message="请帮我研判一下 300750 宁德时代目前的估值和财务质地",
            persona_info={"name": "张先生", "tag": "R3 平衡型", "max_drawdown": 15, "budget_cap": "30.0%"},
        ):
            events.append(event)

        event_types = [e["type"] for e in events]
        assert "start" in event_types
        assert "tool_start" in event_types or "token" in event_types
        assert "done" in event_types

    asyncio.run(_run())


def test_copilot_portfolio_parser() -> None:
    async def _run():
        agent = CopilotAgent()
        parsed = await agent.parse_portfolio_from_text(
            "我持有1000股宁德时代，买入价格220元；还有20000份科创50ETF，以及5万元现金"
        )
        assert parsed["cash_cny"] == 50000.0
        assert parsed["parsed_count"] >= 1
        names = [p["name"] for p in parsed["positions"]]
        assert any("宁德时代" in n for n in names)

    asyncio.run(_run())


def test_copilot_http_endpoints() -> None:
    client = TestClient(app)

    # Test Live Quote Endpoint - Valid symbol
    quote_resp = client.get("/api/v1/copilot/live-quote?symbol=688256")
    assert quote_resp.status_code == 200
    quote_data = quote_resp.json()
    assert quote_data["status"] == "SUCCESS"
    assert quote_data["data"]["name"] == "寒武纪"

    # Test Live Quote Endpoint - Newly added benchmark symbols
    smic_resp = client.get("/api/v1/copilot/live-quote?symbol=688981")
    assert smic_resp.status_code == 200
    assert smic_resp.json()["data"]["name"] == "中芯国际"

    cmb_resp = client.get("/api/v1/copilot/live-quote?symbol=600036")
    assert cmb_resp.status_code == 200
    assert cmb_resp.json()["data"]["name"] == "招商银行"

    # Test Live Quote Endpoint - Hard Gate: Invalid Code (114514 / non-standard format) -> 400 REJECTED
    invalid_resp = client.get("/api/v1/copilot/live-quote?symbol=114514")
    assert invalid_resp.status_code == 400
    invalid_data = invalid_resp.json()
    assert invalid_data["status"] == "REJECTED"
    assert invalid_data["error_code"] == "INVALID_SECURITY_CODE"

    invalid_char_resp = client.get("/api/v1/copilot/live-quote?symbol=XYZ123")
    assert invalid_char_resp.status_code == 400
    assert invalid_char_resp.json()["error_code"] == "INVALID_SECURITY_CODE"

    # Test Live Quote Endpoint - Hard Gate: Unrecorded Valid Symbol -> 404 NOT_FOUND
    unrecorded_resp = client.get("/api/v1/copilot/live-quote?symbol=600999")
    assert unrecorded_resp.status_code == 404
    unrecorded_data = unrecorded_resp.json()
    assert unrecorded_data["status"] == "NOT_FOUND"
    assert unrecorded_data["error_code"] == "SECURITY_NOT_FOUND"

    # Test Live Fund Endpoint - Valid ETF
    fund_resp = client.get("/api/v1/copilot/live-fund?fund_code=512480")
    assert fund_resp.status_code == 200
    fund_data = fund_resp.json()
    assert fund_data["status"] == "SUCCESS"
    assert "半导体" in fund_data["data"]["fund_name"]

    # Test Live Fund Endpoint - Newly added ETF
    chinext_fund_resp = client.get("/api/v1/copilot/live-fund?fund_code=159915")
    assert chinext_fund_resp.status_code == 200
    assert "创业板" in chinext_fund_resp.json()["data"]["fund_name"]

    # Test Live Fund Endpoint - Invalid and Unrecorded
    invalid_fund_resp = client.get("/api/v1/copilot/live-fund?fund_code=ABC")
    assert invalid_fund_resp.status_code == 400
    assert invalid_fund_resp.json()["error_code"] == "INVALID_FUND_CODE"

    unsupported_fund_resp = client.get("/api/v1/copilot/live-fund?fund_code=999999")
    assert unsupported_fund_resp.status_code == 400
    assert unsupported_fund_resp.json()["error_code"] == "INVALID_FUND_CODE"

    unrecorded_fund_resp = client.get("/api/v1/copilot/live-fund?fund_code=510999")
    assert unrecorded_fund_resp.status_code == 404
    assert unrecorded_fund_resp.json()["error_code"] == "FUND_NOT_FOUND"

    # Test Parse Portfolio Endpoint
    parse_resp = client.post(
        "/api/v1/copilot/parse-portfolio",
        json={"text": "持有500股贵州茅台和10000份沪深300ETF，现金2万元"},
    )
    assert parse_resp.status_code == 200
    parse_data = parse_resp.json()
    assert parse_data["cash_cny"] == 20000.0
    assert len(parse_data["positions"]) >= 1

    # Test Streaming Chat Endpoint
    chat_resp = client.post(
        "/api/v1/copilot/chat",
        json={
            "message": "我的持仓科技股太多了，请帮我做一下健康体检",
            "model_mode": "MOCK",
            "persona_id": "persona-zhang-r3",
            "persona_info": {"name": "张先生", "tag": "R3 平衡型", "max_drawdown": 15, "budget_cap": "30.0%"},
        },
    )
    assert chat_resp.status_code == 200
    assert "text/event-stream" in chat_resp.headers["content-type"]
    assert "data:" in chat_resp.text
