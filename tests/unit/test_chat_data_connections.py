"""Regressions for conversational wording and existing data-service connections."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.llm.agent import CopilotAgent
from app.llm.prompts import COPILOT_TOOLS
from app.providers.contracts import ProviderOperation, ProviderStatus
from app.providers.fuyao import FuyaoProviderError
from app.runtime.mode import DataMode, reset_runtime_mode_controller


async def _record_async(target, value):
    target.append(value)


@pytest.mark.parametrize("question", [
    "请用通俗的语言解释一下市盈率", "能不能介绍一下什么是ETF？",
    "我想了解一下资产配置的概念", "请举例说明什么是最大回撤",
])
def test_education_wording_does_not_require_external_data(question):
    assert not CopilotAgent._requires_grounded_tool(question)


@pytest.mark.parametrize("question", [
    "请解释一下贵州茅台的市盈率", "今天ETF的收益率是多少",
    "请解释一下我的持仓风险", "什么是市盈率，今天茅台适合买入吗",
])
def test_live_or_personal_questions_still_require_tools(question):
    assert CopilotAgent._requires_grounded_tool(question)

def test_compound_greeting_does_not_require_tools():
    assert not CopilotAgent._requires_grounded_tool("你好，你是谁，你能干什么")


def test_structured_financial_tool_is_exposed_and_validated():
    assert "query_financial_data" in {t["function"]["name"] for t in COPILOT_TOOLS}
    args, error = CopilotAgent._validate_tool_call(
        "query_financial_data", {"query": "贵州茅台2025年ROE", "category": "company"})
    assert error is None
    assert args["category"] == "company"
    assert CopilotAgent._validate_tool_call(
        "query_financial_data", {"query": "test", "category": "unknown"})[1]


def test_structured_query_preserves_provider_fields(monkeypatch):
    from app.providers.contracts import ProviderStatus
    controller = SimpleNamespace(is_wencai_ready=False)
    monkeypatch.setattr("app.llm.agent.get_runtime_mode_controller", lambda: controller)
    calls = []
    class Provider:
        is_configured = True
        async def execute(self, request):
            calls.append(request)
            return SimpleNamespace(
                status=ProviderStatus.SUCCESS,
                records=[SimpleNamespace(fields={"items": [{"股票代码": "600519", "净资产收益率[2025]": 25.1}]})],
                issues=[], missing_fields=(), retrieved_at=SimpleNamespace(isoformat=lambda: "2026-09-15T00:00:00Z"),
            )
    agent = CopilotAgent(skillhub_provider=Provider())
    args = {"query": "贵州茅台2025年ROE", "category": "company"}
    result = asyncio.run(agent._execute_tool("query_financial_data", args, {}, None, DataMode.LIVE))
    assert calls[0].operation == ProviderOperation.COMPANY_DATA
    assert result["items"][0]["净资产收益率[2025]"] == 25.1
    answer = agent._synthesize_grounded_response("ROE", {}, [{"tool": "query_financial_data", "result": result}], None)
    assert "25.1" in answer and "净资产收益率[2025]" in answer


def test_stock_quote_uses_global_wencai_when_fuyao_is_unconfigured(monkeypatch):
    failures = []
    controller = SimpleNamespace(
        mode=DataMode.LIVE,
        record_fuyao_capability_failure=lambda capability, code: _record_async(
            failures, (capability, code)
        ),
    )
    monkeypatch.setattr("app.llm.agent.get_runtime_mode_controller", lambda: controller)

    class FuyaoUnavailable:
        async def get_quote(self, _symbol):
            raise FuyaoProviderError("NOT_CONFIGURED", "missing")

        get_stock_research = get_quote

    class Wencai:
        is_configured = True

        async def execute(self, request):
            assert request.operation == ProviderOperation.COMPANY_DATA
            assert request.subject.startswith("300750.SZ ")
            return SimpleNamespace(
                status=ProviderStatus.SUCCESS,
                records=[SimpleNamespace(fields={"items": [{
                    "股票代码": "300750.SZ", "股票简称": "宁德时代",
                    "最新价": 337.11, "所属同花顺行业": "电力设备",
                    "净资产收益率(ROE)": "18.5%",
                }]})],
                retrieved_at=SimpleNamespace(isoformat=lambda: "2026-09-16T00:00:00Z"),
            )

    agent = CopilotAgent(
        live_finance_provider=FuyaoUnavailable(), skillhub_provider=Wencai()
    )
    result = asyncio.run(agent._execute_tool(
        "query_stock_quote", {"symbol": "300750"}, {}, None, DataMode.LIVE
    ))

    assert result["status"] == "SUCCESS"
    assert result["execution_context"]["provider"] == "wencai_skillhub_provider"
    assert result["data"]["symbol"] == "300750.SZ"
    assert result["data"]["name"] == "宁德时代"
    assert result["data"]["price_cny"] == 337.11
    assert failures == [("stock_quote", "NOT_CONFIGURED")]


def test_fund_name_screen_uses_wencai_instead_of_sending_name_to_fuyao(monkeypatch):
    controller = SimpleNamespace(mode=DataMode.LIVE)
    monkeypatch.setattr("app.llm.agent.get_runtime_mode_controller", lambda: controller)
    calls = []

    class Fuyao:
        async def get_fund_lookthrough(self, _fund_code):
            raise AssertionError("a semantic fund name must not reach Fuyao code validation")

    class Wencai:
        is_configured = True

        async def execute(self, request):
            calls.append(request)
            return SimpleNamespace(
                status=ProviderStatus.SUCCESS,
                records=[SimpleNamespace(fields={"items": [
                    {"基金代码": "510880.SH", "基金简称": "华泰柏瑞上证红利ETF"},
                    {"基金代码": "515180.SH", "基金简称": "易方达中证红利ETF"},
                ]})],
                issues=(), missing_fields=(),
                retrieved_at=SimpleNamespace(
                    isoformat=lambda: "2026-09-17T00:00:00+00:00"
                ),
            )

    agent = CopilotAgent(
        live_finance_provider=Fuyao(), skillhub_provider=Wencai()
    )
    result = asyncio.run(agent._execute_tool(
        "query_fund_lookthrough", {"fund_code": "红利ETF"}, {}, None, DataMode.LIVE
    ))

    assert result["status"] == "SUCCESS"
    assert result["execution_context"]["provider_serving_mode"] == "LIVE_NAME_SCREEN"
    assert [row["基金代码"] for row in result["items"]] == ["510880.SH", "515180.SH"]
    assert len(calls) == 1
    assert calls[0].operation == ProviderOperation.FUND_DATA
    assert "披露持仓" not in calls[0].subject
    assert "基金代码 基金简称 单位净值" in calls[0].subject
    answer = agent._synthesize_grounded_response(
        "筛选红利ETF", {}, [{"tool": "query_fund_lookthrough", "result": result}], None
    )
    assert "510880.SH" in answer
    assert "筛选结果不等同于单基金持仓穿透" in answer


def test_stock_research_endpoint_uses_wencai_when_fuyao_is_unconfigured():
    reset_runtime_mode_controller(DataMode.LIVE)

    class FuyaoUnavailable:
        async def get_quote(self, _symbol):
            raise FuyaoProviderError("NOT_CONFIGURED", "missing")

        get_stock_research = get_quote

    class Wencai:
        is_configured = True

        async def execute(self, request):
            assert request.operation == ProviderOperation.COMPANY_DATA
            assert request.subject.startswith("300750.SZ ")
            return SimpleNamespace(
                status=ProviderStatus.SUCCESS,
                records=[SimpleNamespace(fields={"items": [{
                    "股票代码": "300750.SZ",
                    "股票简称": "宁德时代",
                    "最新价": 337.11,
                    "所属同花顺行业": "电力设备",
                    "市盈率(TTM)": 25.1,
                    "净资产收益率(ROE)": "18.5%",
                }]})],
                issues=(),
                retrieved_at=SimpleNamespace(
                    isoformat=lambda: "2026-09-16T00:00:00+00:00"
                ),
            )

    with TestClient(create_app(
        live_finance_provider=FuyaoUnavailable(),
        wencai_provider=Wencai(),
    )) as client:
        response = client.get(
            "/api/v1/copilot/live-quote",
            params={"symbol": "300750", "include_financials": "true"},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["execution_context"]["provider"] == "wencai_skillhub_provider"
    assert body["execution_context"]["provider_serving_mode"] == "LIVE_FALLBACK"
    assert body["data"]["symbol"] == "300750.SZ"
    assert body["data"]["name"] == "宁德时代"
    assert body["data"]["price_cny"] == 337.11
    assert body["data"]["industry"] == "电力设备"


def test_generic_industry_wording_is_blocked_before_wencai_stock_screen(monkeypatch):
    controller = SimpleNamespace(mode=DataMode.LIVE)
    monkeypatch.setattr("app.llm.agent.get_runtime_mode_controller", lambda: controller)

    class Wencai:
        is_configured = True

        async def execute(self, _request):
            raise AssertionError("generic industry request must not reach provider")

    result = asyncio.run(CopilotAgent(skillhub_provider=Wencai())._execute_tool(
        "query_financial_data",
        {"query": "行业配置 概念 定义 方法", "category": "industry"},
        {}, None, DataMode.LIVE,
    ))

    assert result["status"] == "BLOCKED"
    assert result["error_code"] == "INDUSTRY_QUERY_UNDERSPECIFIED"
    assert "误执行为选股查询" in result["message"]


def test_invalid_convertible_code_is_rejected_before_wencai_call(monkeypatch):
    controller = SimpleNamespace(mode=DataMode.LIVE)
    monkeypatch.setattr("app.llm.agent.get_runtime_mode_controller", lambda: controller)

    class Wencai:
        is_configured = True

        async def execute(self, _request):
            raise AssertionError("invalid convertible code must not reach provider")

    result = asyncio.run(CopilotAgent(skillhub_provider=Wencai())._execute_tool(
        "query_financial_data",
        {"query": "可转债 114514 最新价格", "category": "convertible_bond"},
        {}, None, DataMode.LIVE,
    ))

    assert result["status"] == "REJECTED"
    assert result["error_code"] == "INVALID_CONVERTIBLE_BOND_CODE"
    assert result["execution_context"]["provider"] == "tool_contract_gate"


@pytest.mark.parametrize("subject", [
    "可转债 114514 最新价格",
    "114514 转债现价 转股价 转股价值 转股溢价率",
])
def test_direct_provider_endpoint_rejects_invalid_convertible_code(subject):
    controller = reset_runtime_mode_controller(DataMode.LIVE)
    asyncio.run(controller.configure_wencai(configured=True, contract_verified=True))

    class Wencai:
        is_configured = True

        async def execute(self, _request):
            raise AssertionError("invalid convertible code must not reach provider")

    with TestClient(create_app(wencai_provider=Wencai())) as client:
        response = client.post("/api/v1/runtime/provider-query", json={
            "request_id": "invalid-convertible-code",
            "operation": "CONVERTIBLE_BOND_DATA",
            "subject": subject,
            "parameters": {"limit": 5},
        })

    assert response.status_code == 422
    assert response.json()["error_code"] == "INVALID_CONVERTIBLE_BOND_CODE"
    assert response.json()["actual_source"] is None


def test_direct_provider_success_recovers_after_previous_runtime_failure():
    controller = reset_runtime_mode_controller(DataMode.LIVE)
    asyncio.run(controller.configure_wencai(configured=True, contract_verified=True))
    asyncio.run(controller.record_wencai_failure("AUTH_FAILED"))
    assert controller.is_wencai_ready is False

    class Wencai:
        is_configured = True

        async def execute(self, request):
            return SimpleNamespace(
                status=ProviderStatus.SUCCESS,
                issues=(),
                model_dump=lambda mode: {
                    "request_id": request.request_id,
                    "provider": "wencai_skillhub_provider",
                    "status": "SUCCESS",
                    "records": [{"fields": {"items": [{"指数代码": "000001.SH"}]}}],
                    "issues": [],
                    "missing_fields": [],
                },
            )

    with TestClient(create_app(wencai_provider=Wencai())) as client:
        response = client.post("/api/v1/runtime/provider-query", json={
            "request_id": "recover-market-route",
            "operation": "MARKET_DATA",
            "subject": "上证指数 最新价",
            "parameters": {"limit": 1},
        })

    assert response.status_code == 200
    assert response.json()["status"] == "SUCCESS"
    assert controller.is_wencai_ready is True


@pytest.mark.parametrize("query", [
    "113056", "可转债 113056 最新价格", "113056 转债现价 转股价",
    "价格低于130元且转股溢价率低于30%",
])
def test_valid_convertible_code_or_screen_reaches_wencai(monkeypatch, query):
    controller = SimpleNamespace(mode=DataMode.LIVE)
    monkeypatch.setattr("app.llm.agent.get_runtime_mode_controller", lambda: controller)
    calls = []

    class Wencai:
        is_configured = True

        async def execute(self, request):
            calls.append(request)
            return SimpleNamespace(
                status=ProviderStatus.EMPTY, records=(), issues=(), missing_fields=(),
                retrieved_at=SimpleNamespace(isoformat=lambda: "2026-09-16T00:00:00Z"),
            )

    result = asyncio.run(CopilotAgent(skillhub_provider=Wencai())._execute_tool(
        "query_financial_data", {"query": query, "category": "convertible_bond"},
        {}, None, DataMode.LIVE,
    ))

    assert result["status"] == "EMPTY"
    assert len(calls) == 1
    assert calls[0].operation == ProviderOperation.CONVERTIBLE_BOND_DATA


@pytest.mark.parametrize("status", ["FAILED", "EMPTY", "PARTIAL"])
def test_structured_query_preserves_non_success_status(monkeypatch, status):
    from app.providers.contracts import ProviderIssueCode, ProviderStatus
    revoked = []
    async def record_failure(code):
        revoked.append(code)
    controller = SimpleNamespace(is_wencai_ready=True, record_wencai_failure=record_failure)
    monkeypatch.setattr("app.llm.agent.get_runtime_mode_controller", lambda: controller)
    class Provider:
        is_configured = True
        async def execute(self, request):
            return SimpleNamespace(
                status=ProviderStatus(status), records=[], missing_fields=("ROE",) if status == "PARTIAL" else (),
                issues=[SimpleNamespace(code=ProviderIssueCode.AUTH_FAILED, safe_message="Credential rejected")] if status == "FAILED" else [],
                retrieved_at=SimpleNamespace(isoformat=lambda: "2026-09-15T00:00:00Z"))
    agent = CopilotAgent(skillhub_provider=Provider())
    result = asyncio.run(agent._execute_tool("query_financial_data", {"query": "ROE", "category": "company"}, {}, None, DataMode.LIVE))
    assert result["status"] == status
    assert revoked == []  # A financial-skill failure does not revoke search.
    answer = agent._synthesize_grounded_response("ROE", {}, [{"tool": "query_financial_data", "result": result}], None)
    assert "鉴权" in answer or "AUTH_FAILED" in answer if status == "FAILED" else "未取得匹配数据" in answer


def test_health_without_locked_context_remains_blocked():
    result = asyncio.run(CopilotAgent()._execute_tool(
        "run_portfolio_health_check", {}, {}, None, DataMode.LIVE))
    assert result["status"] == "BLOCKED"


def test_locked_live_health_uses_deterministic_service_and_rejects_mock():
    from datetime import UTC, datetime
    from decimal import Decimal
    from app.llm.ocr_portfolio_parser import recalculate_portfolio_values
    from app.profile.questionnaire import QUESTIONNAIRE_TEMPLATE, QuestionnaireAnswer, build_questionnaire_snapshot
    answers = [QuestionnaireAnswer.model_validate({"question_id": q.question_id,
        **({"score": 3} if q.question_type.value == "SCORE" else {"selected_option_ids": [q.options[0].option_id]})})
        for q in QUESTIONNAIRE_TEMPLATE.questions]
    snapshot = build_questionnaire_snapshot("owner", tuple(answers), confirmed_at=datetime.now(UTC), snapshot_version=1)
    bundle = recalculate_portfolio_values([{"asset_id": "600519.SH", "quantity": 100, "price": 1000}], Decimal(20000), "owner")["portfolio"]
    context = {"session_truth": {"revision": 1}, "profile": snapshot.profile.model_dump(mode="json"), "portfolio": bundle, "data_mode": "LIVE"}
    agent = CopilotAgent()
    result = asyncio.run(agent._execute_tool("run_portfolio_health_check", {}, {}, context, DataMode.LIVE))
    assert result["status"] == "SUCCESS"
    assert result["health"]["total_market_value_cny"] == "120000.00"
    answer = agent._synthesize_grounded_response("体检", {}, [{"tool": "run_portfolio_health_check", "result": result}], context)
    assert "120000.00" in answer and "HHI" in answer
    assert "减仓" not in answer
    assert "已锁定的持仓快照" in answer
    assert "|\n\n核查时间" in answer
    result["health"]["sectors"][0]["sector_key"] = "UNCLASSIFIED"
    incomplete_answer = agent._synthesize_grounded_response("体检", {}, [{"tool": "run_portfolio_health_check", "result": result}], context)
    assert "行业数据暂缺" in incomplete_answer
    context["data_mode"] = "MOCK"
    assert asyncio.run(agent._execute_tool("run_portfolio_health_check", {}, {}, context, DataMode.LIVE))["status"] == "BLOCKED"


def test_quote_answer_does_not_list_unavailable_financial_fields():
    result = {"status": "SUCCESS", "data": {"name": "贵州茅台", "symbol": "600519.SH", "price_cny": 1272.75},
              "execution_context": {"data_mode": "LIVE", "provider": "fuyao_finance_api"}}
    answer = CopilotAgent()._synthesize_grounded_response(
        "最新股价", {}, [{"tool": "query_stock_quote", "result": result}], None)
    assert "1272.75" in answer
    assert "ROE **未提供" not in answer


@pytest.mark.parametrize("question", [
    "你好，你是谁，你能干什么", "嗨，简单介绍下自己吧", "给我写一段欢迎词",
    "请换一种说法解释刚才的概念", "你支持哪些分析功能？",
])
def test_semantic_routing_allows_general_conversation(monkeypatch, question):
    import json
    import httpx
    from app.llm.client import AsyncLLMClient, LLMConfig
    requests = []
    def respond(request):
        payload = json.loads(request.content)
        requests.append(payload)
        if len(requests) == 1:
            assert payload["tool_choice"]["function"]["name"] == "route_conversation"
            assert payload["thinking"] == {"type": "disabled"}
            delta = {"tool_calls": [{"index": 0, "function": {
                "name": "route_conversation", "arguments": '{"requires_tools":false}'}}]}
        else:
            assert "tools" not in payload
            delta = {"content": "我是 Prism，可以介绍功能并解释概念。"}
        return httpx.Response(200, text="data: " + json.dumps({"choices": [{"delta": delta}]}) + "\n\ndata: [DONE]\n")
    original = httpx.AsyncClient
    monkeypatch.setattr("app.llm.client.httpx.AsyncClient",
                        lambda **kw: original(transport=httpx.MockTransport(respond), **kw))
    async def run():
        agent = CopilotAgent(llm_client=AsyncLLMClient(LLMConfig(api_key="test")))
        return [event async for event in agent.stream_chat(question)]
    events = asyncio.run(run())
    assert len(requests) == 2
    assert any(e["type"] == "token" for e in events)
    assert not any(e["type"] == "error" for e in events)


@pytest.mark.parametrize("route", [True, "true", None])
def test_financial_or_invalid_route_never_exposes_ungrounded_price(monkeypatch, route):
    from app.llm.client import AsyncLLMClient, LLMConfig
    calls = []
    async def stream(self, messages, tools=None, *, tool_choice="auto"):
        calls.append(tool_choice)
        if len(calls) == 1:
            yield {"type": "tool_call", "name": "route_conversation", "arguments": {"requires_tools": route}}
        else:
            assert tool_choice == "required"
            yield {"type": "content", "delta": "股价999元"}
    monkeypatch.setattr(AsyncLLMClient, "stream_chat", stream)
    async def run():
        agent = CopilotAgent(llm_client=AsyncLLMClient(LLMConfig(api_key="test")))
        return [e async for e in agent.stream_chat("你好，查一下宁德时代现在的股价")]
    events = asyncio.run(run())
    assert not any(e["type"] == "token" for e in events)
    assert any(e["type"] == "error" for e in events)
    assert len(calls) == (2 if route is True else 1)
