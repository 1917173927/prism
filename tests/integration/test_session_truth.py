from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from app.api.main import create_app
from app.llm.agent import CopilotAgent
from app.llm.ocr_portfolio_parser import recalculate_portfolio_values
from app.profile.questionnaire import QUESTIONNAIRE_TEMPLATE, QuestionnaireAnswer, build_questionnaire_snapshot
from app.runtime.mode import DataMode
from app.store import SQLiteDecisionEventStore
from app.store.sqlite import StoreConflictError, StoreCorruptError


def populate(store):
    now = datetime.now(UTC)
    answers = [{"question_id":q.question_id, **({"score":3} if q.question_type.value == "SCORE" else {"selected_option_ids":[q.options[0].option_id]})}
               for q in QUESTIONNAIRE_TEMPLATE.questions]
    store.save_questionnaire_snapshot(build_questionnaire_snapshot("owner", tuple(QuestionnaireAnswer.model_validate(a) for a in answers), confirmed_at=now, snapshot_version=1))
    data = recalculate_portfolio_values([{"asset_id":"600519.SH", "quantity":100, "price":1000}], Decimal(20000), "owner")
    store.save_current_portfolio("owner", "MOCK", data)
    return data


def test_revision_scope_persistence_and_corruption(tmp_path):
    path = tmp_path / "truth.sqlite3"
    store = SQLiteDecisionEventStore(path)
    try:
        record = store.save_session_truth("owner", "session", {"data_mode":"MOCK"}, 0, datetime.now(UTC).isoformat())
        assert record["revision"] == 1
        assert store.get_session_truth("other", "session") is None
        with pytest.raises(StoreConflictError):
            store.save_session_truth("owner", "session", {}, 0, datetime.now(UTC).isoformat())
    finally:
        store.close()
    store = SQLiteDecisionEventStore(path)
    try:
        assert store.get_session_truth("owner", "session")["revision"] == 1
        store._connection.execute("UPDATE session_truth SET payload_json='{}'")
        with pytest.raises(StoreCorruptError):
            store.get_session_truth("owner", "session")
    finally:
        store.close()


def test_lock_blocks_drift_and_binds_chat_to_server_facts(monkeypatch):
    monkeypatch.setattr("app.api.main.get_runtime_mode_controller", lambda: SimpleNamespace(mode=DataMode.MOCK))
    captured = {}
    async def chat(self, **kwargs):
        captured.update(kwargs)
        yield {"type":"token", "delta":"verified-context"}
    monkeypatch.setattr(CopilotAgent, "stream_chat", chat)
    store = SQLiteDecisionEventStore()
    data = populate(store)
    try:
        with TestClient(create_app(store=store)) as client:
            headers = {"X-Owner-ID":"owner"}
            endpoint = "/api/v1/advisor/session-truth"
            assert client.get(endpoint, headers=headers).json()["status"] == "NOT_LOCKED"
            locked = client.post(endpoint, headers=headers, json={"expected_revision":0})
            assert locked.status_code == 200, locked.text
            assert locked.json()["status"] == "LOCKED"
            assert client.post(endpoint, headers=headers, json={"expected_revision":0}).status_code == 409
            request = {"owner_id":"owner", "message":"请检查", "session_truth_id":"workbench", "session_truth_revision":1,
                       "persona_info":{"max_drawdown":99}, "portfolio_context":{"fabricated":True}}
            assert client.post("/api/v1/copilot/chat", headers=headers, json=request).status_code == 200
            assert captured["persona_info"]["max_drawdown"] != 99
            assert captured["portfolio_context"]["portfolio"] == data["portfolio"]
            assert client.post("/api/v1/copilot/chat", headers=headers, json={**request, "portfolio_snapshot_id":"wrong"}).status_code == 409
            new_data = recalculate_portfolio_values([{"asset_id":"600519.SH", "quantity":200, "price":1000}], Decimal(20000), "owner")
            store.save_current_portfolio("owner", "MOCK", new_data)
            assert client.get(endpoint, headers=headers).json()["status"] == "DRIFT_DETECTED"
            assert client.post("/api/v1/copilot/chat", headers=headers, json=request).status_code == 409
            assert client.post(endpoint, headers=headers, json={"expected_revision":1}).json()["revision"] == 2
    finally:
        store.close()


def test_stream_is_stopped_if_premises_change_during_generation(monkeypatch):
    monkeypatch.setattr("app.api.main.get_runtime_mode_controller", lambda: SimpleNamespace(mode=DataMode.MOCK))
    store = SQLiteDecisionEventStore()
    populate(store)
    closed = []
    async def chat(self, **kwargs):
        try:
            store.save_current_portfolio("owner", "MOCK", recalculate_portfolio_values(
                [{"asset_id":"600519.SH", "quantity":300, "price":1000}], Decimal(20000), "owner"))
            yield {"type":"token", "delta":"must-not-be-returned"}
        finally:
            closed.append(True)
    monkeypatch.setattr(CopilotAgent, "stream_chat", chat)
    try:
        with TestClient(create_app(store=store)) as client:
            headers = {"X-Owner-ID":"owner"}
            client.post("/api/v1/advisor/session-truth", headers=headers, json={"expected_revision":0})
            response = client.post("/api/v1/copilot/chat", headers=headers, json={
                "owner_id":"owner", "message":"hello", "session_truth_id":"workbench", "session_truth_revision":1})
            assert "must-not-be-returned" not in response.text
            assert '"type":"error"' in response.text
            assert closed == [True]
    finally:
        store.close()
