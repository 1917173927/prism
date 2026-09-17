import json
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
        assert template.json()["questionnaire_version"] == "investor-questionnaire.v2"
        assert next(item for item in template.json()["questions"] if item["question_id"] == "Q13")["required"] is False
        payload = {
            "schema_version": "questionnaire-preview-request.v1",
            "owner_id": owner,
            "evaluated_at": NOW.isoformat(),
            "answers": valid_answers(),
        }
        preview = client.post("/api/v1/advisor/profile/questionnaire/preview", headers=headers, json=payload)
        assert preview.status_code == 200
        preview_body = preview.json()
        assert preview_body["persisted"] is False
        assert preview_body["presentation"]["schema_version"] == "profile-presentation.v2"
        assert preview_body["presentation"]["archetype"] == preview_body["presentation"]["persona"]
        assert preview_body["presentation"]["rule_trace"]["ruleset_version"] == "investor-profile-presentation-rules.v2"
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
        summary_body = summary.json()
        assert summary_body["questionnaire_snapshot"]["snapshot_id"] == snapshot["snapshot_id"]
        assert summary_body["data_gaps"] == []
        assert summary_body["next_actions"] == []
        assert summary_body["presentation"]["suitability_level"] == snapshot["suitability_level"]
        assert 3 <= len(summary_body["presentation"]["tags"]) <= 6
        assert len(summary_body["presentation"]["feats"]) <= 3
        assert "交易记录" not in "".join(summary_body["data_gaps"])

        other = client.get("/api/v1/advisor/profile/summary", headers={"X-Owner-ID": "other-questionnaire-owner"})
        assert other.status_code == 200
        assert other.json()["questionnaire_snapshot"] is None


def test_optional_q13_uses_default_feature_order() -> None:
    store = SQLiteDecisionEventStore(":memory:")
    answers = valid_answers()
    for answer in answers:
        if answer["question_id"] == "Q13":
            answer["selected_option_ids"] = []
    with TestClient(create_app(store=store, clock=lambda: NOW)) as client:
        response = client.post(
            "/api/v1/advisor/profile/questionnaire/preview",
            headers={"X-Owner-ID": "optional-q13-owner"},
            json={
                "schema_version": "questionnaire-preview-request.v1",
                "owner_id": "optional-q13-owner",
                "evaluated_at": NOW.isoformat(),
                "answers": answers,
            },
        )
    assert response.status_code == 200
    presentation = response.json()["presentation"]
    assert presentation["feats"] == ["market", "stock", "optimize"]
    assert presentation["rule_trace"]["feats"]["defaulted"] is True


def test_v2_migration_records_complete_presentation_rule_config() -> None:
    store = SQLiteDecisionEventStore(":memory:")
    row = store._connection.execute(
        "SELECT config_json FROM behavior_rule_versions WHERE ruleset_version = ?",
        ("investor-questionnaire-rules.v2",),
    ).fetchone()
    assert row is not None
    config = json.loads(row[0])
    assert config["presentation_ruleset"] == "investor-profile-presentation-rules.v2"
    assert len(config["personas"]) == 7
    assert list(config["service_strategy"]) == [f"S{index:02d}" for index in range(1, 11)]
    assert config["feature_map"]["risk"] == "optimize"
    assert config["tags"]["personalization"] == "per>=52"
