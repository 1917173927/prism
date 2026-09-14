"""Deterministic display metrics; missing costs/previous closes stay unavailable."""
from decimal import Decimal, ROUND_HALF_UP


def portfolio_summary(data: dict | None) -> dict:
    rows = (data or {}).get("positions", [])
    cash = Decimal(str((data or {}).get("cash_cny", 0)))
    value = Decimal(0)
    cost = Decimal(0)
    daily = Decimal(0)
    costs_complete = bool(rows)
    daily_complete = bool(rows)
    positions = []
    for raw in rows:
        qty = Decimal(str(raw["quantity"]))
        price = Decimal(str(raw["price"]))
        market_value = qty * price
        value += market_value
        cost_price = raw.get("cost_price")
        previous = raw.get("previous_close")
        pnl = None
        if cost_price is None or Decimal(str(cost_price)) <= 0:
            costs_complete = False
        else:
            cost += qty * Decimal(str(cost_price))
            pnl = market_value - qty * Decimal(str(cost_price))
        if previous is None or Decimal(str(previous)) <= 0:
            daily_complete = False
        else:
            daily += qty * (price - Decimal(str(previous)))
        positions.append({**raw, "market_value_cny": money(market_value), "pnl_cny": money(pnl)})
    for row in positions:
        row["weight_pct"] = money(Decimal(row["market_value_cny"]) / value * 100) if value else "0.00"
    allocation = [{"label": row.get("name") or row.get("asset_id", "资产"),
                   "weight": money(Decimal(row["market_value_cny"]) / (value + cash) * 100)}
                  for row in positions] if value + cash else []
    if cash > 0:
        allocation.append({"label": "现金", "weight": money(cash / (value + cash) * 100)})
    return {"positions": positions, "holdings_value_cny": money(value), "cash_cny": money(cash),
            "allocation": allocation,
            "total_value_cny": money(value + cash), "position_count": len(rows),
            "pnl_cny": money(value - cost) if costs_complete else None,
            "pnl_pct": money((value / cost - 1) * 100) if costs_complete and cost else None,
            "daily_pnl_cny": money(daily) if daily_complete else None}


def money(value: Decimal | None) -> str | None:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) if value is not None else None
