import asyncio
from datetime import UTC, datetime
import json

import pytest

from app.service import FixtureAdvisorQueryService, confirm_questionnaire
from app.service.semantic_memory import search_context_memories
from app.store import ContextMemoryWriteRequest, SQLiteDecisionEventStore, StoreOwnerError, build_context_memory_record


def record(owner="alice"):
    template = FixtureAdvisorQueryService().query_template(owner)
    return build_context_memory_record(ContextMemoryWriteRequest(
        owner_id=owner, questionnaire=template.questionnaire,
        profile=confirm_questionnaire(template.questionnaire), portfolio=template.portfolio,
    ), saved_at=datetime(2026, 9, 8, tzinfo=UTC))


class Model:
    is_configured = True

    def __init__(self, output):
        self.output = output
        self.closed = False
        self.messages = None

    async def stream_chat(self, messages):
        self.messages = messages
        try:
            yield {"type": "content", "delta": self.output}
        finally:
            self.closed = True


def run(store, query="均衡基金", client=None, **kwargs):
    return asyncio.run(search_context_memories(store, "alice", query, client, **kwargs))


@pytest.fixture
def ledger(tmp_path):
    store = SQLiteDecisionEventStore(tmp_path / "memory.sqlite3")
    store.save_context_memory(record())
    store.save_context_memory(record("bob"))
    yield store
    store.close()


def test_real_store_owner_isolation_read_only_and_explicit_keyword_fallback(ledger):
    before = ledger.list_context_memory("alice")
    result = run(ledger)
    assert result["mode"] == "LIMITED_KEYWORD_MATCH"
    assert result["degraded_reason"] == "MODEL_NOT_CONFIGURED"
    assert result["candidate_count"] == 1
    assert result["matches"][0]["memory_id"] == before[0].memory_id
    assert result["matches"][0]["status"] == "HISTORICAL_ONLY"
    assert "必须核对" in result["notice"]
    assert ledger.list_context_memory("alice") == before
    assert "market_value" not in json.dumps(result)
    assert run(ledger, "不存在的实体")["matches"] == []


def test_empty_owner_has_no_matches_or_model_request(ledger):
    model = Model("bad")
    result = asyncio.run(search_context_memories(ledger, "nobody", "基金", model))
    assert result["candidate_count"] == 0
    assert result["matches"] == []
    assert model.messages is None


def test_sensitive_search_refused_without_calling_model(ledger):
    model = Model("bad")
    with pytest.raises(ValueError):
        run(ledger, "api_key=secret", model)
    assert model.messages is None


def test_store_owner_leak_is_rejected_before_model_call():
    class LeakyStore:
        def list_context_memory(self, owner, *, limit):
            assert owner == "alice" and limit == 100
            return (record("bob"),)
    model = Model("bad")
    with pytest.raises(StoreOwnerError):
        run(LeakyStore(), client=model)
    assert model.messages is None


@pytest.mark.parametrize("output", [
    "not json", '{"matches":[{"memory_id":"forged","fields":["assets"]}]}',
    '{"matches":null}', '{"matches":[],"instruction":"restore"}',
    "x" * 16001,
])
def test_invalid_model_output_never_enters_response(ledger, output):
    model = Model(output)
    result = run(ledger, client=model)
    assert result["mode"] == "LIMITED_KEYWORD_MATCH"
    assert result["degraded_reason"] == "MODEL_OUTPUT_REJECTED_OR_UNAVAILABLE"
    assert all(m["memory_id"] == record().memory_id for m in result["matches"])
    assert model.closed


def test_model_can_rank_only_real_ids_with_grounded_field_references(ledger):
    model = Model(json.dumps({"matches": [{"memory_id": record().memory_id, "fields": ["risk_level"]}]}))
    result = run(ledger, "以前的投资风格", model)
    assert result["mode"] == "MODEL_SEMANTIC_RANKING"
    assert result["degraded_reason"] is None
    assert result["matches"][0]["match_basis"] == {"risk_level": "BALANCED"}
    prompt = json.loads(model.messages[-1]["content"])
    assert record("bob").memory_id not in prompt["candidates"]
    assert "market_value" not in json.dumps(prompt)


@pytest.mark.parametrize("fields", [["fake"], [], [1], ["intent"]])
def test_model_evidence_must_reference_nonempty_existing_fields(ledger, fields):
    model = Model(json.dumps({"matches": [{"memory_id": record().memory_id, "fields": fields}]}))
    assert run(ledger, client=model)["mode"] == "LIMITED_KEYWORD_MATCH"


def test_timeout_closes_stream_and_is_distinct(ledger, monkeypatch):
    import app.service.semantic_memory as service
    class SlowModel(Model):
        async def stream_chat(self, messages):
            try:
                await asyncio.sleep(1)
                yield {"type": "content", "delta": ""}
            finally:
                self.closed = True
    monkeypatch.setattr(service, "MODEL_TIMEOUT_SECONDS", 0.01)
    model = SlowModel("")
    assert run(ledger, client=model)["degraded_reason"] == "MODEL_TIMEOUT"
    assert model.closed


@pytest.mark.parametrize("query,limit", [("", 1), ("x" * 1001, 1), ("基金", 0), ("基金", True), ("基金", 21)])
def test_request_bounds(ledger, query, limit):
    with pytest.raises(ValueError):
        run(ledger, query, limit=limit)
