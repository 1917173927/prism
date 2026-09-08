from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.profile.questionnaire import QUESTIONNAIRE_TEMPLATE
from app.store import SQLiteDecisionEventStore


NOW = datetime(2026, 9, 8, 10, 0, tzinfo=UTC)


def valid_answers() -> list[dict]:
    result = []
    for question in QUESTIONNAIRE_TEMPLATE.questions:
        if question.question_type.value == "SCORE":
            result.append({"question_id": question.question_id, "score": 3})
        else:
            result.append({"question_id": question.question_id, "selected_option_ids": [question.options[0].option_id]})
    return result


def test_questionnaire_preview_confirm_summary_and_owner_isolation() -> None:
    store = SQLiteDecisionEventStore(":memory:")
    with TestClient(create_app(store=store, clock=lambda: NOW)) as client:
        owner = "full-questionnaire-owner"
        headers = {"X-Owner-ID": owner}
        template = client.get("/api/v1/advisor/profile/questionnaire-template", headers=headers)
        assert template.status_code == 200
        assert len(template.json()["questions"]) == 19
        payload = {
            "schema_version": "questionnaire-preview-request.v1",
            "owner_id": owner,
            "evaluated_at": NOW.isoformat(),
            "answers": valid_answers(),
        }
        preview = client.post("/api/v1/advisor/profile/questionnaire/preview", headers=headers, json=payload)
        assert preview.status_code == 200
        assert preview.json()["persisted"] is False
        assert client.get("/api/v1/advisor/profile/summary", headers=headers).json()["questionnaire_snapshot"] is None

        confirm = client.post(
            "/api/v1/advisor/profile/questionnaire/confirm",
            headers=headers,
            json={
                "schema_version": "questionnaire-confirmation-request.v1",
                "owner_id": owner,
                "confirmed_at": NOW.isoformat(),
                "answers": valid_answers(),
            },
        )
        assert confirm.status_code == 200
        snapshot = confirm.json()["snapshot"]
        assert snapshot["snapshot_version"] == 1
        assert len(snapshot["dimensions"]) == 8

        summary = client.get("/api/v1/advisor/profile/summary", headers=headers)
        assert summary.status_code == 200
        assert summary.json()["questionnaire_snapshot"]["snapshot_id"] == snapshot["snapshot_id"]
        assert "尚未完成 19 题风险问卷" not in summary.json()["data_gaps"]

        other = client.get("/api/v1/advisor/profile/summary", headers={"X-Owner-ID": "other-questionnaire-owner"})
        assert other.status_code == 200
        assert other.json()["questionnaire_snapshot"] is None
