from fastapi.testclient import TestClient

from app.api import create_app
from app.runtime.mode import DataMode, reset_runtime_mode_controller
from app.store import SQLiteDecisionEventStore


class FakeOcrParser:
    def parse_image_bytes(self, content: bytes):
        assert content == b"bounded-image"
        return {
            "status": "SUCCESS",
            "positions": [{
                "asset_id": "300750.SZ",
                "name": "宁德时代",
                "asset_class": "STOCK",
                "sector": "Technology",
                "quantity": 100,
                "cost_price": 258.6,
                "price": 258.6,
                "market_value_cny": 25860,
                "confidence": 0.99,
                "confidence_pct": 99,
                "needs_review": True,
                "review_reasons": ["MISSING_OBSERVED_FIELDS"],
            }],
            "cash_cny": 0,
            "parsed_count": 1,
            "has_low_confidence_items": True,
        }


class FakeLiveFinance:
    is_configured = True

    async def get_quote(self, symbol: str):
        assert symbol == "300750"
        return {
            "symbol": "300750.SZ",
            "name": "宁德时代",
            "price_cny": 310.25,
            "previous_close_cny": 305.0,
            "observed_at": "2026-09-14T14:30:00+08:00",
            "source": "verified-live-test-provider",
            "is_synthetic": False,
        }


class FakeNameResolvingDirectory:
    async def resolve_security_identity(self, name: str):
        assert name == "江苏新能"
        return {
            "asset_id": "603693.SH",
            "name": "江苏新能",
            "market": "SH",
            "source": "test exact-name official directory",
        }


class FakeCorrectingDirectory:
    async def resolve_security_identity(self, name: str):
        assert name == "华天科技"
        return {
            "asset_id": "002185.SZ",
            "name": "华天科技",
            "market": "SZ",
            "source": "test exact-name official directory",
        }


class FakeNameOnlyOcrParser:
    def parse_image_bytes(self, content: bytes):
        assert content == b"bounded-image"
        return {
            "status": "SUCCESS",
            "positions": [{
                "asset_id": "",
                "name": "江苏新能",
                "asset_class": "EQUITY",
                "sector": "Unclassified",
                "quantity": 100,
                "available_quantity": 0,
                "cost_price": 17.91,
                "price": 17.95,
                "market_value_cny": 1795,
                "confidence": 0.99,
                "confidence_pct": 99,
                "needs_review": True,
                "review_reasons": ["SECURITY_IDENTITY_REQUIRED"],
                "field_sources": {"identity": "unresolved broker display name"},
            }],
            "cash_cny": 0,
            "parsed_count": 1,
            "has_low_confidence_items": True,
        }


def test_ocr_resolves_name_only_holding_without_provider_credential(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.llm.ocr_portfolio_parser.OCRPortfolioParser.get_instance",
        lambda: FakeNameOnlyOcrParser(),
    )
    reset_runtime_mode_controller(DataMode.MOCK)
    store = SQLiteDecisionEventStore(":memory:")
    client = TestClient(create_app(
        store,
        security_directory_provider=FakeNameResolvingDirectory(),
    ))

    parsed = client.post(
        "/api/v1/copilot/upload-portfolio-ocr",
        files={"file": ("holding.png", b"bounded-image", "image/png")},
    )

    assert parsed.status_code == 200, parsed.text
    position = parsed.json()["positions"][0]
    assert position["asset_id"] == "603693.SH"
    assert position["identity_candidates"][0]["source"] == "test exact-name official directory"
    assert "SECURITY_IDENTITY_REQUIRED" not in position["review_reasons"]
    assert position["field_sources"]["identity"] == "test exact-name official directory"
    store.close()
    reset_runtime_mode_controller(DataMode.MOCK)


def test_ocr_corrects_syntactically_valid_code_when_exact_name_disagrees(monkeypatch) -> None:
    class WrongCodeOcrParser:
        def parse_image_bytes(self, content: bytes):
            assert content == b"bounded-image"
            return {
                "status": "SUCCESS",
                "positions": [{
                    "asset_id": "600000.SH",
                    "name": "华天科技",
                    "asset_class": "EQUITY",
                    "quantity": 100,
                    "cost_price": 15.3,
                    "price": 16.97,
                    "market_value_cny": 1697,
                    "needs_review": False,
                    "review_reasons": [],
                    "field_sources": {"identity": "broker screenshot OCR"},
                }],
                "cash_cny": 0,
                "parsed_count": 1,
                "has_low_confidence_items": False,
            }

    monkeypatch.setattr(
        "app.llm.ocr_portfolio_parser.OCRPortfolioParser.get_instance",
        lambda: WrongCodeOcrParser(),
    )
    reset_runtime_mode_controller(DataMode.LIVE)
    store = SQLiteDecisionEventStore(":memory:")
    client = TestClient(create_app(
        store,
        live_finance_provider=FakeLiveFinance(),
        security_directory_provider=FakeCorrectingDirectory(),
    ))

    parsed = client.post(
        "/api/v1/copilot/upload-portfolio-ocr",
        files={"file": ("holding.png", b"bounded-image", "image/png")},
    )

    assert parsed.status_code == 200, parsed.text
    position = parsed.json()["positions"][0]
    assert position["asset_id"] == "002185.SZ"
    assert position["identity_candidates"][0]["source"] == "test exact-name official directory"
    assert position["review_reasons"] == ["SECURITY_CODE_CORRECTED"]
    assert position["needs_review"] is True
    store.close()
    reset_runtime_mode_controller(DataMode.MOCK)


def test_live_ocr_replaces_static_fallback_with_real_quote_before_confirmation(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.llm.ocr_portfolio_parser.OCRPortfolioParser.get_instance",
        lambda: FakeOcrParser(),
    )
    reset_runtime_mode_controller(DataMode.LIVE)
    store = SQLiteDecisionEventStore(":memory:")
    client = TestClient(create_app(store, live_finance_provider=FakeLiveFinance()))
    headers = {"X-Owner-ID": "live-ocr-owner"}

    parsed = client.post(
        "/api/v1/advisor/portfolio/ocr",
        headers=headers,
        files={"file": ("holding.png", b"bounded-image", "image/png")},
    )

    assert parsed.status_code == 200
    draft = parsed.json()
    position = draft["positions"][0]
    assert position["price"] == 310.25
    assert position["market_value_cny"] == 31025.0
    assert position["observed_at"] == "2026-09-14T14:30:00+08:00"
    assert position["price_source"] == "verified-live-test-provider"
    assert position["sector"] == "Unclassified"
    assert position["cost_price"] is None
    assert "MISSING_OBSERVED_FIELDS" not in position["review_reasons"]

    confirmed = client.post(
        "/api/v1/advisor/portfolio/ocr/confirm",
        headers=headers,
        json={
            "owner_id": "live-ocr-owner",
            "image_digest": draft["image_digest"],
            "positions": draft["positions"],
            "cash_cny": 0,
        },
    )
    assert confirmed.status_code == 200
    saved = confirmed.json()["positions"][0]
    assert saved["price"] == 310.25
    assert saved["sector"] == "Unclassified"
    contract_position = confirmed.json()["portfolio"]["position_snapshot"]["positions"][0]
    assert contract_position["source"] == "verified-live-test-provider"
    assert contract_position["as_of"] == "2026-09-14T14:30:00+08:00"
    store.close()
    reset_runtime_mode_controller(DataMode.MOCK)


def test_live_ocr_confirmation_rejects_unverified_static_price() -> None:
    reset_runtime_mode_controller(DataMode.LIVE)
    store = SQLiteDecisionEventStore(":memory:")
    client = TestClient(create_app(store))

    response = client.post(
        "/api/v1/advisor/portfolio/ocr/confirm",
        headers={"X-Owner-ID": "live-ocr-owner"},
        json={
            "owner_id": "live-ocr-owner",
            "image_digest": "a" * 64,
            "cash_cny": 0,
            "positions": [{
                "asset_id": "300750.SZ",
                "name": "宁德时代",
                "asset_class": "STOCK",
                "quantity": 100,
                "price": 258.6,
                "review_reasons": ["MISSING_OBSERVED_FIELDS"],
            }],
        },
    )

    assert response.status_code == 422
    assert response.json()["error_code"] == "LIVE_OCR_PRICE_REQUIRED"
    assert store.get_current_portfolio("live-ocr-owner", "LIVE") is None
    store.close()
    reset_runtime_mode_controller(DataMode.MOCK)


def test_live_validation_does_not_trust_packaged_or_client_stock_sector() -> None:
    reset_runtime_mode_controller(DataMode.LIVE)
    store = SQLiteDecisionEventStore(":memory:")
    client = TestClient(create_app(store))

    response = client.post(
        "/api/v1/copilot/validate-portfolio-ocr",
        headers={"X-Owner-ID": "live-sector-owner"},
        json={
            "owner_id": "live-sector-owner",
            "cash_cny": 0,
            "positions": [{
                "asset_id": "300750.SZ",
                "name": "宁德时代",
                "asset_class": "STOCK",
                "sector": "Technology",
                "quantity": 100,
                "price": 310.25,
                "observed_at": "2026-09-14T14:30:00+08:00",
            }],
        },
    )

    assert response.status_code == 200
    assert response.json()["positions"][0]["sector"] == "Unclassified"
    assert response.json()["portfolio"]["position_snapshot"]["positions"][0]["sector"] == "Unclassified"
    store.close()
    reset_runtime_mode_controller(DataMode.MOCK)
