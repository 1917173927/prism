"""Server-side adapter for the Fuyao structured financial data API."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta, timezone
import math
import os
import re
from time import perf_counter
from typing import Any

import httpx

from app.providers.live_market import MarketDataProvider, market_prefix


SHANGHAI_TZ = timezone(timedelta(hours=8))
CAPABILITY_FAILURE_CODES = frozenset({
    "FUYAO_2001",
    "FUYAO_2003",
    "NOT_CONFIGURED",
    "UPSTREAM_TIMEOUT",
    "UPSTREAM_UNAVAILABLE",
})


class FuyaoProviderError(RuntimeError):
    """A safe, structured upstream failure that never contains credentials."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


def _datetime_from_millis(value: Any) -> datetime | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        return None
    try:
        return datetime.fromtimestamp(value / 1000, tz=UTC).astimezone(SHANGHAI_TZ)
    except (OverflowError, OSError, ValueError):
        return None


def _optional_finite_number(value: Any, field_name: str) -> int | float | None:
    if value is None:
        return None
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
    ):
        raise FuyaoProviderError(
            "INVALID_RESPONSE", f"扶摇数据字段 {field_name} 不是有效有限数值。"
        )
    return value


class FuyaoFinanceProvider(MarketDataProvider):
    """Fetch live A-share quotes and disclosed fund look-through data.

    Credentials remain server-side. The API uses HTTP 200 for business errors,
    so every response is validated through its ``code`` field.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float = 1.5,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key_override = api_key
        self._base_url = (
            base_url
            or os.getenv("HITHINK_FINANCE_BASE_URL", "https://fuyao.aicubes.cn")
        ).rstrip("/")
        self._timeout_seconds = min(max(timeout_seconds, 0.1), 2.0)
        self._transport = transport
        self.last_probe_errors: dict[str, str | None] = {}

    @property
    def api_key(self) -> str:
        if self._api_key_override is not None:
            return self._api_key_override.strip()
        return os.getenv("HITHINK_FINANCE_API_KEY", "").strip()

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    A_SHARE_PREFIXES = (
        "600", "601", "603", "605", "688", "689",
        "000", "001", "002", "003", "300", "301",
        "82", "83", "87", "88", "92",
    )
    EXCHANGE_FUND_PREFIXES = ("510", "512", "513", "515", "588", "159")

    @staticmethod
    def _normalize_thscode(code: str, allowed_prefixes: tuple[str, ...]) -> str:
        value = code.strip().upper()
        match = re.fullmatch(r"(?P<code>\d{6})(?:\.(?P<suffix>SH|SZ|BJ))?", value)
        if match is None:
            raise FuyaoProviderError(
                "INVALID_SYMBOL", "标的代码必须为 6 位数字，可附带 .SH、.SZ 或 .BJ。"
            )
        clean_code = match.group("code")
        if not clean_code.startswith(allowed_prefixes):
            raise FuyaoProviderError("UNSUPPORTED_ASSET_TYPE", "该接口不支持此类标的。")
        expected_suffix = market_prefix(clean_code).upper()
        supplied_suffix = match.group("suffix")
        if supplied_suffix is not None and supplied_suffix != expected_suffix:
            raise FuyaoProviderError("INVALID_SYMBOL", "证券代码与交易所后缀不一致。")
        return f"{clean_code}.{expected_suffix}"

    async def _get(
        self,
        client: httpx.AsyncClient,
        path: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            response = await client.get(path, params=params)
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise FuyaoProviderError("UPSTREAM_TIMEOUT", "扶摇数据接口响应超时。") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise FuyaoProviderError("UPSTREAM_UNAVAILABLE", "扶摇数据接口暂时不可用。") from exc

        if not isinstance(payload, dict):
            raise FuyaoProviderError("INVALID_RESPONSE", "扶摇数据接口返回了无效响应。")
        business_code = payload.get("code")
        if business_code != 0:
            if business_code == 2001:
                message = "扶摇数据凭据无效或已失效。"
            elif business_code == 2003:
                message = "当前扶摇数据凭据未开通此项能力。"
            else:
                message = "扶摇数据接口拒绝了本次请求。"
            raise FuyaoProviderError(f"FUYAO_{business_code}", message)
        data = payload.get("data")
        if not isinstance(data, dict):
            raise FuyaoProviderError("INVALID_RESPONSE", "扶摇数据接口缺少 data 字段。")
        return data

    def _client(self) -> httpx.AsyncClient:
        if not self.is_configured:
            raise FuyaoProviderError(
                "NOT_CONFIGURED", "服务端尚未配置 HITHINK_FINANCE_API_KEY。"
            )
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers={"X-api-key": self.api_key},
            timeout=self._timeout_seconds,
            transport=self._transport,
        )

    async def get_quote(self, code: str) -> dict[str, Any] | None:
        """Return one normalized A-share quote and its upstream observation time."""
        try:
            return await asyncio.wait_for(
                self._get_quote_impl(code), timeout=self._timeout_seconds
            )
        except TimeoutError as exc:
            raise FuyaoProviderError(
                "UPSTREAM_TIMEOUT", "扶摇数据接口响应超时。"
            ) from exc

    @staticmethod
    def _index_symbol(symbol: str) -> str:
        symbol = symbol.strip().upper()
        if not re.fullmatch(r"\d{6}\.(SH|SZ|TI)", symbol):
            raise FuyaoProviderError("UNSUPPORTED_INDEX", "当前接口仅支持 A 股及同花顺行业指数。")
        return symbol

    async def get_index_quote(self, symbol: str) -> dict[str, Any] | None:
        symbol = self._index_symbol(symbol)
        async with self._client() as client:
            data = await self._get(client, "/api/a-share-index/prices/snapshot", {"thscodes": symbol})
        row = next((row for row in data.get("item", []) if row.get("thscode") == symbol), None)
        if row is None:
            return None
        price = _optional_finite_number(row.get("last_price"), "last_price")
        change = _optional_finite_number(row.get("price_change_ratio_pct"), "price_change_ratio_pct")
        observed = _datetime_from_millis(data.get("timestamp"))
        if price is None or price <= 0 or change is None or observed is None:
            raise FuyaoProviderError("INVALID_RESPONSE", "指数快照缺少有效价格或观察时间。")
        return {"symbol": symbol, "price_cny": price, "change_pct": change,
                "observed_at": observed.isoformat(), "source": "同花顺金融数据 · 指数行情", "is_synthetic": False}

    async def get_index_history(self, symbol: str) -> list[dict[str, Any]]:
        symbol = self._index_symbol(symbol)
        end = datetime.now(UTC)
        async with self._client() as client:
            data = await self._get(client, "/api/a-share-index/prices/historical", {
                "thscode": symbol, "interval": "1d", "start": int((end - timedelta(days=90)).timestamp() * 1000), "end": int(end.timestamp() * 1000)})
        bars = []
        for row in data.get("item", []):
            observed = _datetime_from_millis(row.get("date_ms"))
            values = [_optional_finite_number(row.get(key), key) for key in ("open_price", "high_price", "low_price", "close_price")]
            if observed is None or any(v is None or v <= 0 for v in values):
                raise FuyaoProviderError("INVALID_RESPONSE", "指数日线缺少有效日期或 OHLC 数据。")
            opening, high, low, close = values
            if not low <= min(opening, close) <= max(opening, close) <= high:
                raise FuyaoProviderError("INVALID_RESPONSE", "指数日线高低价关系无效。")
            bars.append({"time": observed.date().isoformat(), "open": opening, "high": high, "low": low, "close": close})
        if len({bar["time"] for bar in bars}) != len(bars):
            raise FuyaoProviderError("INVALID_RESPONSE", "指数日线含重复日期。")
        return sorted(bars, key=lambda bar: bar["time"])

    async def get_industry_observations(self) -> list[dict[str, Any]]:
        """Bounded twelve-industry observation set; never claim a full-market ranking."""
        from decimal import Decimal
        async with self._client() as client:
            data = await self._get(client, "/api/a-share-index/catalog/ths-index-list", {"tag": "industry"})
        catalog = [row for row in data.get("item", []) if re.fullmatch(r"881\d{3}\.TI", row.get("thscode", ""))][:12]
        semaphore = asyncio.Semaphore(2)
        async def observe(row):
            async with semaphore:
                try:
                    bars = await self.get_index_history(row["thscode"])
                    def change(days):
                        return str(((Decimal(str(bars[-1]["close"])) / Decimal(str(bars[-days-1]["close"])) - 1) * 100).quantize(Decimal("0.01"))) if len(bars) > days else None
                    return {"name": row["name"], "symbol": row["thscode"], "as_of": bars[-1]["time"] if bars else None,
                            "day_pct": change(1), "five_day_pct": change(5), "twenty_day_pct": change(20), "status": "CALCULATED" if bars else "REVIEW_REQUIRED"}
                except FuyaoProviderError as exc:
                    return {"name": row["name"], "symbol": row["thscode"], "status": "REVIEW_REQUIRED", "error_code": exc.code}
        return await asyncio.gather(*(observe(row) for row in catalog))

    async def _get_quote_impl(self, code: str) -> dict[str, Any] | None:
        started = perf_counter()
        thscode = self._normalize_thscode(code, self.A_SHARE_PREFIXES)
        async with self._client() as client:
            quote_task = self._get(
                client, "/api/a-share/prices/snapshot", {"thscodes": thscode}
            )
            meta_task = self._get(
                client,
                "/api/meta/tickers/search",
                {"q": thscode, "asset_type": "a-share", "limit": 1},
            )
            quote_result, meta_result = await asyncio.gather(
                quote_task, meta_task, return_exceptions=True
            )

        if isinstance(quote_result, BaseException):
            raise quote_result
        items = quote_result.get("item")
        if not isinstance(items, list) or not items or not isinstance(items[0], dict):
            return None
        item = items[0]
        if item.get("thscode") != thscode or item.get("ticker") != thscode[:6]:
            raise FuyaoProviderError("SYMBOL_MISMATCH", "扶摇行情返回了不匹配的标的。")
        last_price = item.get("last_price")
        if (
            not isinstance(last_price, (int, float))
            or isinstance(last_price, bool)
            or not math.isfinite(float(last_price))
            or last_price <= 0
        ):
            raise FuyaoProviderError("INVALID_RESPONSE", "扶摇行情缺少有效最新成交价。")

        name = None
        metadata_missing = isinstance(meta_result, BaseException)
        if not metadata_missing:
            meta_items = meta_result.get("item")
            if isinstance(meta_items, list):
                exact = next(
                    (
                        row
                        for row in meta_items
                        if isinstance(row, dict) and row.get("thscode") == thscode
                    ),
                    None,
                )
                if exact:
                    name = exact.get("name")

        observed = _datetime_from_millis(quote_result.get("timestamp"))
        if observed is None:
            raise FuyaoProviderError("MISSING_TIMESTAMP", "扶摇行情缺少可核验的数据时间。")
        retrieved = datetime.now(UTC)
        return {
            "symbol": thscode,
            "name": name or thscode,
            "price_cny": float(last_price),
            "change_pct": _optional_finite_number(item.get("price_change_ratio_pct"), "price_change_ratio_pct"),
            "price_change_cny": _optional_finite_number(item.get("price_change"), "price_change"),
            "open_price_cny": _optional_finite_number(item.get("open_price"), "open_price"),
            "high_price_cny": _optional_finite_number(item.get("high_price"), "high_price"),
            "low_price_cny": _optional_finite_number(item.get("low_price"), "low_price"),
            "previous_close_cny": _optional_finite_number(item.get("prev_price"), "prev_price"),
            "volume_shares": _optional_finite_number(item.get("volume"), "volume"),
            "turnover_cny": _optional_finite_number(item.get("turnover"), "turnover"),
            "provider_tier": "LIVE_PRIMARY",
            "quote_latency_ms": round((perf_counter() - started) * 1000, 2),
            "staleness_seconds": (
                round(max(0.0, (retrieved - observed).total_seconds()), 2)
                if observed else None
            ),
            "observed_at": observed.isoformat(),
            "retrieved_at": retrieved.isoformat(),
            "is_synthetic": False,
            "missing_fields": ["name"] if not name else [],
            "fallback_reasons": [],
            "source": "Fuyao structured financial data API",
        }

    async def get_fund_lookthrough(self, code: str) -> dict[str, Any] | None:
        """Return the latest disclosed fund holdings, never labelled as real-time."""
        try:
            return await asyncio.wait_for(
                self._get_fund_lookthrough_impl(code), timeout=self._timeout_seconds
            )
        except TimeoutError as exc:
            raise FuyaoProviderError(
                "UPSTREAM_TIMEOUT", "扶摇数据接口响应超时。"
            ) from exc

    async def _get_fund_lookthrough_impl(self, code: str) -> dict[str, Any] | None:
        started = perf_counter()
        thscode = self._normalize_thscode(code, self.EXCHANGE_FUND_PREFIXES)
        fund_type = "exchange"
        async with self._client() as client:
            profile_result, holdings_result = await asyncio.gather(
                self._get(
                    client,
                    "/api/fund/profile/detail",
                    {"fund_type": fund_type, "thscode": thscode},
                ),
                self._get(
                    client,
                    "/api/fund/portfolio/holdings",
                    {"fund_type": fund_type, "thscode": thscode},
                ),
            )
        holding_items = holdings_result.get("item")
        if not isinstance(holding_items, list) or not holding_items:
            return None
        report_dates = [
            date
            for row in holding_items
            if isinstance(row, dict)
            if (date := _datetime_from_millis(row.get("end_date_ms"))) is not None
        ]
        if not report_dates:
            raise FuyaoProviderError("INVALID_RESPONSE", "扶摇基金持仓缺少披露日期。")
        report_date = max(report_dates)
        profile_items = profile_result.get("item")
        profile = profile_items[0] if isinstance(profile_items, list) and profile_items else None
        if not isinstance(profile, dict):
            raise FuyaoProviderError("INVALID_RESPONSE", "扶摇基金档案缺少可核验的标的代码。")
        if profile.get("thscode") != thscode:
            raise FuyaoProviderError("SYMBOL_MISMATCH", "扶摇基金档案返回了不匹配的标的。")
        top_holdings = [
            {
                "asset_id": row.get("thscode"),
                "name": row.get("stock_name"),
                "weight_pct": _optional_finite_number(row.get("hold_ratio"), "hold_ratio"),
                "market_value_cny": _optional_finite_number(row.get("position_capital"), "position_capital"),
                "rank": _optional_finite_number(row.get("investment_rank"), "investment_rank"),
                "asset_type": row.get("asset_type"),
            }
            for row in holding_items
            if isinstance(row, dict)
            and _datetime_from_millis(row.get("end_date_ms")) == report_date
        ]
        retrieved = datetime.now(UTC)
        return {
            "fund_code": thscode,
            "fund_name": profile.get("fund_name") or thscode,
            "fund_type": "ETF / 交易所基金",
            "net_asset_value_cny": _optional_finite_number(profile.get("unit_nav"), "unit_nav"),
            "top_holdings": top_holdings,
            "sector_exposure": {},
            "main_industry": holdings_result.get("main_industry"),
            "disclosed_stock_ratio_pct": _optional_finite_number(
                holdings_result.get("stock_ratio_pct"), "stock_ratio_pct"
            ),
            "holding_disclosure_as_of": report_date.isoformat(),
            "observed_at": report_date.isoformat(),
            "retrieved_at": retrieved.isoformat(),
            "staleness_seconds": round(
                max(0.0, (retrieved - report_date).total_seconds()), 2
            ),
            "quote_latency_ms": round((perf_counter() - started) * 1000, 2),
            "provider_tier": "LIVE_PRIMARY",
            "is_synthetic": False,
            "missing_fields": ["sector_exposure"],
            "fallback_reasons": [],
            "source": "Fuyao fund periodic disclosure API",
            "data_freshness_label": "PERIODIC_DISCLOSURE",
        }

    async def probe_capabilities(self) -> dict[str, bool]:
        """Verify the capabilities granted to the configured key with real calls."""
        capabilities = {"stock_quote": False, "fund_lookthrough": False}
        if not self.is_configured:
            return capabilities
        quote_result, fund_result = await asyncio.gather(
            self.get_quote("600519"),
            self.get_fund_lookthrough("510300"),
            return_exceptions=True,
        )
        for name, result in zip(capabilities, (quote_result, fund_result)):
            capabilities[name] = not isinstance(result, BaseException) and result is not None
            self.last_probe_errors[name] = (
                result.code if isinstance(result, FuyaoProviderError)
                else "PROBE_FAILED" if isinstance(result, BaseException)
                else "NO_DATA" if result is None else None
            )
        return capabilities


__all__ = ["CAPABILITY_FAILURE_CODES", "FuyaoFinanceProvider", "FuyaoProviderError"]
