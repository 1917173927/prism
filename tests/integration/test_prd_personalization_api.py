from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.providers.live_market import MarketDataProvider


class QuoteProvider(MarketDataProvider):
    async def get_quote(self, code: str):
        raise AssertionError("index routes must not use equity quotes")

    async def get_index_quote(self, code: str):
        assert code == "000001.SH"
        return {
            "symbol": "000001.SH",
            "price_cny": 3200.5,
            "change_pct": 0.25,
            "observed_at": datetime.now(UTC).isoformat(),
            "source": "test quote",
            "is_synthetic": False,
        }


def test_owner_preferences_are_persistent_and_trading_stays_disabled(tmp_path):
    with TestClient(create_app(database_path=tmp_path / "preferences.sqlite3")) as client:
        headers = {"X-Owner-ID": "alice"}
        initial = client.get("/api/v1/user/preferences", headers=headers)
        assert initial.status_code == 200
        assert initial.json()["holdings_data_enabled"] is False
        update = client.put("/api/v1/user/preferences", headers=headers, json={
            "owner_id": "alice", "theme": "DARK", "holdings_data_enabled": True,
            "market_data_enabled": False,
        })
        assert update.status_code == 200
        assert update.json()["trading_enabled"] is False
        assert client.get("/api/v1/user/preferences", headers=headers).json()["theme"] == "DARK"
        assert client.get("/api/v1/user/preferences", headers={"X-Owner-ID": "bob"}).json()["theme"] == "LIGHT"


def test_market_assessment_never_fabricates_unknown_or_unauthorized_quotes(tmp_path):
    with TestClient(create_app(database_path=tmp_path / "market.sqlite3", market_provider=QuoteProvider())) as client:
        headers = {"X-Owner-ID": "alice"}
        known = client.get("/api/v1/market-assessments/%E4%B8%8A%E8%AF%81%E6%8C%87%E6%95%B0", headers=headers)
        assert known.status_code == 200
        assert known.json()["status"] == "CALCULATED"
        assert known.json()["price"] == "3200.5"
        unknown = client.get("/api/v1/market-assessments/%E6%9C%AA%E7%9F%A5%E6%8C%87%E6%95%B0", headers=headers)
        assert unknown.status_code == 200
        assert unknown.json()["status"] == "REVIEW_REQUIRED"
        assert unknown.json()["price"] is None
        client.put("/api/v1/user/preferences", headers=headers, json={
            "owner_id": "alice", "theme": "LIGHT", "holdings_data_enabled": False,
            "market_data_enabled": False,
        })
        disabled = client.get("/api/v1/market-assessments/%E4%B8%8A%E8%AF%81%E6%8C%87%E6%95%B0", headers=headers)
        assert disabled.json()["status"] == "REVIEW_REQUIRED"
        assert disabled.json()["price"] is None
