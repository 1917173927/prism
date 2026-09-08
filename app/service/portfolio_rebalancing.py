"""Service for computing deterministic portfolio rebalancing plans."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN
import re

from app.gates import GateStatus
from app.portfolio.contracts import AssetType, PositionImportStatus
from app.rebalancing.contracts import (
    PortfolioRebalancingRequest,
    PortfolioRebalancingResponse,
    RebalancingAction,
    RebalancingActionType,
    RebalancingMetrics,
    RebalancingStep,
)


def _q2(val: Decimal) -> Decimal:
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def trade_fees(amount: Decimal, selling: bool, stock: bool = True) -> dict[str, Decimal]:
    """User-specified A-share model; each component rounded to CNY cents."""
    stamp = _q2(amount * Decimal("0.0005")) if selling and stock else Decimal("0.00")
    transfer = _q2(amount * Decimal("0.00001")) if stock else Decimal("0.00")
    commission = _q2(max(Decimal("5"), amount * Decimal("0.00025"))) if amount else Decimal("0.00")
    return dict(stamp_duty=stamp, transfer_fee=transfer, commission=commission,
                total_fees_cny=stamp + transfer + commission)


def _exchange_asset(asset_id: str) -> bool:
    return bool(re.fullmatch(r"\d{6}(?:\.(?:SH|SZ|BJ))?", asset_id))


class PortfolioRebalancingService:
    """Deterministic rebalancing planner."""

    def plan_rebalancing(
        self,
        request: PortfolioRebalancingRequest,
    ) -> PortfolioRebalancingResponse:
        positions = request.bundle.position_snapshot.positions
        if any(p.currency != "CNY" for p in positions):
            raise ValueError("Rebalancing requires CNY positions; FX conversion is unavailable")
        if len({p.asset_id for p in positions}) != len(positions):
            raise ValueError("Aggregate duplicate asset positions before rebalancing")
        total_val = sum((pos.market_value for pos in positions), start=Decimal("0"))

        if total_val <= Decimal("0"):
            raise ValueError("Portfolio total market value must be positive")

        actions: list[RebalancingAction] = []
        pos_by_asset = {pos.asset_id: pos for pos in positions}

        # Process existing positions
        for pos in positions:
            curr_weight = _q2((pos.market_value / total_val) * Decimal("100"))
            target_weight = _q2(request.target_weights.get(pos.asset_id, Decimal("0.00")))
            delta_weight = _q2(target_weight - curr_weight)
            target_val = _q2(total_val * target_weight / Decimal("100"))
            cash_delta = _q2(target_val - pos.market_value)

            if abs(delta_weight) <= request.deadband_pct:
                action_type = RebalancingActionType.HOLD
                rationale = f"权重偏差 {delta_weight}% 在死区阈值 (±{request.deadband_pct}%) 内，维持现状以降低交易摩擦"
            elif delta_weight > Decimal("0"):
                action_type = RebalancingActionType.BUY
                rationale = f"当前权重 {curr_weight}% 低于目标 {target_weight}%，建议加仓补足"
            elif target_weight == Decimal("0"):
                action_type = RebalancingActionType.SELL
                rationale = "目标权重为 0.00%，建议全部清仓移出"
            else:
                action_type = RebalancingActionType.REDUCE
                rationale = f"当前权重 {curr_weight}% 高于目标 {target_weight}%，建议减仓调优"

            actions.append(
                RebalancingAction(
                    asset_id=pos.asset_id,
                    asset_name=pos.asset_name,
                    asset_type=pos.asset_type,
                    current_weight_pct=curr_weight,
                    target_weight_pct=target_weight,
                    delta_weight_pct=delta_weight,
                    current_value_cny=pos.market_value,
                    target_value_cny=target_val,
                    cash_delta_cny=cash_delta,
                    action_type=action_type,
                    rationale=rationale,
                )
            )

        # Process new target assets not in current portfolio
        for asset_id, target_w in request.target_weights.items():
            if asset_id not in pos_by_asset and target_w > Decimal("0"):
                tw = _q2(target_w)
                tv = _q2(total_val * tw / Decimal("100"))
                actions.append(
                    RebalancingAction(
                        asset_id=asset_id,
                        asset_name=f"新增资产({asset_id})",
                        asset_type=request.asset_types.get(asset_id, AssetType.STOCK if _exchange_asset(asset_id) else AssetType.ETF),
                        current_weight_pct=Decimal("0.00"),
                        target_weight_pct=tw,
                        delta_weight_pct=tw,
                        current_value_cny=Decimal("0.00"),
                        target_value_cny=tv,
                        cash_delta_cny=tv,
                        action_type=RebalancingActionType.BUY,
                        rationale=f"新建目标仓位 {tw}%",
                    )
                )

        # Convert target amounts to executable quantities. Abstract fixture assets
        # retain amount-only semantics; exchange instruments require an observed price.
        cash_available = sum((p.market_value for p in positions if p.asset_type == AssetType.CASH), Decimal(0))
        execution_issues: list[str] = []
        adjusted: dict[str, RebalancingAction] = {}
        ordered = sorted(actions, key=lambda a: a.action_type == RebalancingActionType.BUY)
        for action in ordered:
            pos = pos_by_asset.get(action.asset_id)
            if action.asset_type == AssetType.CASH or action.action_type == RebalancingActionType.HOLD:
                adjusted[action.asset_id] = action.model_copy(update={
                    "cash_delta_cny": Decimal("0.00"), "delta_weight_pct": Decimal("0.00"),
                    "action_type": RebalancingActionType.HOLD, "shares": Decimal(0),
                    "rationale": "现金不直接下单，实际余额由证券交易及费用决定" if action.asset_type == AssetType.CASH else action.rationale,
                })
                continue
            if not _exchange_asset(action.asset_id):
                adjusted[action.asset_id] = action
                continue
            price = request.prices_cny.get(action.asset_id) or ((pos.market_value / pos.quantity) if pos else None)
            if not price or price <= 0:
                execution_issues.append(f"{action.asset_id}: 缺少有效报价，无法计算股数")
                adjusted[action.asset_id] = action.model_copy(update={"executable": False, "cash_delta_cny": Decimal(0), "delta_weight_pct": Decimal(0)})
                continue
            selling = action.action_type in (RebalancingActionType.SELL, RebalancingActionType.REDUCE)
            if pos and pos.quantity != pos.quantity.to_integral_value():
                raise ValueError("Exchange positions require integer quantities")
            lot = Decimal(100) if request.round_to_lot and action.asset_type in (AssetType.STOCK, AssetType.ETF) else Decimal(1)
            shares = (abs(action.cash_delta_cny) / price / lot).to_integral_value(rounding=ROUND_DOWN) * lot
            if selling and pos:
                shares = pos.quantity if action.target_weight_pct == 0 else min(shares, (pos.quantity // lot) * lot)
            rationale = action.rationale
            if shares == 0:
                rationale = f"目标偏差 {action.target_weight_pct - action.current_weight_pct}% 超过死区，但按 {lot} 股/份交易单位向下取整为 0，本项未执行，目标尚未达到"
                execution_issues.append(f"{action.asset_id}: {rationale}")
            stock = action.asset_type == AssetType.STOCK
            if not selling:
                # Bisection finds the largest affordable lot count including minimum fees.
                low, high = 0, int(shares / lot)
                while low < high:
                    middle = (low + high + 1) // 2
                    amount = _q2(Decimal(middle) * lot * price)
                    if amount + trade_fees(amount, False, stock)["total_fees_cny"] <= cash_available:
                        low = middle
                    else:
                        high = middle - 1
                affordable = Decimal(low) * lot
                if affordable < shares:
                    execution_issues.append(f"{action.asset_id}: 已按可用资金及费用缩减买入数量")
                shares = affordable
            amount = _q2(shares * price)
            fees = trade_fees(amount, selling, stock)
            delta = -amount if selling else amount
            cash_available += (amount if selling else -amount) - fees["total_fees_cny"]
            adjusted[action.asset_id] = action.model_copy(update={
                "shares": shares, "current_price_cny": price, "cash_delta_cny": delta,
                "delta_weight_pct": _q2(delta / total_val * 100),
                "action_type": action.action_type if shares else RebalancingActionType.HOLD,
                "target_value_cny": action.current_value_cny + delta, "rationale": rationale, **fees})
        actions = [adjusted[a.asset_id] for a in actions]

        # Calculate metrics from executable amounts, excluding HOLD deadband drift.
        total_buy = sum((abs(a.cash_delta_cny) for a in actions if a.action_type == RebalancingActionType.BUY), start=Decimal("0"))
        total_sell = sum((abs(a.cash_delta_cny) for a in actions if a.action_type in (RebalancingActionType.SELL, RebalancingActionType.REDUCE)), start=Decimal("0"))
        turnover_pct = _q2((total_buy + total_sell) / total_val * 50)
        total_fees = sum((a.total_fees_cny for a in actions), Decimal(0))
        net_cash = _q2(total_sell - total_buy - total_fees)
        initial_cash = sum((p.market_value for p in positions if p.asset_type == AssetType.CASH), Decimal(0))
        turnover_breached = turnover_pct > request.max_turnover_pct

        metrics = RebalancingMetrics(
            total_portfolio_value_cny=_q2(total_val),
            total_turnover_pct=turnover_pct,
            total_buy_cny=_q2(total_buy),
            total_sell_cny=_q2(total_sell),
            net_cash_flow_cny=net_cash,
            turnover_cap_breached=turnover_breached,
            net_turnover_cost=total_fees,
            net_turnover_cost_pct=_q2(total_fees / (total_buy + total_sell) * 100) if total_buy + total_sell else Decimal("0.00"),
            cash_after_cny=_q2(initial_cash + net_cash),
            cash_shortfall_cny=max(Decimal("0.00"), -initial_cash - net_cash),
        )

        # Build execution steps: Sell/Reduce first, then Buy
        sells = [a for a in actions if a.executable and a.action_type in (RebalancingActionType.SELL, RebalancingActionType.REDUCE)]
        buys = [a for a in actions if a.executable and a.action_type == RebalancingActionType.BUY]
        sells.sort(key=lambda x: abs(x.cash_delta_cny), reverse=True)
        buys.sort(key=lambda x: abs(x.cash_delta_cny), reverse=True)

        steps: list[RebalancingStep] = []
        step_idx = 1
        for s in sells:
            steps.append(
                RebalancingStep(
                    step_number=step_idx,
                    action_type=s.action_type,
                    asset_id=s.asset_id,
                    asset_name=s.asset_name,
                    amount_cny=abs(s.cash_delta_cny),
                    liquidity_priority=1,
                    shares=s.shares, total_fees_cny=s.total_fees_cny,
                    description=f"优先卖出/减持 {s.asset_name} 释放现金 {abs(s.cash_delta_cny)} CNY",
                )
            )
            step_idx += 1

        for b in buys:
            steps.append(
                RebalancingStep(
                    step_number=step_idx,
                    action_type=b.action_type,
                    asset_id=b.asset_id,
                    asset_name=b.asset_name,
                    amount_cny=abs(b.cash_delta_cny),
                    liquidity_priority=2,
                    shares=b.shares, total_fees_cny=b.total_fees_cny,
                    description=f"使用释放流动性买入/增持 {b.asset_name} 金额 {abs(b.cash_delta_cny)} CNY",
                )
            )
            step_idx += 1

        issues: list[str] = execution_issues
        cash_target = sum((request.target_weights.get(p.asset_id, Decimal(0))
                           for p in positions if p.asset_type == AssetType.CASH), Decimal(0))
        if cash_target < request.minimum_cash_pct:
            issues.append(f"目标现金比例 {cash_target}% 低于体检最低要求 {request.minimum_cash_pct}%；当前目标结构未满足现金约束")
        cash_after_pct = metrics.cash_after_cny / (total_val - total_fees) * 100 if total_val > total_fees else Decimal(0)
        if cash_after_pct < request.minimum_cash_pct:
            issues.append(f"按当前步骤执行并扣费后现金比例 {_q2(cash_after_pct)}% 仍低于最低要求 {request.minimum_cash_pct}%，现金风险未解除")
        status = GateStatus.REVIEW_REQUIRED if issues else GateStatus.PASS
        if metrics.cash_shortfall_cny > 0:
            status = GateStatus.REVIEW_REQUIRED
            issues.append(f"扣费后现金缺口 {metrics.cash_shortfall_cny} CNY")

        if turnover_breached:
            status = GateStatus.REVIEW_REQUIRED
            issues.append(f"总换手率 {turnover_pct}% 超出设定上限 {request.max_turnover_pct}%")

        invalidation_conditions = (
            "组合内任意资产价格变动超过 5.00%",
            "宏观或行业风险预算上限调整",
            "用户风险画像发生变更",
        )

        return PortfolioRebalancingResponse(
            request_id=request.request_id,
            owner_id=request.owner_id,
            status=status,
            metrics=metrics,
            actions=tuple(actions),
            execution_steps=tuple(steps),
            issues=tuple(issues),
            invalidation_conditions=invalidation_conditions,
        )
