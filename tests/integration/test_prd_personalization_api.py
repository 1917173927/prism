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

    async def get_index_history(self, code: str):
        assert code == "000001.SH"
        return [{"time": "2026-09-14", "open": 3190, "high": 3210, "low": 3180, "close": 3200.5}]


class AnalysisProvider(QuoteProvider):
    async def get_index_quote(self, code: str):
        return {
            "symbol": code, "price_cny": 3200.5, "change_pct": 0.25,
            "observed_at": datetime.now(UTC).isoformat(), "source": "test quote", "is_synthetic": False,
        }

    async def get_index_history(self, code: str, *, start=None, end=None):
        assert code == "000001.SH" and start < end
        return [
            {"time": "2026-08-29", "open": 3180, "high": 3210, "low": 3170, "close": 3200,
             "volume": 100, "turnover": 1000},
            {"time": "2026-09-14", "open": 3190, "high": 3220, "low": 3180, "close": 3200.5,
             "volume": 120, "turnover": 1300},
        ]


def test_owner_theme_is_persistent_and_data_source_policy_is_fixed(tmp_path):
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
        assert update.json()["holdings_data_enabled"] is False
        assert update.json()["market_data_enabled"] is True
        saved = client.get("/api/v1/user/preferences", headers=headers).json()
        assert saved["theme"] == "DARK"
        assert saved["holdings_data_enabled"] is False
        assert saved["market_data_enabled"] is True
        assert client.get("/api/v1/user/preferences", headers={"X-Owner-ID": "bob"}).json()["theme"] == "LIGHT"


def test_market_assessment_never_fabricates_unknown_quotes_and_market_data_is_required(tmp_path):
    with TestClient(create_app(database_path=tmp_path / "market.sqlite3", market_provider=QuoteProvider())) as client:
        headers = {"X-Owner-ID": "alice"}
        known = client.get("/api/v1/market-assessments/%E4%B8%8A%E8%AF%81%E6%8C%87%E6%95%B0", headers=headers)
        assert known.status_code == 200
        assert known.json()["status"] == "CALCULATED"
        assert known.json()["price"] == "3200.5"
        assert known.json()["history_status"] == "LIVE"
        assert len(known.json()["bars"]) == 1
        unknown = client.get("/api/v1/market-assessments/%E6%9C%AA%E7%9F%A5%E6%8C%87%E6%95%B0", headers=headers)
        assert unknown.status_code == 200
        assert unknown.json()["status"] == "REVIEW_REQUIRED"
        assert unknown.json()["price"] is None
        client.put("/api/v1/user/preferences", headers=headers, json={
            "owner_id": "alice", "theme": "LIGHT", "holdings_data_enabled": False,
            "market_data_enabled": False,
        })
        still_required = client.get("/api/v1/market-assessments/%E4%B8%8A%E8%AF%81%E6%8C%87%E6%95%B0", headers=headers)
        assert still_required.json()["status"] == "CALCULATED"
        assert still_required.json()["price"] == "3200.5"


def test_cross_market_catalog_and_analysis_keep_unverified_overseas_data_unavailable(tmp_path):
    with TestClient(create_app(database_path=tmp_path / "analysis.sqlite3", market_provider=AnalysisProvider())) as client:
        headers = {"X-Owner-ID": "alice"}
        catalog = client.get("/api/v1/market/catalog", headers=headers)
        assert catalog.status_code == 200
        assert {row["market"] for row in catalog.json()} == {"CN", "HK", "US"}
        assert len(catalog.json()) == 12
        quotes = client.get("/api/v1/market/quotes/CN", headers=headers)
        assert quotes.status_code == 200
        assert len(quotes.json()) == 4
        assert all(row["status"] == "LIVE" for row in quotes.json())
        assert client.get("/api/v1/market/quotes/EU", headers=headers).status_code == 404
        cn = client.get("/api/v1/market/analysis/CN/sse-composite?interval=1d", headers=headers)
        assert cn.status_code == 200
        body = cn.json()
        assert body["status"] == "CALCULATED"
        assert body["history_status"] == "LIVE"
        assert body["volume"]["latest_volume"] == "120"
        assert set(body["indicators"]) == {"boll", "macd", "kdj", "parameters"}
        hk = client.get("/api/v1/market/analysis/HK/hang-seng", headers=headers)
        assert hk.status_code == 200
        assert hk.json()["status"] == "REVIEW_REQUIRED"
        assert hk.json()["price"] is None
        assert "权限" in hk.json()["source"]
        monthly = client.get("/api/v1/market/analysis/CN/sse-composite?interval=1M", headers=headers)
        assert monthly.status_code == 200
        assert monthly.json()["history_status"] == "REVIEW_REQUIRED"
        assert client.get("/api/v1/market/analysis/CN/sse-composite?interval=5m", headers=headers).status_code == 422
        assert client.get("/api/v1/market/analysis/EU/not-registered", headers=headers).status_code == 404
