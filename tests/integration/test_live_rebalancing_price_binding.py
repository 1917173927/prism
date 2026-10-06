"""Controlled regression of LIVE provenance; not an upstream capacity test."""
from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.portfolio import AssetType, PortfolioImportBundle, Position, PositionSnapshot
from app.runtime.mode import DataMode, reset_runtime_mode_controller
from app.service import FixtureAdvisorQueryService, confirm_questionnaire
from app.store import SQLiteDecisionEventStore


NOW = datetime(2026, 10, 6, 8, tzinfo=UTC)
OWNER = "live-price-binding-owner"
SECURITIES = (
    ("600001.SH", 3700, "Consumer"),
    ("000001.SZ", 1500, "Technology"),
    ("600002.SH", 1500, "Industrials"),
    ("600003.SH", 1300, "Finance"),
)


class ControlledQuoteProvider:
    is_configured = True

    async def get_quote(self, code):
        return {"symbol": code, "name": code, "price_cny": "10",
                "observed_at": NOW.isoformat(), "source": "controlled regression quote",
                "is_synthetic": False}

    async def get_fund_lookthrough(self, code):
        return None


class ControlledIndustryProvider:
    async def get_industry(self, code):
        sector = next(sector for symbol, _, sector in SECURITIES if symbol == code)
        return {"sector": sector, "industry": (sector,), "name": code,
                "source": "controlled regression industry", "retrieved_at": NOW.isoformat()}


def initial_portfolio():
    positions = tuple(Position(
        position_id=code, owner_id=OWNER, asset_id=code, asset_type=AssetType.STOCK,
        asset_name=code, sector=sector, quantity=Decimal(quantity),
        market_value=Decimal(quantity * 10), currency="CNY", as_of=NOW, source="user import",
    ) for code, quantity, sector in SECURITIES)
    positions += (Position(position_id="cash", owner_id=OWNER, asset_id="CASH-CNY",
        asset_type=AssetType.CASH, asset_name="现金", sector="Cash", quantity=Decimal("20000"),
        market_value=Decimal("20000"), currency="CNY", as_of=NOW, source="user-confirmed cash"),)
    return PortfolioImportBundle(bundle_id="live-price-audit", owner_id=OWNER, created_at=NOW,
        position_snapshot=PositionSnapshot(snapshot_id="live-price-audit", owner_id=OWNER,
            as_of=NOW, base_currency="CNY", source="user import", positions=positions))


def test_live_regular_rebalancing_binds_prices_and_lots_to_refreshed_snapshot():
    reset_runtime_mode_controller(DataMode.LIVE)
    store = SQLiteDecisionEventStore()
    app = create_app(store, clock=lambda: NOW, live_finance_provider=ControlledQuoteProvider(),
                     industry_provider=ControlledIndustryProvider())
    headers = {"X-Owner-ID": OWNER}
    with TestClient(app) as client:
        refreshed = client.post("/api/v1/advisor/portfolio/refresh", headers=headers, json={
            "schema_version": "portfolio-refresh-request.v1", "request_id": "bind-real-route",
            "owner_id": OWNER, "as_of": NOW.isoformat(),
            "portfolio": initial_portfolio().model_dump(mode="json"),
        })
        assert refreshed.status_code == 200
        assert refreshed.json()["status"] == "COMPLETE"
        bundle = refreshed.json()["portfolio"]
        profile = confirm_questionnaire(FixtureAdvisorQueryService().query_template(OWNER).questionnaire)
        assert profile.risk_level.value == "BALANCED"
        body = {
            "request_id": "bound-price-rebalance", "owner_id": OWNER, "generated_at": NOW.isoformat(),
            "bundle": bundle, "confirmed_profile": profile.model_dump(mode="json"),
            "target_weights": {"600001.SH": "35", "000001.SZ": "15", "600002.SH": "15",
                               "600003.SH": "13", "CASH-CNY": "22"},
            "prices_cny": {"600001.SH": "10"}, "round_to_lot": True,
        }
        # Deliberately use the ordinary route with no personal policy reference.
        baseline = client.post("/api/v1/advisor/rebalancing-runs", headers=headers, json=body)
        tampered = client.post("/api/v1/advisor/rebalancing-runs", headers=headers, json={
            **body, "prices_cny": {"600001.SH": "20"}, "round_to_lot": False,
            "asset_types": {"600001.SH": "CASH"},
        })
        assert baseline.status_code == tampered.status_code == 200
        baseline_data, tampered_data = baseline.json(), tampered.json()
        assert tampered_data["status"] == baseline_data["status"]
        assert tampered_data["post_trade_health"] == baseline_data["post_trade_health"]
        assert tampered_data["metrics"] == baseline_data["metrics"]
        assert tampered_data["actions"] == baseline_data["actions"]
        assert tampered_data["execution_steps"] == baseline_data["execution_steps"]
        action = next(action for action in tampered_data["actions"] if action["asset_id"] == "600001.SH")
        assert Decimal(action["current_price_cny"]) == 10
        assert Decimal(action["shares"]) == 200
        assert all(Decimal(step["shares"]) % 100 == 0 for step in tampered_data["execution_steps"])
        # Before binding, malicious price=20 sold only 100 shares and falsely
        # passed a 36.002% actual holding against the BALANCED 35% limit.
        actual_remaining = Decimal("37000") - Decimal(action["shares"]) * 10
        actual_total = Decimal("100000") - Decimal(tampered_data["metrics"]["net_turnover_cost"])
        assert actual_remaining / actual_total * 100 <= Decimal("35.01")
    store.close()
