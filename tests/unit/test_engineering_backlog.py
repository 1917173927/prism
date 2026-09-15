from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
import shutil
import subprocess
from time import perf_counter

import pytest

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.llm.ocr_portfolio_parser import (
    levenshtein_similarity,
    resolve_security_name,
    validate_portfolio_values,
)
from app.providers.live_market import A_SHARE_DATABASE, CompositeMarketProvider, MarketDataProvider
from app.portfolio.contracts import AssetType, PortfolioImportBundle, Position, PositionSnapshot
from app.rebalancing.contracts import PortfolioRebalancingRequest, RebalancingActionType
from app.service.portfolio_rebalancing import PortfolioRebalancingService, trade_fees
from app.scenarios import CustomStressScenarioRequest, calculate_custom_stress


class _FailingProvider(MarketDataProvider):
    async def get_quote(self, code: str):
        raise TimeoutError("504 upstream timeout")


class _QuoteProvider(MarketDataProvider):
    async def get_quote(self, code: str):
        return {"symbol": f"{code}.SZ", "name": "宁德时代", "price_cny": 260.0,
                "change_pct": 1.0, "observed_at": datetime.now(UTC).isoformat(), "source": "test"}


class _SlowProvider(MarketDataProvider):
    async def get_quote(self, code: str):
        await asyncio.sleep(5)
        return None


def test_market_provider_504_falls_back_to_secondary_without_error():
    provider = CompositeMarketProvider(primary=_FailingProvider(), secondary=_QuoteProvider())
    result = asyncio.run(provider.get_quote("300750"))
    assert result is not None
    assert result["provider_tier"] == "LIVE_SECONDARY"
    assert result["quote_latency_ms"] >= 0
    assert result["staleness_seconds"] >= 0


def test_market_provider_total_deadline_includes_static_fallback():
    provider = CompositeMarketProvider(
        primary=_SlowProvider(), secondary=_SlowProvider(), total_timeout_seconds=2.0
    )
    started = perf_counter()
    result = asyncio.run(provider.get_quote("300750"))
    elapsed = perf_counter() - started
    assert result is not None
    assert result["provider_tier"] == "STATIC_FALLBACK"
    assert result["staleness_seconds"] > 0
    assert elapsed < 2.0


def test_market_provider_504_downgrade_is_http_200():
    original = deepcopy(A_SHARE_DATABASE["300750"])
    provider = CompositeMarketProvider(primary=_FailingProvider(), secondary=_QuoteProvider())
    try:
        client = TestClient(create_app(market_provider=provider))
        response = client.post("/api/v1/copilot/auto-index-security", params={"symbol": "300750"})
        assert response.status_code == 200
        assert response.json()["data"]["provider_tier"] == "LIVE_SECONDARY"
    finally:
        A_SHARE_DATABASE["300750"] = original


def test_mock_quote_exposes_static_snapshot_freshness_instead_of_live_zero():
    client = TestClient(create_app())
    response = client.get("/api/v1/copilot/live-quote", params={"symbol": "300750"})
    assert response.status_code == 200
    body = response.json()
    quote = body["data"]
    context = body["execution_context"]
    assert quote["provider_tier"] == "STATIC_FALLBACK"
    assert quote["observed_at"]
    assert quote["staleness_seconds"] > 0
    assert context["staleness_seconds"] == quote["staleness_seconds"]
    assert context["is_synthetic"] is True


def test_ocr_fuzzy_name_correction_and_deterministic_checks():
    assert levenshtein_similarity("宁德时伐", "宁德时代") >= 0.85
    assert levenshtein_similarity("宁德", "招商银行") < 0.85
    assert resolve_security_name(["30075O", "宁德时伐", "100", "250", "25000"]) == "300750"
    positions = [{"quantity": 99, "price": 10, "market_value_cny": 990,
                  "asset_class": "EQUITY", "needs_review": False, "review_reasons": []}]
    validation = validate_portfolio_values(positions, 10, 1000)
    assert validation["weights_balanced"] is True
    assert positions[0]["confidence_level"] == "REVIEW_REQUIRED"
    assert any("ODD_LOT_REVIEW" in reason for reason in positions[0]["review_reasons"])


def test_ocr_confirmation_recalculates_and_returns_owner_scoped_portfolio():
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/copilot/validate-portfolio-ocr",
        headers={"X-Owner-ID": "ocr-owner"},
        json={
            "owner_id": "ocr-owner",
            "cash_cny": "1000.00",
            "positions": [
                {
                    "asset_id": "300750.SZ", "name": "宁德时代", "asset_class": "EQUITY",
                    "quantity": 101, "price": "10.005", "market_value_cny": 1,
                    "confidence": 0.99, "confidence_pct": 99, "needs_review": False,
                    "review_reasons": [],
                },
                {
                    "asset_id": "588000.SH", "name": "科创50ETF", "asset_class": "FUND_ETF",
                    "quantity": 100, "price": "1.00", "market_value_cny": 100,
                    "confidence": 0.99, "confidence_pct": 99, "needs_review": False,
                    "review_reasons": [],
                },
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["positions"][0]["market_value_cny"] == 1010.51
    assert body["portfolio"]["owner_id"] == "ocr-owner"
    assert body["portfolio"]["position_snapshot"]["positions"][0]["sector"] == "Industrials"
    assert len(body["portfolio"]["fund_holdings"]) == 1
    headers = {"X-Owner-ID": "ocr-owner"}
    template = client.get("/api/v1/advisor/query-template", headers=headers).json()
    profile = client.post(
        "/api/v1/advisor/context/profile",
        headers=headers,
        json={"schema_version": "profile-context-request.v1", "questionnaire": template["questionnaire"]},
    ).json()["profile"]
    health = client.post(
        "/api/v1/advisor/portfolio-health",
        headers=headers,
        json={
            "schema_version": "portfolio-health-request.v1", "request_id": "ocr-health",
            "owner_id": "ocr-owner", "calculated_at": datetime.now(UTC).isoformat(),
            "portfolio": body["portfolio"], "profile": profile,
        },
    )
    assert health.status_code == 200
    assert health.json()["source_exposure_status"] == "COMPLETE"
    denied = client.post(
        "/api/v1/copilot/validate-portfolio-ocr",
        headers={"X-Owner-ID": "other-owner"},
        json={"owner_id": "ocr-owner", "cash_cny": 0, "positions": []},
    )
    assert denied.status_code == 403


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


def test_rebalancing_allows_odd_lot_only_for_full_liquidation_and_minimum_commission():
    now = datetime.now(UTC)
    stock = Position(
        position_id="odd", owner_id="owner", asset_id="300750.SZ", asset_type=AssetType.STOCK,
        asset_name="宁德时代", sector="Industrials", quantity=1050, market_value=10500,
        currency="CNY", as_of=now, source="test",
    )
    cash = Position(
        position_id="cash", owner_id="owner", asset_id="CASH-CNY", asset_type=AssetType.CASH,
        asset_name="现金", sector="Cash", quantity=10500, market_value=10500,
        currency="CNY", as_of=now, source="test",
    )
    snapshot = PositionSnapshot(
        snapshot_id="odd-snap", owner_id="owner", as_of=now, base_currency="CNY",
        source="test", positions=(stock, cash),
    )
    bundle = PortfolioImportBundle(
        bundle_id="odd-bundle", owner_id="owner", created_at=now, position_snapshot=snapshot
    )
    result = PortfolioRebalancingService().plan_rebalancing(PortfolioRebalancingRequest(
        request_id="odd-clear", owner_id="owner", generated_at=now, bundle=bundle,
        target_weights={"300750.SZ": 0, "CASH-CNY": 100}, max_turnover_pct=100,
        round_to_lot=True,
    ))
    sold = next(action for action in result.actions if action.asset_id == "300750.SZ")
    assert sold.shares == 1050
    assert trade_fees(Decimal("1000.00"), False)["commission"] == Decimal("5.00")


def test_custom_stress_uses_portfolio_contract_instead_of_ui_weights():
    now = datetime.now(UTC)
    positions = (
        Position(position_id="tech", owner_id="owner", asset_id="688981.SH", asset_type=AssetType.STOCK,
                 asset_name="中芯国际", sector="Technology", quantity=100, market_value=25000,
                 currency="CNY", as_of=now, source="test"),
        Position(position_id="industry", owner_id="owner", asset_id="300750.SZ", asset_type=AssetType.STOCK,
                 asset_name="宁德时代", sector="Industrials", quantity=100, market_value=25000,
                 currency="CNY", as_of=now, source="test"),
        Position(position_id="consumer", owner_id="owner", asset_id="600519.SH", asset_type=AssetType.STOCK,
                 asset_name="贵州茅台", sector="Consumer", quantity=10, market_value=20000,
                 currency="CNY", as_of=now, source="test"),
        Position(position_id="finance", owner_id="owner", asset_id="600036.SH", asset_type=AssetType.STOCK,
                 asset_name="招商银行", sector="Finance", quantity=100, market_value=20000,
                 currency="CNY", as_of=now, source="test"),
        Position(position_id="cash", owner_id="owner", asset_id="CASH-CNY", asset_type=AssetType.CASH,
                 asset_name="现金", sector="Cash", quantity=10000, market_value=10000,
                 currency="CNY", as_of=now, source="test"),
    )
    portfolio = PortfolioImportBundle(
        bundle_id="stress-bundle", owner_id="owner", created_at=now,
        position_snapshot=PositionSnapshot(
            snapshot_id="stress-snap", owner_id="owner", as_of=now, base_currency="CNY",
            source="test", positions=positions,
        ),
    )
    result = calculate_custom_stress(_stress_request(
        owner_id="owner", portfolio=portfolio, portfolio_value_cny=None, sector_weights_pct=None,
    ))
    assert result.scenario_return_pct == Decimal("-5.00")
    assert result.scenario_pnl_cny == Decimal("-5000.00")


def test_frontend_keeps_safe_dom_and_renders_sector_result_below_chart():
    static_root = Path(__file__).resolve().parents[2] / "app" / "api" / "static"
    script = (static_root / "app.js").read_text(encoding="utf-8")
    page = (static_root / "index.html").read_text(encoding="utf-8")
    assert "innerHTML" not in script
    assert "outerHTML" not in script
    assert "WENCAI_SKILLHUB_API_KEY" not in script
    assert "Authorization: Bearer" not in script
    assert "state.profileContext" not in script
    assert "state.portfolioContext" not in script
    assert "pos.market_value_cny = Math.round" not in script
    assert 'store.portfolio = null;' in script
    assert 'store.portfolioHealthRun = null;' in script
    assert 'byId("donut-sector-detail")' in script
    assert "renderSectorDetail(s);" in script
    assert 'quote.valuation_observed_at || "未提供"' in script
    assert 'risk_score: "35.00"' not in script
    assert 'tech_exposure_pct: "38.50"' not in script
    assert 'await refreshPortfolioHealth()' in script
    assert 'liveCapabilities.portfolio_refresh === true' in script
    assert 'liveCapabilities.stock_quote === true' in script
    assert 'liveCapabilities.stock_quote === true && state.wencaiConfigured === true' not in script
    assert 'status: "BLOCKED"' in script
    assert 'error.errorCode = payload?.error_code || null' in script
    assert 'err.errorCode === "LIVE_PORTFOLIO_REFRESH_REQUIRED"' in script
    assert 'state.portfolioOptimizationRun = null' in script
    assert 'state.portfolioRefreshRun?.status !== "COMPLETE"' in script
    assert "当前真实持仓 · Python 确定性计算" in script
    assert '["fuyao_finance_api", "wencai_skillhub_provider"].includes(' in script
    assert 'id="donut-sector-detail"' in page
    assert page.index('id="copilot-donut-legend"') < page.index('id="donut-sector-detail"')
    assert "为什么得到这个分析结果？" in page
    assert "先看结论和关键原因，需要时再展开专业计算依据" in page
    assert "穿透证据链与确定性计算流转底稿" not in page
    assert 'track.setAttribute("role", "img")' in script
    assert 'details.className = "evidence-professional-details"' in script
    assert 'processFlow.className = "evidence-process-flow"' in script
    profile_modal = page.index('id="profile-edit-modal"')
    evidence_modal = page.index('id="evidence-lineage-modal"')
    assert page.rfind("</div>", profile_modal, evidence_modal) > profile_modal


def test_micro_store_rejects_stale_persona_results_and_invalidates_mode_runs():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the frontend state lifecycle regression")
    script_path = Path(__file__).resolve().parents[2] / "app" / "api" / "static" / "app.js"
    script = script_path.read_text(encoding="utf-8")
    prefix, separator, _ = script.partition("  microStore.subscribe((store) => {")
    assert separator, "unable to isolate Micro-Store implementation"
    probe = prefix + r'''
  state.ownerId = "demo-owner";
  state.selectedPersona = "persona-a";
  state.profile = {profile: {risk_level: "BALANCED"}};
  state.portfolio = {bundle_id: "portfolio-a"};
  state.portfolioHealthRun = {request_id: "health-a"};
  const staleToken = beginContextRequest("portfolioHealthSequence");
  state.selectedPersona = "persona-b";
  if (isContextRequestCurrent(staleToken)) throw new Error("stale persona token accepted");
  if (state.portfolioHealthRun !== null) throw new Error("persona change retained health result");

  DERIVED_RUN_KEYS.forEach((key) => { state[key] = {source: "MOCK"}; });
  const sequenceBefore = Object.fromEntries(
    DERIVED_SEQUENCE_KEYS.map((key) => [key, state[key]])
  );
  state.dataMode = "LIVE";
  if (DERIVED_RUN_KEYS.some((key) => state[key] !== null)) {
    throw new Error("mode change retained a derived result");
  }
  if (DERIVED_SEQUENCE_KEYS.some((key) => state[key] <= sequenceBefore[key])) {
    throw new Error("mode change did not invalidate an in-flight sequence");
  }
  process.stdout.write("PASS");
})();
'''
    completed = subprocess.run(
        [node, "-e", probe], capture_output=True, text=True, check=False, timeout=10
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "PASS"
