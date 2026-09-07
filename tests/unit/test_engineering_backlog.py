from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.llm.ocr_portfolio_parser import resolve_security_name, validate_portfolio_values
from app.providers.live_market import CompositeMarketProvider, MarketDataProvider
from app.portfolio.contracts import AssetType, PortfolioImportBundle, Position, PositionSnapshot
from app.rebalancing.contracts import PortfolioRebalancingRequest, RebalancingActionType
from app.service.portfolio_rebalancing import PortfolioRebalancingService
from app.scenarios import CustomStressScenarioRequest, calculate_custom_stress


class _FailingProvider(MarketDataProvider):
    async def get_quote(self, code: str):
        raise TimeoutError("504 upstream timeout")


class _QuoteProvider(MarketDataProvider):
    async def get_quote(self, code: str):
        return {"symbol": f"{code}.SZ", "name": "宁德时代", "price_cny": 260.0,
                "change_pct": 1.0, "observed_at": datetime.now(UTC).isoformat(), "source": "test"}


def test_market_provider_504_falls_back_to_secondary_without_error():
    provider = CompositeMarketProvider(primary=_FailingProvider(), secondary=_QuoteProvider())
    result = asyncio.run(provider.get_quote("300750"))
    assert result is not None
    assert result["provider_tier"] == "LIVE_SECONDARY"
    assert result["quote_latency_ms"] >= 0
    assert result["staleness_seconds"] >= 0


def test_ocr_fuzzy_name_correction_and_deterministic_checks():
    assert resolve_security_name(["30075O", "宁德时伐", "100", "250", "25000"]) == "300750"
    positions = [{"quantity": 99, "price": 10, "market_value_cny": 990,
                  "asset_class": "EQUITY", "needs_review": False, "review_reasons": []}]
    validation = validate_portfolio_values(positions, 10, 1000)
    assert validation["weights_balanced"] is True
    assert positions[0]["confidence_level"] == "REVIEW_REQUIRED"
    assert any("ODD_LOT_REVIEW" in reason for reason in positions[0]["review_reasons"])


def _stress_request(**overrides):
    values = dict(
        request_id="stress-1", owner_id="stress-owner", portfolio_value_cny=Decimal("500000"),
        sector_weights_pct={"TECHNOLOGY": 28, "INDUSTRIALS": 22, "CONSUMER_HEALTHCARE": 18,
                            "FINANCE_CYCLICAL": 14, "CASH": 18},
        sector_shocks_pct={"TECHNOLOGY": -20, "INDUSTRIALS": 0, "CONSUMER_HEALTHCARE": 0,
                           "FINANCE_CYCLICAL": 0, "CASH": 0},
    )
    values.update(overrides)
    return CustomStressScenarioRequest(**values)


def test_custom_stress_calculates_loss_volatility_and_var():
    result = calculate_custom_stress(_stress_request())
    assert result.scenario_return_pct == Decimal("-5.60")
    assert result.scenario_pnl_cny == Decimal("-28000.00")
    assert result.baseline_var_95_1d_cny > 0
    assert result.stressed_var_95_1d_cny > 0


def test_custom_stress_api_owner_scope():
    client = TestClient(create_app())
    payload = _stress_request().model_dump(mode="json")
    ok = client.post("/api/v1/advisor/custom-stress-scenarios", headers={"X-Owner-ID": "stress-owner"}, json=payload)
    assert ok.status_code == 200
    denied = client.post("/api/v1/advisor/custom-stress-scenarios", headers={"X-Owner-ID": "other"}, json=payload)
    assert denied.status_code in (403, 422)


def test_rebalancing_uses_lots_and_reports_cent_accurate_fees():
    now = datetime.now(UTC)
    positions = (
        Position(position_id="p-a", owner_id="owner", asset_id="300750.SZ", asset_type=AssetType.STOCK,
                 asset_name="宁德时代", quantity=1000, market_value=100000,
                 currency="CNY", as_of=now, source="test"),
        Position(position_id="p-b", owner_id="owner", asset_id="600036.SH", asset_type=AssetType.STOCK,
                 asset_name="招商银行", quantity=1000, market_value=50000,
                 currency="CNY", as_of=now, source="test"),
        Position(position_id="cash", owner_id="owner", asset_id="CASH-CNY", asset_type=AssetType.CASH,
                 asset_name="现金", quantity=50000, market_value=50000,
                 currency="CNY", as_of=now, source="test"),
    )
    snapshot = PositionSnapshot(snapshot_id="snap", owner_id="owner", as_of=now, base_currency="CNY",
                                source="test", positions=positions)
    bundle = PortfolioImportBundle(bundle_id="bundle", owner_id="owner", created_at=now,
                                   position_snapshot=snapshot)
    request = PortfolioRebalancingRequest(request_id="reb-lot", owner_id="owner", generated_at=now,
        bundle=bundle, target_weights={"300750.SZ": 25, "600036.SH": 50, "CASH-CNY": 25},
        max_turnover_pct=100, round_to_lot=True)
    result = PortfolioRebalancingService().plan_rebalancing(request)
    traded = [action for action in result.actions if action.action_type != RebalancingActionType.HOLD]
    assert all(action.shares % 100 == 0 for action in traded)
    sold = next(action for action in traded if action.asset_id == "300750.SZ")
    assert sold.shares == 500
    assert sold.stamp_duty == Decimal("25.00")
    assert sold.transfer_fee == Decimal("0.50")
    assert sold.commission == Decimal("12.50")
    assert sold.total_fees_cny == Decimal("38.00")
    assert result.metrics.net_turnover_cost > 0


def test_frontend_keeps_safe_dom_and_renders_sector_result_below_chart():
    static_root = Path(__file__).resolve().parents[2] / "app" / "api" / "static"
    script = (static_root / "app.js").read_text(encoding="utf-8")
    page = (static_root / "index.html").read_text(encoding="utf-8")
    assert "innerHTML" not in script
    assert "outerHTML" not in script
    assert 'byId("donut-sector-detail")' in script
    assert "renderSectorDetail(s);" in script
    assert 'id="donut-sector-detail"' in page
    assert page.index('id="copilot-donut-legend"') < page.index('id="donut-sector-detail"')
    profile_modal = page.index('id="profile-edit-modal"')
    evidence_modal = page.index('id="evidence-lineage-modal"')
    assert page.rfind("</div>", profile_modal, evidence_modal) > profile_modal
