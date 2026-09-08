import asyncio
from datetime import UTC, datetime
from decimal import Decimal

from app.llm.ocr_portfolio_parser import recalculate_portfolio_values
from app.optimization import PortfolioOptimizationRequest
from app.portfolio import PortfolioImportBundle
from app.rebalancing import PortfolioRebalancingRequest
from app.service import FixturePortfolioOptimizationService, PortfolioRebalancingService
from app.service.profile_confirmation import confirm_questionnaire


def test_cash_floor_and_executable_portfolio_are_independently_checked():
    owner = "closed-loop-owner"
    service = FixturePortfolioOptimizationService()
    template = service.template(owner)
    profile = confirm_questionnaire(template.questionnaire)
    rows = [
        {"asset_id": symbol, "quantity": quantity, "price": price}
        for symbol, quantity, price in [
            ("600519.SH", 600, 1309.3), ("300750.SZ", 1000, 335.49),
            ("601318.SH", 800, 55.77), ("688981.SH", 2000, 121.55),
            ("600276.SH", 1500, 45.72),
        ]
    ]
    bundle = PortfolioImportBundle.model_validate(recalculate_portfolio_values(rows, Decimal(28000), owner)["portfolio"])
    request = PortfolioOptimizationRequest(
        request_id="closed-loop", owner_id=owner, generated_at=datetime.now(UTC),
        questionnaire=template.questionnaire, portfolio=bundle, confirmed_profile=profile,
        minimum_cash_pct=Decimal(5),
    )
    targets = asyncio.run(service.run(request))
    assert targets.status == "READY"
    weights = {row.target_id: row.target_weight_pct for row in targets.targets}
    assert weights["CASH-CNY"] >= 5
    assert sum(weights.values()) == 100
    plan = PortfolioRebalancingService().plan_rebalancing(PortfolioRebalancingRequest(
        request_id="closed-loop-trades", owner_id=owner, generated_at=request.generated_at,
        bundle=bundle, target_weights=weights, confirmed_profile=profile, minimum_cash_pct=Decimal(5),
    ))
    assert plan.execution_steps
    assert plan.post_trade_health is not None
    assert plan.post_trade_health.cash_weight_pct >= 5
    assert all(step.shares % 100 == 0 for step in plan.execution_steps)
    assert plan.post_trade_health.total_market_value_cny == plan.metrics.total_portfolio_value_cny - plan.metrics.net_turnover_cost
    if plan.post_trade_health.status != "PASS":
        assert plan.status == "REVIEW_REQUIRED"
        assert any("完整体检未通过" in issue for issue in plan.issues)


def test_missing_cash_bucket_refuses_floor_instead_of_false_ready():
    service = FixturePortfolioOptimizationService()
    template = service.template("cash-missing")
    request = PortfolioOptimizationRequest(
        request_id="missing-cash", owner_id="cash-missing", generated_at=datetime.now(UTC),
        questionnaire=template.questionnaire, portfolio=template.portfolio, minimum_cash_pct=Decimal(100),
    )
    result = asyncio.run(service.run(request))
    assert result.status != "READY"
