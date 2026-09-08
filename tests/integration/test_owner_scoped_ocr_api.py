from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.store import SQLiteDecisionEventStore


NOW = datetime(2026, 9, 8, 11, 0, tzinfo=UTC)
OWNER = "ocr-api-owner"
SAMPLE = Path(__file__).parents[2] / "app" / "api" / "static" / "sample_holding.png"


def test_owner_scoped_ocr_requires_confirmation_before_persistence() -> None:
    store = SQLiteDecisionEventStore(":memory:")
    with TestClient(create_app(store=store, clock=lambda: NOW)) as client:
        with SAMPLE.open("rb") as image:
            parsed = client.post(
                "/api/v1/advisor/portfolio/ocr",
                headers={"X-Owner-ID": OWNER},
                files={"file": ("holding.png", image, "image/png")},
            )
        assert parsed.status_code == 200
        draft = parsed.json()
        assert draft["status"] == "SUCCESS"
        assert draft["original_image_persisted"] is False
        assert len(draft["image_digest"]) == 64
        count = store._connection.execute(
            "SELECT COUNT(*) FROM portfolio_ocr_confirmations"
        ).fetchone()[0]
        assert count == 0

        confirmed = client.post(
            "/api/v1/advisor/portfolio/ocr/confirm",
            headers={"X-Owner-ID": OWNER},
            json={
                "owner_id": OWNER,
                "image_digest": draft["image_digest"],
                "positions": draft["positions"],
                "cash_cny": draft["cash_cny"],
            },
        )
        assert confirmed.status_code == 200
        result = confirmed.json()
        assert result["confirmation_status"] == "CALCULATED"
        assert result["portfolio"]["owner_id"] == OWNER
        assert result["original_image_persisted"] is False
        behavior_events = store.list_behavior_events(OWNER)
        assert len(behavior_events) == 1
        assert behavior_events[0].event_type.value == "POSITION_SNAPSHOT"
        payload = store._connection.execute(
            "SELECT payload_json FROM portfolio_ocr_confirmations"
        ).fetchone()[0]
        assert "image_base64" not in payload
        assert "data:image" not in payload

        repeated = client.post(
            "/api/v1/advisor/portfolio/ocr/confirm",
            headers={"X-Owner-ID": OWNER},
            json={
                "owner_id": OWNER,
                "image_digest": draft["image_digest"],
                "positions": draft["positions"],
                "cash_cny": draft["cash_cny"],
            },
        )
        assert repeated.status_code == 200
        assert repeated.json()["created"] is False

        other_owner = "ocr-api-owner-2"
        cross_tenant_same_image = client.post(
            "/api/v1/advisor/portfolio/ocr/confirm",
            headers={"X-Owner-ID": other_owner},
            json={
                "owner_id": other_owner,
                "image_digest": draft["image_digest"],
                "positions": draft["positions"],
                "cash_cny": draft["cash_cny"],
            },
        )
        assert cross_tenant_same_image.status_code == 200
        assert cross_tenant_same_image.json()["created"] is True


def test_owner_scoped_ocr_rejects_unsupported_media_and_cross_owner_confirmation() -> None:
    store = SQLiteDecisionEventStore(":memory:")
    with TestClient(create_app(store=store, clock=lambda: NOW)) as client:
        bad = client.post(
            "/api/v1/advisor/portfolio/ocr",
            headers={"X-Owner-ID": OWNER},
            files={"file": ("holding.txt", b"not an image", "text/plain")},
        )
        assert bad.status_code == 415
        cross_owner = client.post(
            "/api/v1/advisor/portfolio/ocr/confirm",
            headers={"X-Owner-ID": "other-owner"},
            json={
                "owner_id": OWNER,
                "image_digest": "a" * 64,
                "positions": [],
                "cash_cny": 0,
            },
        )
        assert cross_owner.status_code == 403


def test_owner_scoped_ocr_rejects_sensitive_extra_position_fields() -> None:
    with TestClient(create_app(clock=lambda: NOW)) as client:
        response = client.post(
            "/api/v1/advisor/portfolio/ocr/confirm",
            headers={"X-Owner-ID": OWNER},
            json={
                "owner_id": OWNER,
                "image_digest": "b" * 64,
                "cash_cny": 0,
                "positions": [{
                    "asset_id": "300750.SZ",
                    "quantity": 100,
                    "price": 200,
                    "password": "must-not-be-accepted",
                }],
            },
        )
        assert response.status_code == 422


def test_updated_screenshot_creates_distinct_behavior_snapshot() -> None:
    store = SQLiteDecisionEventStore(":memory:")
    with TestClient(create_app(store=store, clock=lambda: NOW)) as client:
        for digest, quantity in [("c", 100), ("d", 200)]:
            response = client.post(
                "/api/v1/advisor/portfolio/ocr/confirm",
                headers={"X-Owner-ID": OWNER},
                json={"owner_id": OWNER, "image_digest": digest * 64, "cash_cny": 28000,
                      "positions": [{"asset_id": "600519.SH", "quantity": quantity, "price": 1300}]},
            )
            assert response.status_code == 200, response.text
        events = store.list_behavior_events(OWNER)
        assert len(events) == 2
        assert len({event.event_id for event in events}) == 2
