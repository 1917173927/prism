"""Regressions for conversational wording and existing data-service connections."""
import asyncio
from types import SimpleNamespace

import pytest

from app.llm.agent import CopilotAgent
from app.llm.prompts import COPILOT_TOOLS
from app.providers.contracts import ProviderOperation
from app.runtime.mode import DataMode


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
                issues=[SimpleNamespace(code=ProviderIssueCode.AUTH_FAILED)] if status == "FAILED" else [],
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
    context["data_mode"] = "MOCK"
    assert asyncio.run(agent._execute_tool("run_portfolio_health_check", {}, {}, context, DataMode.LIVE))["status"] == "BLOCKED"


def test_quote_answer_does_not_list_unavailable_financial_fields():
    result = {"status": "SUCCESS", "data": {"name": "贵州茅台", "symbol": "600519.SH", "price_cny": 1272.75},
              "execution_context": {"data_mode": "LIVE", "provider": "fuyao_finance_api"}}
    answer = CopilotAgent()._synthesize_grounded_response(
        "最新股价", {}, [{"tool": "query_stock_quote", "result": result}], None)
    assert "1272.75" in answer
    assert "ROE **未提供" not in answer
