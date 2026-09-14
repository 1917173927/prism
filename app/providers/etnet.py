"""Public ET Net chart-data adapter used as a Hong Kong fallback.

ET Net's interactive index page embeds daily OHLCV rows in a JavaScript
variable.  This is a public web page, not a supported developer API; callers
must expect delayed data, rate limits and upstream HTML changes.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
import re
from typing import Any

import httpx


class EtNetError(RuntimeError):
    """Safe, user-facing error raised when ET Net data cannot be parsed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


class EtNetProvider:
    """Read daily Hong Kong index data from ET Net's public chart page."""

    base_url = "https://www.etnet.com.hk"
    _chart_pattern = re.compile(r"var\s+testData_1_Daily\s*=\s*(\{.*?\});", re.S)
    # Hong Kong has no daylight-saving transition; a fixed UTC+8 offset keeps
    # the adapter dependency-free on Windows environments without tzdata.
    _market_timezone = timezone(timedelta(hours=8))
    _symbols = {
        "^HSI": "HSI",
        "^HSCE": "CEI",
        "HSTECH.HK": "TEH",
        "HSC": "HSC",
    }

    def __init__(
        self,
        *,
        base_url: str = base_url,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.transport = transport

    @property
    def is_configured(self) -> bool:
        # Public page access needs no account or API key. Availability is not
        # a contract because the provider is an HTML page rather than an API.
        return True

    @classmethod
    def supports_symbol(cls, symbol: str) -> bool:
        return symbol.upper() in cls._symbols

    @staticmethod
    def _decimal(value: Any, field: str) -> Decimal | None:
        if value is None or value == "":
            return None
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise EtNetError("INVALID_RESPONSE", f"ET Net {field} 字段无效。") from exc
        return parsed if parsed.is_finite() else None

    async def _html(self, symbol: str) -> str:
        subtype = self._symbols.get(symbol.upper())
        if not subtype:
            raise EtNetError("SYMBOL_UNSUPPORTED", "ET Net 未登记该港股指数代码。")
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=8.0,
                transport=self.transport,
                headers={"User-Agent": "Mozilla/5.0 Prism prototype"},
            ) as client:
                response = await client.get(
                    "/www/eng/stocks/indexes_chart_interactive.php",
                    params={"subtype": subtype},
                )
                response.raise_for_status()
                return response.text
        except (httpx.HTTPError, UnicodeError) as exc:
            raise EtNetError("UPSTREAM_UNAVAILABLE", "ET Net 港股指数页面暂时不可用。") from exc

    @classmethod
    def _bars(cls, html: str, symbol: str) -> list[dict[str, Any]]:
        match = cls._chart_pattern.search(html)
        if not match:
            raise EtNetError("INVALID_RESPONSE", "ET Net 页面未返回可解析的指数 K 线。")
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            raise EtNetError("INVALID_RESPONSE", "ET Net 指数 K 线结构无效。") from exc
        if not isinstance(payload, dict):
            raise EtNetError("INVALID_RESPONSE", "ET Net 指数 K 线结构无效。")
        subtype = cls._symbols.get(symbol.upper())
        if str(payload.get("code", "")).upper() != subtype:
            raise EtNetError("IDENTITY_MISMATCH", "ET Net 返回的标的身份与请求不一致。")
        rows = payload.get("result")
        if not isinstance(rows, list):
            return []
        bars: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, list) or len(row) < 6:
                continue
            timestamp = row[0]
            if not isinstance(timestamp, (int, float)) or timestamp <= 0:
                continue
            try:
                observed = datetime.fromtimestamp(timestamp / 1000, UTC).astimezone(cls._market_timezone).date().isoformat()
            except (OverflowError, OSError, ValueError):
                continue
            opening = cls._decimal(row[1], "open")
            high = cls._decimal(row[2], "high")
            low = cls._decimal(row[3], "low")
            close = cls._decimal(row[4], "close")
            volume = cls._decimal(row[5], "volume")
            if any(value is None or value <= 0 for value in (opening, high, low, close)):
                continue
            if not low <= min(opening, close) <= max(opening, close) <= high:
                raise EtNetError("INVALID_RESPONSE", "ET Net 指数 K 线高低价关系无效。")
            if volume is not None and volume < 0:
                raise EtNetError("INVALID_RESPONSE", "ET Net 指数成交量字段无效。")
            bars.append({
                "time": observed,
                "open": opening,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
                "turnover": None,
            })
        return sorted(bars, key=lambda item: item["time"])

    async def get_index_history(self, symbol: str, start: date, end: date) -> list[dict[str, Any]]:
        bars = self._bars(await self._html(symbol), symbol)
        return [bar for bar in bars if start.isoformat() <= bar["time"] <= end.isoformat()]

    async def get_index_quote(self, symbol: str) -> dict[str, Any] | None:
        end = datetime.now(UTC).date()
        bars = await self.get_index_history(symbol, end - timedelta(days=14), end)
        if not bars:
            return None
        latest = bars[-1]
        previous = bars[-2]["close"] if len(bars) > 1 else latest["open"]
        change = latest["close"] - previous
        change_pct = change / previous * Decimal(100) if previous else Decimal(0)
        observed_at = datetime.fromisoformat(f"{latest['time']}T00:00:00+08:00").astimezone(UTC).isoformat()
        return {
            "symbol": symbol,
            "price": latest["close"],
            "price_cny": latest["close"],
            "change": change,
            "change_pct": change_pct,
            "observed_at": observed_at,
            "source": "ET Net公开图表接口（非正式原型数据）",
            "is_synthetic": False,
        }


__all__ = ["EtNetError", "EtNetProvider"]
