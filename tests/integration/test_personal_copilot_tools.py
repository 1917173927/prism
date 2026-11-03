"""A saved private skill is actually callable through the conversational Agent."""
import asyncio
from contextlib import closing
from datetime import UTC, datetime

from app.llm.agent import CopilotAgent
from app.providers.contracts import ProviderRecord, ProviderResult
from app.providers.fingerprint import compute_request_fingerprint
from app.runtime.mode import DataMode
from app.service.personal_research import PersonalResearchSave, PersonalResearchService, profitability_template
from app.service.research_runtime import ResearchRuntime
from app.service.skill_registry import SkillRegistry
from app.store.sqlite import SQLiteDecisionEventStore


NOW = datetime(2026, 10, 6, tzinfo=UTC)


def test_saved_personal_skill_is_executed_by_owner_scoped_copilot(tmp_path):
    class Provider:
        name = "controlled-personal-copilot"
        calls = 0

        async def execute(self, request):
            self.calls += 1
            return ProviderResult(request_id=request.request_id,
                request_fingerprint=compute_request_fingerprint(request), provider=self.name,
                status="SUCCESS", retrieved_at=NOW, records=(ProviderRecord(
                    source="controlled-financial-report", record_id="statement-one", observed_at=NOW,
                    period="2025", fields={"items": [{"股票代码": "600519", "revenue": "100", "net_profit": "20"}]},
                    units={"revenue": "CNY", "net_profit": "CNY"}),))

    async def scenario():
        with closing(SQLiteDecisionEventStore(tmp_path / "copilot.sqlite")) as store:
            provider = Provider()
            runtime = ResearchRuntime()
            service = PersonalResearchService(store=store, provider=provider, registry=SkillRegistry(store),
                runtime=runtime, clock=lambda: NOW, evidence_mode="CONTROLLED_REGRESSION")
            service.save("alice", "profitability", PersonalResearchSave(
                definition=profitability_template(), expected_revision=0))
            shared = CopilotAgent()
            alice = shared.with_owner("alice", personal_research_service=service)
            bob = shared.with_owner("bob", personal_research_service=service)
            assert not hasattr(shared, "authorized_owner")
            catalog = await alice._execute_tool("list_personal_research_systems", {}, {}, None, data_mode=DataMode.MOCK)
            assert catalog["items"][0]["revision"] == 1
            args = {"system_id": "profitability", "expected_revision": 1, "subject": "600519", "period": "2025"}
            result = await alice._execute_tool("run_personal_research_system", args, {}, None, data_mode=DataMode.MOCK)
            assert result["status"] == "COMPLETED"
            assert result["indicators"][0]["value"] == "20.0000000000"
            rendered = alice._synthesize_grounded_response("使用我的研究系统", {}, [
                {"tool": "run_personal_research_system", "args": args, "result": result}], None)
            assert "20.0000000000" in rendered and "不构成买卖指令" in rendered
            assert (await bob._execute_tool("run_personal_research_system", args, {}, None))["status"] == "UNAVAILABLE"
            assert provider.calls == 1
            assert CopilotAgent._validate_tool_call("run_personal_research_system", {**args, "owner_id": "alice"})[1]
            assert CopilotAgent._validate_tool_call("run_personal_research_system", {**args, "expected_revision": True})[1]

            class IntentOnlyClient:
                async def stream_chat(self, messages, **kwargs):
                    yield {"type": "tool_call", "name": "run_personal_research_system", "arguments": args}
                    # Model text cannot replace the deterministic financial result.
                    yield {"type": "content", "delta": "指标为999%"}

            streamed_agent = CopilotAgent(llm_client=IntentOnlyClient()).with_owner("alice", personal_research_service=service)
            events = [event async for event in streamed_agent.stream_chat(
                "使用我的研究系统", tool_data_mode=DataMode.MOCK)]
            finished = next(event for event in events if event["type"] == "tool_done")
            assert finished["result"]["indicators"][0]["value"] == "20.0000000000"
            answer = "".join(event.get("delta", "") for event in events if event["type"] == "token")
            assert "20.0000000000" in answer and "999" not in answer
            assert provider.calls == 2
            await service.aclose()
            await runtime.aclose()

    asyncio.run(scenario())
