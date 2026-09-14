"""Unofficial Yahoo Finance Chart adapter for prototype market analysis.

This adapter intentionally has no account or API-key dependency. Yahoo's chart
endpoint is not a formal public developer API; callers must treat data as
delayed/last-close prototype data and handle rate limits or upstream changes.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import os
from typing import Any

import httpx


class YahooFinanceError(RuntimeError):
    """Safe, user-facing error raised when Yahoo cannot serve a request."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


class YahooFinanceProvider:
    """Read daily Yahoo Chart data without user login or an API key."""

    def __init__(
        self,
        *,
        base_url: str = "https://query1.finance.yahoo.com",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.transport = transport

    @property
    def is_configured(self) -> bool:
        # The unofficial endpoint is public, although availability is not a
        # contract and can be affected by rate limits or upstream changes.
        return True

    @staticmethod
    def _decimal(value: Any, field: str) -> Decimal | None:
        if value is None or value == "":
            return None
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise YahooFinanceError("INVALID_RESPONSE", f"Yahoo Finance {field} 字段无效。") from exc
        return parsed if parsed.is_finite() else None

    async def _chart(self, symbol: str, start: date, end: date) -> dict[str, Any]:
        period1 = int(datetime(start.year, start.month, start.day, tzinfo=UTC).timestamp())
        period2 = int(datetime(end.year, end.month, end.day, tzinfo=UTC).timestamp()) + 86400
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=8.0,
                transport=self.transport,
                headers={"User-Agent": "Mozilla/5.0 Prism prototype"},
            ) as client:
                response = await client.get(
                    f"/v8/finance/chart/{symbol}",
                    params={
                        "period1": period1,
                        "period2": period2,
                        "interval": "1d",
                        "events": "history",
                        "includeAdjustedClose": "true",
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise YahooFinanceError("UPSTREAM_UNAVAILABLE", "Yahoo Finance 行情接口暂时不可用。") from exc
        if not isinstance(payload, dict):
            raise YahooFinanceError("INVALID_RESPONSE", "Yahoo Finance 返回了无效响应。")
        chart = payload.get("chart")
        if not isinstance(chart, dict):
            raise YahooFinanceError("INVALID_RESPONSE", "Yahoo Finance 返回缺少 chart 数据。")
        if chart.get("error"):
            error = chart["error"]
            description = error.get("description") if isinstance(error, dict) else None
            raise YahooFinanceError("UPSTREAM_REJECTED", str(description or "Yahoo Finance 拒绝了本次数据请求。"))
        results = chart.get("result")
        if not isinstance(results, list) or not results or not isinstance(results[0], dict):
            return {"result": None}
        return {"result": results[0]}

    @staticmethod
    def _bars(payload: dict[str, Any], symbol: str) -> list[dict[str, Any]]:
        result = payload.get("result")
        if not isinstance(result, dict):
            return []
        meta = result.get("meta")
        if isinstance(meta, dict):
            returned_symbol = str(meta.get("symbol", "")).strip()
            if returned_symbol and returned_symbol.upper() != symbol.upper():
                raise YahooFinanceError("IDENTITY_MISMATCH", "Yahoo Finance 返回的标的身份与请求不一致。")
        timestamps = result.get("timestamp")
        quote = ((result.get("indicators") or {}).get("quote") or [None])[0]
        if not isinstance(timestamps, list) or not isinstance(quote, dict):
            return []

        def value_at(field: str, index: int) -> Any:
            values = quote.get(field)
            if not isinstance(values, list) or index >= len(values):
                return None
            return values[index]

        bars: list[dict[str, Any]] = []
        for index, timestamp in enumerate(timestamps):
            if not isinstance(timestamp, (int, float)):
                continue
            try:
                observed = datetime.fromtimestamp(timestamp, UTC).date().isoformat()
            except (OverflowError, OSError, ValueError):
                continue
            opening = YahooFinanceProvider._decimal(value_at("open", index), "open")
            high = YahooFinanceProvider._decimal(value_at("high", index), "high")
            low = YahooFinanceProvider._decimal(value_at("low", index), "low")
            close = YahooFinanceProvider._decimal(value_at("close", index), "close")
            if any(value is None or value <= 0 for value in (opening, high, low, close)):
                continue
            if not low <= min(opening, close) <= max(opening, close) <= high:
                raise YahooFinanceError("INVALID_RESPONSE", "Yahoo Finance K 线高低价关系无效。")
            raw_volume = value_at("volume", index)
            volume = YahooFinanceProvider._decimal(raw_volume, "volume")
            if volume is not None and volume < 0:
                raise YahooFinanceError("INVALID_RESPONSE", "Yahoo Finance 成交量字段无效。")
            bars.append({
                "time": observed,
                "open": opening,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
                "turnover": None,
            })
        return sorted(bars, key=lambda row: row["time"])

    async def get_index_history(self, symbol: str, start: date, end: date) -> list[dict[str, Any]]:
        return self._bars(await self._chart(symbol, start, end), symbol)

    async def get_index_quote(self, symbol: str) -> dict[str, Any] | None:
        end = datetime.now(UTC).date()
        bars = await self.get_index_history(symbol, end - timedelta(days=14), end)
        if not bars:
            return None
        latest = bars[-1]
        previous = bars[-2]["close"] if len(bars) > 1 else latest["open"]
        change = latest["close"] - previous
        change_pct = change / previous * Decimal(100) if previous else Decimal(0)
        observed_at = datetime.fromisoformat(f"{latest['time']}T00:00:00+00:00").isoformat()
        return {
            "symbol": symbol,
            "price": latest["close"],
            "price_cny": latest["close"],
            "change": change,
            "change_pct": change_pct,
            "observed_at": observed_at,
            "source": "Yahoo Finance非正式接口（原型数据）",
            "is_synthetic": False,
        }

    async def get_factor_history(self, factor_id: str, start: date, end: date) -> list[dict[str, Any]]:
        symbols = {
            "us10y": os.getenv("YAHOO_US10Y_SYMBOL", "^TNX").strip(),
            "brent": os.getenv("YAHOO_BRENT_SYMBOL", "BZ=F").strip(),
            "comex-gold": os.getenv("YAHOO_GOLD_SYMBOL", "GC=F").strip(),
        }
        symbol = symbols.get(factor_id, "")
        if not symbol:
            raise YahooFinanceError("FACTOR_NOT_CONFIGURED", "Yahoo Finance 宏观因子代码尚未配置。")
        rows = self._bars(await self._chart(symbol, start, end), symbol)
        output: list[dict[str, Any]] = []
        for row in rows:
            value = row["close"]
            # Yahoo's ^TNX quote is conventionally yield * 10 (e.g. 43.5 =
            # 4.35%). Convert it to percentage points before correlation.
            if factor_id == "us10y":
                value = value / Decimal(10)
            if value > 0:
                output.append({"time": row["time"], "value": value})
        return output


__all__ = ["YahooFinanceError", "YahooFinanceProvider"]
