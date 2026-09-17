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


def test_same_screenshot_can_be_reconfirmed_after_clear_with_revised_quote_time() -> None:
    store = SQLiteDecisionEventStore(":memory:")
    headers = {"X-Owner-ID": OWNER}
    first_payload = {
        "owner_id": OWNER,
        "image_digest": "f" * 64,
        "cash_cny": 416.64,
        "positions": [{
            "asset_id": "002185.SZ",
            "name": "华天科技",
            "quantity": 100,
            "available_quantity": 100,
            "cost_price": 15.3,
            "price": 16.97,
            "market_value_cny": 1697,
            "observed_at": "2026-09-16T13:21:00Z",
        }],
    }
    with TestClient(create_app(store=store, clock=lambda: NOW)) as client:
        first = client.post(
            "/api/v1/advisor/portfolio/ocr/confirm",
            headers=headers,
            json=first_payload,
        )
        assert first.status_code == 200, first.text
        assert first.json()["created"] is True

        cleared = client.put(
            "/api/v1/advisor/portfolio/current",
            headers=headers,
            json={"owner_id": OWNER, "positions": [], "cash_cny": 0},
        )
        assert cleared.status_code == 200

        revised_payload = {
            **first_payload,
            "positions": [{
                **first_payload["positions"][0],
                "observed_at": "2026-09-17T07:39:00Z",
            }],
        }
        revised = client.post(
            "/api/v1/advisor/portfolio/ocr/confirm",
            headers=headers,
            json=revised_payload,
        )
        assert revised.status_code == 200, revised.text
        assert revised.json()["created"] is True
        assert revised.json()["positions"][0]["observed_at"] == "2026-09-17T07:39:00Z"

        repeated = client.post(
            "/api/v1/advisor/portfolio/ocr/confirm",
            headers=headers,
            json=revised_payload,
        )
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()["created"] is False
        assert store._connection.execute(
            "SELECT COUNT(*) FROM portfolio_ocr_confirmations WHERE owner_id = ? AND image_digest = ?",
            (OWNER, first_payload["image_digest"]),
        ).fetchone()[0] == 2
    store.close()


def test_confirm_accepts_editable_broker_row_with_defaulted_quote_time() -> None:
    store = SQLiteDecisionEventStore(":memory:")
    with TestClient(create_app(store=store, clock=lambda: NOW)) as client:
        response = client.post(
            "/api/v1/advisor/portfolio/ocr/confirm",
            headers={"X-Owner-ID": OWNER},
            json={
                "owner_id": OWNER,
                "image_digest": "e" * 64,
                "cash_cny": 23933.53,
                "positions": [{
                    "asset_id": "600251.SH",
                    "name": "冠农股份",
                    "asset_class": "EQUITY",
                    "sector": "Unclassified",
                    "quantity": 6700,
                    "available_quantity": 0,
                    "cost_price": 11.588,
                    "price": 10.03,
                    "market_value_cny": 67201,
                    "calculated_market_value_cny": 67201,
                    "observed_at": "2026-09-16T18:32:00+08:00",
                    "price_source": "user-confirmed broker screenshot",
                    "field_sources": {
                        "observed_at": "system default: browser local current time",
                    },
                    "review_reasons": [],
                    "needs_review": False,
                    "confidence_level": "HIGH",
                }],
            },
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["positions"][0]["asset_id"] == "600251.SH"
        assert result["positions"][0]["available_quantity"] == 0
        assert result["confirmation_status"] == "CALCULATED"
