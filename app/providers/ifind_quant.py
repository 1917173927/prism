"""Server-only iFinD QuantAPI adapter for overseas indices and macro factors."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import os
from typing import Any

import httpx


class IFindQuantError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


class IFindQuantProvider:
    def __init__(self, refresh_token: str | None = None, *, base_url: str = "https://quantapi.51ifind.com",
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._refresh_token = refresh_token
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        self._access_token: str | None = None
        self._token_expires_at = datetime.min.replace(tzinfo=UTC)

    @property
    def refresh_token(self) -> str:
        return (self._refresh_token if self._refresh_token is not None else os.getenv("IFIND_QUANT_REFRESH_TOKEN", "")).strip()

    @property
    def is_configured(self) -> bool:
        return bool(self.refresh_token)

    async def _token(self, client: httpx.AsyncClient) -> str:
        now = datetime.now(UTC)
        if self._access_token and now < self._token_expires_at:
            return self._access_token
        if not self.refresh_token:
            raise IFindQuantError("NOT_CONFIGURED", "服务端尚未配置iFinD QuantAPI凭据。")
        try:
            response = await client.post("/api/v1/get_access_token", headers={"refresh_token": self.refresh_token})
            response.raise_for_status()
            payload = response.json()
            token = payload.get("data", {}).get("access_token")
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            raise IFindQuantError("TOKEN_UNAVAILABLE", "iFinD访问令牌获取失败。") from exc
        if not isinstance(token, str) or not token.strip():
            raise IFindQuantError("TOKEN_INVALID", "iFinD未返回有效访问令牌。")
        self._access_token = token.strip()
        self._token_expires_at = now + timedelta(minutes=30)
        return self._access_token

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=2.0, transport=self.transport) as client:
            token = await self._token(client)
            try:
                response = await client.post(path, json=body, headers={"access_token": token})
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise IFindQuantError("UPSTREAM_UNAVAILABLE", "iFinD行情接口暂时不可用。") from exc
        error_code = payload.get("errorcode", payload.get("error_code", 0))
        if error_code not in (0, "0", None):
            raise IFindQuantError("UPSTREAM_REJECTED", "iFinD拒绝了本次数据请求。")
        return payload

    @staticmethod
    def _rows(payload: dict[str, Any], symbol: str, fields: tuple[str, ...]) -> list[dict[str, Any]]:
        tables = payload.get("tables") or payload.get("data", {}).get("tables") or []
        if not isinstance(tables, list) or not tables:
            return []
        table = next((item for item in tables if item.get("thscode", item.get("code", symbol)) == symbol), None)
        if not isinstance(table, dict):
            raise IFindQuantError("IDENTITY_MISMATCH", "iFinD返回的标的身份与请求不一致。")
        times = table.get("time") or table.get("times") or []
        values = table.get("table") or table.get("data") or {}
        if isinstance(values, list):
            return [row for row in values if isinstance(row, dict)]
        if not isinstance(values, dict) or not isinstance(times, list):
            raise IFindQuantError("INVALID_RESPONSE", "iFinD时间序列结构无效。")
        rows = []
        for index, observed in enumerate(times):
            row = {"time": str(observed)[:10]}
            for field in fields:
                column = values.get(field, [])
                if field == "value" and not isinstance(column, list):
                    column = []
                if field == "value" and not column:
                    column = next((candidate for candidate in values.values() if isinstance(candidate, list)), [])
                row[field] = column[index] if isinstance(column, list) and index < len(column) else None
            rows.append(row)
        return rows

    async def get_index_history(self, symbol: str, start: date, end: date) -> list[dict[str, Any]]:
        fields = ("open", "high", "low", "close", "volume", "amount")
        payload = await self._post("/api/v1/cmd_history_quotation", {
            "codes": symbol, "indicators": ",".join(fields),
            "startdate": start.isoformat(), "enddate": end.isoformat(), "functionpara": {"Fill": "Blank"},
        })
        rows = self._rows(payload, symbol, fields)
        bars = []
        for row in rows:
            try:
                opening, high, low, close = (Decimal(str(row[field])) for field in fields[:4])
            except (InvalidOperation, KeyError, TypeError, ValueError) as exc:
                raise IFindQuantError("INVALID_RESPONSE", "iFinD指数K线缺少OHLC字段。") from exc
            if any(not value.is_finite() or value <= 0 for value in (opening, high, low, close)):
                raise IFindQuantError("INVALID_RESPONSE", "iFinD指数K线包含无效价格。")
            if not low <= min(opening, close) <= max(opening, close) <= high:
                raise IFindQuantError("INVALID_RESPONSE", "iFinD指数K线高低价关系无效。")
            try:
                volume = Decimal(str(row["volume"])) if row.get("volume") is not None else None
                amount = Decimal(str(row["amount"])) if row.get("amount") is not None else None
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise IFindQuantError("INVALID_RESPONSE", "iFinD指数成交量字段无效。") from exc
            if any(value is not None and (not value.is_finite() or value < 0) for value in (volume, amount)):
                raise IFindQuantError("INVALID_RESPONSE", "iFinD指数成交量字段包含无效数值。")
            bars.append({"time": row["time"], "open": opening, "high": high, "low": low, "close": close,
                         "volume": volume, "turnover": amount})
        return sorted(bars, key=lambda row: row["time"])

    async def get_index_quote(self, symbol: str) -> dict[str, Any] | None:
        end = datetime.now(UTC).date()
        bars = await self.get_index_history(symbol, end - timedelta(days=10), end)
        if not bars:
            return None
        latest = bars[-1]
        previous = bars[-2]["close"] if len(bars) > 1 else latest["open"]
        change = latest["close"] - previous
        change_pct = change / previous * Decimal(100) if previous else Decimal(0)
        return {"symbol": symbol, "price_cny": latest["close"], "change": change,
                "change_pct": change_pct, "observed_at": datetime.now(UTC).isoformat(),
                "source": "iFinD QuantAPI", "is_synthetic": False}

    async def get_factor_history(self, factor_id: str, start: date, end: date) -> list[dict[str, Any]]:
        if factor_id == "us10y":
            indicator = os.getenv("IFIND_US10Y_EDB_ID", "").strip()
            if not indicator:
                raise IFindQuantError("FACTOR_NOT_CONFIGURED", "美国10年期国债收益率指标尚未配置。")
            payload = await self._post("/api/v1/edb_service", {
                "indicators": indicator, "startdate": start.isoformat(), "enddate": end.isoformat(),
            })
            rows = self._rows(payload, indicator, ("value",))
        else:
            env_name = "IFIND_BRENT_CODE" if factor_id == "brent" else "IFIND_COMEX_GOLD_CODE"
            symbol = os.getenv(env_name, "").strip()
            if not symbol:
                raise IFindQuantError("FACTOR_NOT_CONFIGURED", "宏观商品代码尚未配置。")
            payload = await self._post("/api/v1/cmd_history_quotation", {
                "codes": symbol, "indicators": "close", "startdate": start.isoformat(),
                "enddate": end.isoformat(), "functionpara": {"Fill": "Blank"},
            })
            rows = self._rows(payload, symbol, ("close",))
            rows = [{"time": row["time"], "value": row.get("close")} for row in rows]
        output = []
        for row in rows:
            value = row.get("value")
            if value is None:
                continue
            try:
                parsed = Decimal(str(value))
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise IFindQuantError("INVALID_RESPONSE", "iFinD宏观因子数值无效。") from exc
            if parsed.is_finite() and parsed > 0:
                output.append({"time": str(row["time"])[:10], "value": parsed})
        return sorted(output, key=lambda row: row["time"])


__all__ = ["IFindQuantError", "IFindQuantProvider"]
