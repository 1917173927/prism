from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.runtime.mode import DataMode
from app.profile.questionnaire import QUESTIONNAIRE_TEMPLATE


@pytest.mark.parametrize("screenshot", [False, True])
def test_confirmed_portfolio_and_profile_survive_app_restart(tmp_path, monkeypatch, screenshot):
    controller = SimpleNamespace(mode=DataMode.LIVE)
    monkeypatch.setattr("app.api.main.get_runtime_mode_controller", lambda: controller)
    path = tmp_path / "private" / "prism.sqlite3"
    headers = {"X-Owner-ID": "saved-owner"}
    payload = {"owner_id": "saved-owner", "cash_cny": 28000,
               "positions": [{"asset_id": "600519.SH", "name": "贵州茅台", "quantity": 600, "price": 1300, "cost_price": 1680}]}
    endpoint = "/api/v1/advisor/portfolio/ocr/confirm" if screenshot else "/api/v1/copilot/validate-portfolio-ocr"
    if screenshot:
        payload["image_digest"] = "a" * 64
    answers = [{"question_id": q.question_id, **({"score": 3} if q.question_type.value == "SCORE"
               else {"selected_option_ids": [q.options[0].option_id]})} for q in QUESTIONNAIRE_TEMPLATE.questions]
    with TestClient(create_app(database_path=path)) as client:
        confirmed = client.post(endpoint, headers=headers, json=payload)
        assert confirmed.status_code == 200, confirmed.text
        original = confirmed.json()
        profile = client.post("/api/v1/advisor/profile/questionnaire/confirm", headers=headers,
                              json={"owner_id": "saved-owner", "confirmed_at": datetime.now(UTC).isoformat(), "answers": answers})
        assert profile.status_code == 200
    with TestClient(create_app(database_path=path)) as client:
        saved = client.get("/api/v1/advisor/portfolio/current", headers=headers).json()
        assert saved["data_mode"] == "LIVE"
        assert saved["data"] == original
        assert float(saved["data"]["positions"][0]["cost_price"]) == 1680
        assert float(saved["data"]["cash_cny"]) == 28000
        assert client.get("/api/v1/advisor/profile/summary", headers=headers).json()["questionnaire_snapshot"] == profile.json()["snapshot"]
        assert client.get("/api/v1/advisor/portfolio/current", headers={"X-Owner-ID": "another-owner"}).json()["data"] is None
        controller.mode = DataMode.MOCK
        assert client.get("/api/v1/advisor/portfolio/current", headers=headers).json()["data"] is None
        controller.mode = DataMode.LIVE
        invalid = {**payload, "positions": [{**payload["positions"][0], "quantity": 0}]}
        assert client.post(endpoint, headers=headers, json=invalid).status_code == 422
        assert client.get("/api/v1/advisor/portfolio/current", headers=headers).json()["data"] == original
