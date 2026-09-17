from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.profile.questionnaire import QUESTIONNAIRE_TEMPLATE
from app.store import SQLiteDecisionEventStore
from app.trading_history import TradeImportPreview


NOW = datetime(2026, 9, 17, 8, tzinfo=UTC)
OWNER = "trade-api-owner"


def valid_answers() -> list[dict]:
    return [
        ({"question_id": question.question_id, "score": 3}
         if question.question_type.value == "SCORE"
         else {"question_id": question.question_id, "selected_option_ids": [question.options[0].option_id]})
        for question in QUESTIONNAIRE_TEMPLATE.questions
    ]


def rows() -> list[dict]:
    result = []
    for index in range(50):
        result.append({
            "traded_at": (NOW - timedelta(days=300 - index * 6)).isoformat(),
            "security_code": "600000.SH",
            "security_name": "浦发银行",
            "side": "BUY" if index < 25 else "SELL",
            "quantity": "100",
            "price_cny": "10",
            "gross_amount_cny": "1000",
            "fee_cny": "1",
            "account_alias": "测试账户",
            "broker_trade_id": f"broker-{index}",
            "source_row": index + 2,
            "source_confidence": "1",
        })
    return result


def test_preview_confirm_list_edit_withdraw_and_restore() -> None:
    store = SQLiteDecisionEventStore(":memory:")
    with TestClient(create_app(store=store, clock=lambda: NOW)) as client:
        headers = {"X-Owner-ID": OWNER}
        questionnaire = client.post(
            "/api/v1/advisor/profile/questionnaire/confirm",
            headers=headers,
            json={
                "owner_id": OWNER,
                "confirmed_at": NOW.isoformat(),
                "answers": valid_answers(),
            },
        )
        assert questionnaire.status_code == 200
        assert store.get_latest_behavior_profile(OWNER) is None
        preview = client.post(
            "/api/v1/advisor/trading-history/import/preview",
            headers=headers,
            files={"files": ("trades.csv", b"\xe6\x88\x90\xe4\xba\xa4\xe6\x97\xa5\xe6\x9c\x9f,\xe8\xaf\x81\xe5\x88\xb8\xe4\xbb\xa3\xe7\xa0\x81,\xe4\xb9\xb0\xe5\x8d\x96\xe6\x96\xb9\xe5\x90\x91,\xe6\x88\x90\xe4\xba\xa4\xe6\x95\xb0\xe9\x87\x8f,\xe6\x88\x90\xe4\xba\xa4\xe4\xbb\xb7\xe6\xa0\xbc\n2026-01-02,600000,\xe4\xb9\xb0\xe5\x85\xa5,100,10\n", "text/csv")},
        )
        assert preview.status_code == 200
        assert preview.json()["original_files_persisted"] is False

        payload = {
            "schema_version": "trade-import-confirm-request.v1",
            "owner_id": OWNER,
            "source_type": "CSV",
            "source_digest": "a" * 64,
            "file_count": 1,
            "rows": rows(),
        }
        confirmed = client.post("/api/v1/advisor/trading-history/imports", headers=headers, json=payload)
        assert confirmed.status_code == 200, confirmed.text
        body = confirmed.json()
        assert body["batch"]["accepted_count"] == 50
        assert body["style_profile"]["status"] == "CALCULATED"
        behavior = store.get_latest_behavior_profile(OWNER)
        assert behavior is not None
        assert behavior.behavior_risk_score is None
        assert behavior.effective_risk_score == Decimal(questionnaire.json()["snapshot"]["profile"]["risk_score"])

        repeated = client.post("/api/v1/advisor/trading-history/imports", headers=headers, json=payload)
        assert repeated.status_code == 200
        assert repeated.json()["batch"]["batch_id"] == body["batch"]["batch_id"]
        assert len(store.list_trade_records(OWNER)) == 50
        assert store.get_latest_behavior_profile(OWNER).profile_version == behavior.profile_version

        overlapping = {**payload, "source_digest": "b" * 64, "rows": [rows()[0]]}
        duplicate = client.post("/api/v1/advisor/trading-history/imports", headers=headers, json=overlapping)
        assert duplicate.status_code == 200
        assert duplicate.json()["batch"]["accepted_count"] == 0
        assert duplicate.json()["batch"]["duplicate_count"] == 1
        assert len(store.list_trade_records(OWNER)) == 50

        listing = client.get("/api/v1/advisor/trading-history/trades?limit=10", headers=headers)
        assert listing.status_code == 200
        assert listing.json()["total"] == 50
        item = listing.json()["items"][0]

        patched = client.patch(
            f"/api/v1/advisor/trading-history/trades/{item['trade_id']}",
            headers=headers,
            json={"schema_version": "trade-update-request.v1", "expected_revision": 1, "quantity": "200"},
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["trade"]["revision"] == 2
        assert patched.json()["trade"]["gross_amount_cny"] == "2000"

        stale = client.patch(
            f"/api/v1/advisor/trading-history/trades/{item['trade_id']}",
            headers=headers,
            json={"expected_revision": 1, "quantity": "300"},
        )
        assert stale.status_code == 409

        withdrawn = client.delete(
            f"/api/v1/advisor/trading-history/trades/{item['trade_id']}?expected_revision=2",
            headers=headers,
        )
        assert withdrawn.status_code == 200
        assert withdrawn.json()["trade"]["status"] == "WITHDRAWN"
        restored = client.post(
            f"/api/v1/advisor/trading-history/trades/{item['trade_id']}/restore",
            headers=headers,
            json={"schema_version": "trade-revision-request.v1", "expected_revision": 3},
        )
        assert restored.status_code == 200
        assert restored.json()["trade"]["status"] == "ACTIVE"

        other = client.get(
            "/api/v1/advisor/trading-history/trades",
            headers={"X-Owner-ID": "other-owner"},
        )
        assert other.json()["total"] == 0


def test_trade_page_is_a_primary_navigation_workspace() -> None:
    html = open("app/api/static/index.html", encoding="utf-8").read()
    script = open("app/api/static/app.js", encoding="utf-8").read()
    styles = open("app/api/static/prism-v2.css", encoding="utf-8").read()
    assert 'href="#trading-style"' in html
    assert 'id="trading-style"' in html
    assert 'id="trade-import-files"' in html
    assert 'id="trade-sheet-selector"' in html
    assert 'id="trade-history-rows"' in html
    assert '"trading-style": "trading-style"' in script
    assert "function renderTradingStyleProfile(" in script
    assert "function previewTradeImport(" in script
    assert ".trading-style-page" in styles


def test_screenshot_preview_resolves_security_code_once_per_unique_name(monkeypatch) -> None:
    calls: list[str] = []

    class FakeSecurityDirectory:
        async def resolve_security_identity(self, name: str):
            calls.append(name)
            return {
                "asset_id": "600186.SH",
                "name": "莲花控股",
                "market": "SH",
                "source": "test exact-name official directory",
            }

    def fake_preview(_files, *, selected_sheet=None):
        assert selected_sheet is None
        row = {
            "row_number": 1,
            "raw_values": {"证券名称": "莲花控股"},
            "proposed": {
                "traded_at": "2026-09-14T10:43:00+08:00",
                "security_code": None,
                "security_name": "莲花控股",
                "side": "SELL",
                "quantity": "200",
                "price_cny": "13.180",
                "gross_amount_cny": "2636.000",
            },
            "confidence": "0.99",
            "status": "PASS",
            "issues": [],
        }
        return TradeImportPreview(
            source_type="IMAGE",
            source_digest="c" * 64,
            file_count=1,
            detected_columns=("证券名称",),
            suggested_mapping={"security_name": "证券名称"},
            rows=(row, {**row, "row_number": 2}),
            accepted_count=2,
            review_count=0,
            rejected_count=0,
        )

    monkeypatch.setattr("app.api.main.preview_trade_files", fake_preview)
    store = SQLiteDecisionEventStore(":memory:")
    with TestClient(create_app(
        store=store,
        security_directory_provider=FakeSecurityDirectory(),
    )) as client:
        response = client.post(
            "/api/v1/advisor/trading-history/import/preview",
            headers={"X-Owner-ID": OWNER},
            files={"files": ("statement.png", b"bounded-image", "image/png")},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert [row["proposed"]["security_code"] for row in body["rows"]] == [
        "600186.SH", "600186.SH",
    ]
    assert body["rows"][0]["proposed"]["security_identity_source"] == "test exact-name official directory"
    assert body["accepted_count"] == 2
    assert calls == ["莲花控股"]
