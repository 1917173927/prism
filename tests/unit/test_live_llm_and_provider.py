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
    event_types = [event["type"] for event in events]
    assert event_types.count("grounding_start") == 1
    assert event_types.index("grounding_start") > max(
        index for index, event_type in enumerate(event_types) if event_type == "tool_done"
    )
    assert event_types.index("grounding_start") < event_types.index("token")
    assert "337.11" in output and "半导体真实检索摘要" in output
    assert "未经核验的价格" not in output


def test_wencai_answer_lists_real_records_instead_of_four_generic_fields() -> None:
    agent = CopilotAgent()
    output = agent._synthesize_grounded_response(
        "贵州茅台最新公告",
        {},
        [{
            "tool": "query_wencai_semantic",
            "args": {"query": "贵州茅台最新公告", "channel": "announcement"},
            "result": {
                "status": "SUCCESS",
                "query": "贵州茅台最新公告",
                "channel": "announcement",
                "source": "iwencai.com / SkillHub (Official Live)",
                "retrieved_at": "2026-09-15T00:00:00+00:00",
                "items": [{
                    "title": "贵州茅台2026年半年度报告",
                    "summary": "公司披露半年度报告主要经营信息。",
                    "publish_date": "2026-08-15",
                }],
                "execution_context": {
                    "data_mode": "LIVE", "provider": "wencai_skillhub_provider",
                    "is_synthetic": False,
                },
            },
        }],
        None,
    )
    assert "贵州茅台2026年半年度报告" in output
    assert "公司披露半年度报告主要经营信息" in output
    assert "查询：" not in output
    assert "数据时间：" not in output


def test_explicit_announcement_question_omits_unrequested_quote_template() -> None:
    agent = CopilotAgent()
    common_context = {"data_mode": "LIVE", "is_synthetic": False}
    tools = [
        {
            "tool": "query_stock_quote",
            "args": {"symbol": "600519"},
            "result": {
                "status": "SUCCESS",
                "data": {
                    "name": "贵州茅台", "symbol": "600519.SH",
                    "price_cny": 1277.96, "roe_pct": 18.2, "industry": "白酒",
                },
                "execution_context": {**common_context, "provider": "fuyao_finance_api"},
            },
        },
        {
            "tool": "query_wencai_semantic",
            "args": {"query": "贵州茅台最新公告", "channel": "announcement"},
            "result": {
                "status": "SUCCESS",
                "query": "贵州茅台最新公告",
                "channel": "announcement",
                "source": "iwencai.com / SkillHub (Official Live)",
                "retrieved_at": "2026-09-15T00:00:00+00:00",
                "items": [{"title": "贵州茅台半年度报告", "summary": "报告正文摘要。"}],
                "execution_context": {**common_context, "provider": "wencai_skillhub_provider"},
            },
        },
    ]
    output = agent._synthesize_grounded_response("请概括贵州茅台最新公告", {}, tools, None)
    assert "贵州茅台半年度报告" in output
    assert "研判卡片" in output
    assert "1277.96" in output
    combined_output = agent._synthesize_grounded_response(
        "请概括贵州茅台最新公告并说明 ROE", {}, tools, None
    )
    assert "贵州茅台半年度报告" in combined_output
    assert "研判卡片" in combined_output
    assert "18.2%" in combined_output
    industry_output = agent._synthesize_grounded_response(
        "请给我贵州茅台最新公告并说明所属行业", {}, tools, None
    )
    assert "贵州茅台半年度报告" in industry_output
    assert "研判卡片" in industry_output
    assert "白酒" in industry_output


def test_multi_intent_response_preserves_all_successful_tool_results() -> None:
    agent = CopilotAgent()
    common_context = {"data_mode": "LIVE", "is_synthetic": False}
    tools = [
        {
            "tool": "query_stock_quote",
            "args": {"symbol": "贵州茅台"},
            "result": {
                "status": "SUCCESS",
                "data": {"name": "贵州茅台", "symbol": "600519.SH", "price_cny": 1277.96},
                "execution_context": {**common_context, "provider": "fuyao_finance_api"},
            },
        },
        {
            "tool": "query_wencai_semantic",
            "args": {"query": "贵州茅台最新公告", "channel": "announcement"},
            "result": {
                "status": "SUCCESS",
                "channel": "announcement",
                "query": "贵州茅台最新公告",
                "items": [{"title": "贵州茅台半年度报告", "summary": "报告正文摘要。"}],
                "execution_context": {**common_context, "provider": "wencai_skillhub_provider"},
            },
        },
        {
            "tool": "run_portfolio_health_check",
            "args": {},
            "result": {
                "status": "SUCCESS",
                "is_over_budget": False,
                "tech_exposure_pct": 12.0,
                "budget_cap_pct": 30.0,
                "execution_context": {**common_context, "provider": "deterministic_risk_engine"},
            },
        },
    ]
    output = agent._synthesize_grounded_response("结合最新公告检查我的组合风险", {}, tools, {})
    assert "贵州茅台半年度报告" in output
    assert "持仓健康度核查报告" in output
    assert "1277.96" in output


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
    assert not any(event.get("message") == "该问题需要真实金融工具结果，模型未完成工具调用。" for event in events)
    assert any(event.get("type") == "token" for event in events)

    async def _run_named_security():
        agent = CopilotAgent(llm_client=ContentOnlyClient())
        return [event async for event in agent.stream_chat("宁德时代现在多少钱")]

    named_events = asyncio.run(_run_named_security())
    assert not any(event["type"] == "token" for event in named_events)


def test_agent_allows_general_financial_education_without_live_tool() -> None:
    class ContentOnlyClient:
        is_configured = True

        async def stream_chat(self, messages, tools=None):
            assert "未绑定已锁定的风险画像与持仓快照" in messages[0]["content"]
            assert "张先生" not in messages[0]["content"]
            yield {"type": "content", "delta": "市盈率是股价与每股收益的比值。"}

    async def _run():
        agent = CopilotAgent(llm_client=ContentOnlyClient())
        return [event async for event in agent.stream_chat("什么是市盈率")]

    events = asyncio.run(_run())
    assert "".join(event.get("delta", "") for event in events) == "市盈率是股价与每股收益的比值。"
    assert sum(event["type"] == "research_skipped" for event in events) == 1
    assert not any(event["type"] == "error" for event in events)
    assert CopilotAgent._requires_grounded_tool("解释一下宁德时代") is True
    assert CopilotAgent._requires_grounded_tool("什么是资产配置") is False
    assert CopilotAgent._requires_grounded_tool("市盈率是什么") is False
    assert CopilotAgent._requires_grounded_tool("什么是投资组合") is False
    assert CopilotAgent._requires_grounded_tool("解释一下买入和卖出的区别") is False
    assert CopilotAgent._requires_grounded_tool("什么是基金净值") is False
    assert CopilotAgent._requires_grounded_tool("什么是债券收益率") is False
    assert CopilotAgent._requires_grounded_tool("什么是净资产收益率(ROE)") is False
    assert CopilotAgent._requires_grounded_tool("什么是贵州茅台的市盈率") is True
    assert CopilotAgent._requires_grounded_tool("解释一下600519的市盈率") is True
    assert CopilotAgent._requires_grounded_tool("什么是沪深300市盈率") is True


def test_real_model_turn_pins_tools_to_live_without_global_live_mode(monkeypatch) -> None:
    """Real model chat must not require or consume the workspace MOCK provider."""
    controller = SimpleNamespace(mode=DataMode.MOCK)
    monkeypatch.setattr("app.llm.agent.get_runtime_mode_controller", lambda: controller)

    class ToolClient:
        is_configured = True

        async def stream_chat(self, messages, tools=None):
            assert any(message["content"] == "上一轮问题" for message in messages)
            yield {"type": "tool_call", "name": "query_stock_quote", "arguments": {"symbol": "600519"}}

    async def collect():
        agent = CopilotAgent(llm_client=ToolClient())
        seen = []

        async def execute(name, args, persona, portfolio, data_mode=None):
            seen.append(data_mode)
            return {
                "status": "BLOCKED",
                "execution_context": {"data_mode": "LIVE", "is_synthetic": False},
            }

        agent._execute_tool = execute
        events = [event async for event in agent.stream_chat(
            "继续查询",
            history=[CopilotMessage(role="user", content="上一轮问题")],
            tool_data_mode=DataMode.LIVE,
        )]
        return seen, events

    seen, events = asyncio.run(collect())
    assert seen == [DataMode.LIVE]
    assert any(event["type"] == "tool_done" for event in events)


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
