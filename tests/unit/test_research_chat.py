import asyncio
from datetime import UTC, datetime

from app.llm.agent import CopilotAgent
from app.service.knowledge import KnowledgeDocumentInput, KnowledgeService
from app.store.sqlite import SQLiteDecisionEventStore


class NoEmbedding:
    model_id, revision = "disabled", "test"
    def encode(self, *args, **kwargs):
        raise RuntimeError("disabled")


def test_chat_knowledge_owner_contract_and_deleted_quote():
    store = SQLiteDecisionEventStore()
    service = KnowledgeService(store, clock=lambda: datetime(2026, 10, 1, tzinfo=UTC), embedder=NoEmbedding())
    try:
        doc = service.ingest("alice", KnowledgeDocumentInput(title="方法", text="协方差收缩采用常相关目标。", source="method", published_at="2026-09-01T00:00:00Z"))
        agent = CopilotAgent().with_owner("alice", knowledge_service=service)
        assert agent._validate_tool_call("search_research_knowledge", {"query": "协方差", "owner_id": "bob"})[1]
        args = {"query": "协方差"}
        result = asyncio.run(agent._execute_tool("search_research_knowledge", args, {}, None))
        tools = [{"tool": "search_research_knowledge", "args": args, "result": result}]
        answer = agent._synthesize_grounded_response("方法", {}, tools, None)
        assert "协方差收缩采用常相关目标" in answer
        bob = CopilotAgent().with_owner("bob", knowledge_service=service)
        hidden = asyncio.run(bob._execute_tool("search_research_knowledge", args, {}, None))
        assert hidden["status"] == "EMPTY"
        service.delete("alice", doc["document_id"], expected_revision=doc["revision"])
        assert "协方差收缩采用常相关目标" not in agent._synthesize_grounded_response("方法", {}, tools, None)
    finally:
        store.close()
