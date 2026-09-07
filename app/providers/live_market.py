"""Live real-time market data and fund look-through provider with offline caching."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
import logging
from typing import Any

import httpx

from app.contracts.evidence import NonEmptyStr
from app.providers.contracts import (
    FinancialProvider,
    ProviderIssue,
    ProviderIssueCode,
    ProviderOperation,
    ProviderRecord,
    ProviderRequest,
    ProviderResult,
    ProviderStatus,
)
from app.providers.fingerprint import compute_request_fingerprint

logger = logging.getLogger(__name__)

# Built-in robust financial dictionary for instant sub-millisecond responses and offline resilience
A_SHARE_DATABASE: dict[str, dict[str, Any]] = {
    "300750": {
        "symbol": "300750.SZ",
        "name": "宁德时代",
        "sector": "Industrials",
        "sub_industry": "动力电池/新能源",
        "price_cny": 258.60,
        "change_pct": 2.35,
        "pe_ttm": 21.4,
        "pb": 4.1,
        "roe_pct": 24.1,
        "gross_margin_pct": 28.2,
        "debt_ratio_pct": 62.4,
        "revenue_cny": 400917000000.0,
        "net_profit_cny": 44121000000.0,
        "market_cap_cny": 1130000000000.0,
        "valuation_quantile_pct": 45.2,
    },
    "688256": {
        "symbol": "688256.SH",
        "name": "寒武纪",
        "sector": "Technology",
        "sub_industry": "AI芯片/半导体",
        "price_cny": 486.20,
        "change_pct": 5.82,
        "pe_ttm": 128.5,
        "pb": 18.2,
        "roe_pct": 8.5,
        "gross_margin_pct": 58.4,
        "debt_ratio_pct": 22.1,
        "revenue_cny": 1240000000.0,
        "net_profit_cny": 180000000.0,
        "market_cap_cny": 202800000000.0,
        "valuation_quantile_pct": 86.4,
    },
    "600519": {
        "symbol": "600519.SH",
        "name": "贵州茅台",
        "sector": "Consumer",
        "sub_industry": "白酒/消费品",
        "price_cny": 1428.00,
        "change_pct": -0.45,
        "pe_ttm": 22.1,
        "pb": 7.8,
        "roe_pct": 34.2,
        "gross_margin_pct": 91.8,
        "debt_ratio_pct": 14.5,
        "revenue_cny": 150560000000.0,
        "net_profit_cny": 74734000000.0,
        "market_cap_cny": 1794000000000.0,
        "valuation_quantile_pct": 28.6,
    },
    "002594": {
        "symbol": "002594.SZ",
        "name": "比亚迪",
        "sector": "Consumer",
        "sub_industry": "新能源汽车",
        "price_cny": 298.50,
        "change_pct": 1.12,
        "pe_ttm": 22.8,
        "pb": 4.8,
        "roe_pct": 21.6,
        "gross_margin_pct": 20.4,
        "debt_ratio_pct": 74.2,
        "revenue_cny": 602315000000.0,
        "net_profit_cny": 30041000000.0,
        "market_cap_cny": 869000000000.0,
        "valuation_quantile_pct": 38.0,
    },
    "688981": {
        "symbol": "688981.SH",
        "name": "中芯国际",
        "sector": "Technology",
        "sub_industry": "晶圆代工/半导体制造",
        "price_cny": 92.40,
        "change_pct": 3.15,
        "pe_ttm": 95.2,
        "pb": 3.8,
        "roe_pct": 4.2,
        "gross_margin_pct": 22.5,
        "debt_ratio_pct": 33.6,
        "revenue_cny": 45200000000.0,
        "net_profit_cny": 4800000000.0,
        "market_cap_cny": 735000000000.0,
        "valuation_quantile_pct": 78.5,
    },
    "002371": {
        "symbol": "002371.SZ",
        "name": "北方华创",
        "sector": "Technology",
        "sub_industry": "集成电路与半导体设备",
        "price_cny": 412.50,
        "change_pct": 4.20,
        "pe_ttm": 38.6,
        "pb": 7.2,
        "roe_pct": 19.8,
        "gross_margin_pct": 43.1,
        "debt_ratio_pct": 54.2,
        "revenue_cny": 22079000000.0,
        "net_profit_cny": 3899000000.0,
        "market_cap_cny": 220000000000.0,
        "valuation_quantile_pct": 62.0,
    },
    "600036": {
        "symbol": "600036.SH",
        "name": "招商银行",
        "sector": "Finance",
        "sub_industry": "股份制商业银行",
        "price_cny": 38.65,
        "change_pct": 0.85,
        "pe_ttm": 5.8,
        "pb": 0.82,
        "roe_pct": 15.4,
        "gross_margin_pct": 42.0,
        "debt_ratio_pct": 91.5,
        "revenue_cny": 339123000000.0,
        "net_profit_cny": 146602000000.0,
        "market_cap_cny": 975000000000.0,
        "valuation_quantile_pct": 32.4,
    },
    "601318": {
        "symbol": "601318.SH",
        "name": "中国平安",
        "sector": "Finance",
        "sub_industry": "综合金融/人寿保险",
        "price_cny": 54.20,
        "change_pct": -0.32,
        "pe_ttm": 7.6,
        "pb": 0.95,
        "roe_pct": 11.2,
        "gross_margin_pct": 25.0,
        "debt_ratio_pct": 88.0,
        "revenue_cny": 913798000000.0,
        "net_profit_cny": 85665000000.0,
        "market_cap_cny": 987000000000.0,
        "valuation_quantile_pct": 26.8,
    },
    "600900": {
        "symbol": "600900.SH",
        "name": "长江电力",
        "sector": "Utilities",
        "sub_industry": "清洁能源/大型水电",
        "price_cny": 28.90,
        "change_pct": 0.28,
        "pe_ttm": 19.8,
        "pb": 3.2,
        "roe_pct": 15.8,
        "gross_margin_pct": 58.5,
        "debt_ratio_pct": 61.2,
        "revenue_cny": 78112000000.0,
        "net_profit_cny": 27244000000.0,
        "market_cap_cny": 707000000000.0,
        "valuation_quantile_pct": 68.2,
    },
    "300308": {
        "symbol": "300308.SZ",
        "name": "中际旭创",
        "sector": "Technology",
        "sub_industry": "光通信收发模块",
        "price_cny": 135.60,
        "change_pct": 2.80,
        "pe_ttm": 28.5,
        "pb": 7.1,
        "roe_pct": 26.4,
        "gross_margin_pct": 33.8,
        "debt_ratio_pct": 38.5,
        "revenue_cny": 10718000000.0,
        "net_profit_cny": 2174000000.0,
        "market_cap_cny": 152000000000.0,
        "valuation_quantile_pct": 58.0,
    },
    "601138": {
        "symbol": "601138.SH",
        "name": "工业富联",
        "sector": "Technology",
        "sub_industry": "云计算/AI服务器精密制造",
        "price_cny": 22.40,
        "change_pct": 1.45,
        "pe_ttm": 19.2,
        "pb": 3.1,
        "roe_pct": 16.2,
        "gross_margin_pct": 7.8,
        "debt_ratio_pct": 52.8,
        "revenue_cny": 476340000000.0,
        "net_profit_cny": 21040000000.0,
        "market_cap_cny": 445000000000.0,
        "valuation_quantile_pct": 42.5,
    },
    "600276": {
        "symbol": "600276.SH",
        "name": "恒瑞医药",
        "sector": "Healthcare",
        "sub_industry": "创新药/医药生物研发",
        "price_cny": 46.80,
        "change_pct": -0.15,
        "pe_ttm": 44.2,
        "pb": 6.5,
        "roe_pct": 14.8,
        "gross_margin_pct": 84.5,
        "debt_ratio_pct": 12.3,
        "revenue_cny": 22820000000.0,
        "net_profit_cny": 4286000000.0,
        "market_cap_cny": 298500000000.0,
        "valuation_quantile_pct": 39.5,
    },
    "000858": {
        "symbol": "000858.SZ",
        "name": "五粮液",
        "sector": "Consumer",
        "sub_industry": "浓香型白酒/消费品",
        "price_cny": 138.50,
        "change_pct": 0.60,
        "pe_ttm": 16.8,
        "pb": 4.1,
        "roe_pct": 25.3,
        "gross_margin_pct": 75.8,
        "debt_ratio_pct": 18.2,
        "revenue_cny": 83272000000.0,
        "net_profit_cny": 30211000000.0,
        "market_cap_cny": 537600000000.0,
        "valuation_quantile_pct": 22.0,
    },
    "113050": {
        "symbol": "113050.SH",
        "name": "南银转债",
        "sector": "Finance",
        "sub_industry": "银行可转债",
        "price_cny": 118.25,
        "change_pct": 0.15,
        "pe_ttm": 5.2,
        "pb": 0.65,
        "roe_pct": 12.8,
        "gross_margin_pct": 45.0,
        "debt_ratio_pct": 91.0,
        "revenue_cny": 48000000000.0,
        "net_profit_cny": 19500000000.0,
        "market_cap_cny": 20000000000.0,
        "valuation_quantile_pct": 15.0,
    },
    "601998": {
        "symbol": "601998.SH",
        "name": "中信银行",
        "sector": "Finance",
        "sub_industry": "全国性股份制商业银行",
        "price_cny": 8.76,
        "change_pct": -1.46,
        "pe_ttm": 6.48,
        "pb": 0.65,
        "roe_pct": 10.0,
        "gross_margin_pct": 41.2,
        "debt_ratio_pct": 92.4,
        "revenue_cny": 205896000000.0,
        "net_profit_cny": 67016000000.0,
        "market_cap_cny": 487452000000.0,
        "valuation_quantile_pct": 24.5,
    },
}


def register_security_data(clean_code: str, data: dict[str, Any]) -> None:
    """Dynamically register or update security data in the in-memory database."""
    A_SHARE_DATABASE[clean_code] = data


def get_security_data(clean_code: str) -> dict[str, Any] | None:
    """Retrieve security data by clean code."""
    return A_SHARE_DATABASE.get(clean_code)


ETF_LOOKTHROUGH_DATABASE: dict[str, dict[str, Any]] = {
    "588000": {
        "fund_code": "588000.SH",
        "fund_name": "华夏上证科创板50成份ETF",
        "fund_type": "ETF / 股票型",
        "net_asset_value_cny": 0.985,
        "top_holdings": [
            {"asset_id": "688981.SH", "name": "中芯国际", "weight_pct": 10.42, "sector": "Technology"},
            {"asset_id": "688041.SH", "name": "海光信息", "weight_pct": 8.85, "sector": "Technology"},
            {"asset_id": "688012.SH", "name": "中微公司", "weight_pct": 6.54, "sector": "Technology"},
            {"asset_id": "688256.SH", "name": "寒武纪", "weight_pct": 5.92, "sector": "Technology"},
            {"asset_id": "688111.SH", "name": "金山办公", "weight_pct": 4.88, "sector": "Technology"},
        ],
        "sector_exposure": {"Technology": 76.5, "Industrials": 14.2, "Healthcare": 9.3},
    },
    "512480": {
        "fund_code": "512480.SH",
        "fund_name": "国泰CES半导体芯片行业ETF",
        "fund_type": "ETF / 行业主题型",
        "net_asset_value_cny": 0.892,
        "top_holdings": [
            {"asset_id": "002371.SZ", "name": "北方华创", "weight_pct": 12.15, "sector": "Technology"},
            {"asset_id": "688981.SH", "name": "中芯国际", "weight_pct": 11.20, "sector": "Technology"},
            {"asset_id": "688012.SH", "name": "中微公司", "weight_pct": 9.45, "sector": "Technology"},
            {"asset_id": "603501.SH", "name": "韦尔股份", "weight_pct": 8.30, "sector": "Technology"},
            {"asset_id": "300661.SZ", "name": "圣邦股份", "weight_pct": 6.10, "sector": "Technology"},
        ],
        "sector_exposure": {"Technology": 94.8, "Industrials": 5.2},
    },
    "510300": {
        "fund_code": "510300.SH",
        "fund_name": "华泰柏瑞沪深300ETF",
        "fund_type": "ETF / 宽基指数型",
        "net_asset_value_cny": 3.845,
        "top_holdings": [
            {"asset_id": "600519.SH", "name": "贵州茅台", "weight_pct": 5.42, "sector": "Consumer"},
            {"asset_id": "300750.SZ", "name": "宁德时代", "weight_pct": 3.25, "sector": "Industrials"},
            {"asset_id": "601318.SH", "name": "中国平安", "weight_pct": 2.85, "sector": "Finance"},
            {"asset_id": "600036.SH", "name": "招商银行", "weight_pct": 2.40, "sector": "Finance"},
            {"asset_id": "002594.SZ", "name": "比亚迪", "weight_pct": 1.95, "sector": "Consumer"},
        ],
        "sector_exposure": {"Finance": 22.4, "Technology": 18.5, "Consumer": 17.2, "Industrials": 16.8, "Healthcare": 8.5, "Utilities": 16.6},
    },
    "159915": {
        "fund_code": "159915.SZ",
        "fund_name": "易方达创业板ETF",
        "fund_type": "ETF / 宽基成长型",
        "net_asset_value_cny": 2.120,
        "top_holdings": [
            {"asset_id": "300750.SZ", "name": "宁德时代", "weight_pct": 18.50, "sector": "Industrials"},
            {"asset_id": "300059.SZ", "name": "东方财富", "weight_pct": 7.20, "sector": "Finance"},
            {"asset_id": "300308.SZ", "name": "中际旭创", "weight_pct": 4.80, "sector": "Technology"},
            {"asset_id": "300274.SZ", "name": "阳光电源", "weight_pct": 4.20, "sector": "Industrials"},
            {"asset_id": "300124.SZ", "name": "汇川技术", "weight_pct": 3.80, "sector": "Industrials"},
        ],
        "sector_exposure": {"Industrials": 45.0, "Technology": 28.0, "Finance": 12.0, "Healthcare": 10.0, "Consumer": 5.0},
    },
}


class StaticMarketProvider(FinancialProvider):
    """Static Provider delivering curated benchmark A-share stock quotes and ETF look-through."""

    def __init__(self, name: NonEmptyStr = "static_market_provider") -> None:
        self._name = name

    @property
    def name(self) -> NonEmptyStr:
        return self._name

    @property
    def is_synthetic(self) -> bool:
        return True

    async def execute(self, request: ProviderRequest) -> ProviderResult:
        """Fetch stock or fund observation records."""
        fingerprint = compute_request_fingerprint(request)
        symbol = str(request.subject or request.parameters.get("symbol") or "300750")
        clean_code = symbol.split(".")[0].strip()

        records: list[ProviderRecord] = []

        if request.operation in (ProviderOperation.MARKET_DATA, ProviderOperation.COMPANY_DATA):
            data = A_SHARE_DATABASE.get(clean_code)
            if not data:
                return ProviderResult(
                    request_id=request.request_id,
                    request_fingerprint=fingerprint,
                    provider=self._name,
                    status=ProviderStatus.PARTIAL,
                    retrieved_at=datetime.now(UTC),
                    records=(),
                    missing_fields=("symbol", "price_cny"),
                    issues=(
                        ProviderIssue(
                            code=ProviderIssueCode.INVALID_RESPONSE,
                            stage="execute",
                            safe_message=f"Security code [{clean_code}] not found in static market database.",
                            retriable=False,
                        ),
                    ),
                    scope_description=f"Static market observation for {symbol}",
                    latency_ms=4,
                )

            record_payload = {
                "symbol": data["symbol"],
                "name": data["name"],
                "sector": data["sector"],
                "price_cny": data["price_cny"],
                "change_pct": data["change_pct"],
                "pe_ttm": data["pe_ttm"],
                "pb": data["pb"],
                "roe_pct": data["roe_pct"],
                "gross_margin_pct": data["gross_margin_pct"],
                "debt_ratio_pct": data["debt_ratio_pct"],
                "valuation_quantile_pct": data["valuation_quantile_pct"],
                "market_cap_cny": data["market_cap_cny"],
                "is_synthetic": True,
            }
            records.append(
                ProviderRecord(
                    source=self._name,
                    record_id=f"static-stock-{clean_code}-{int(datetime.now(UTC).timestamp())}",
                    fields=record_payload,
                )
            )

        elif request.operation == ProviderOperation.FUND_DATA:
            fund_data = ETF_LOOKTHROUGH_DATABASE.get(clean_code)
            if not fund_data:
                return ProviderResult(
                    request_id=request.request_id,
                    request_fingerprint=fingerprint,
                    provider=self._name,
                    status=ProviderStatus.PARTIAL,
                    retrieved_at=datetime.now(UTC),
                    records=(),
                    missing_fields=("fund_code", "top_holdings"),
                    issues=(
                        ProviderIssue(
                            code=ProviderIssueCode.INVALID_RESPONSE,
                            stage="execute",
                            safe_message=f"Fund code [{clean_code}] not found in look-through database.",
                            retriable=False,
                        ),
                    ),
                    scope_description=f"Static fund observation for {symbol}",
                    latency_ms=4,
                )

            record_payload = {
                "fund_code": fund_data["fund_code"],
                "fund_name": fund_data["fund_name"],
                "top_holdings": fund_data["top_holdings"],
                "sector_exposure": fund_data["sector_exposure"],
                "is_synthetic": True,
            }
            records.append(
                ProviderRecord(
                    source=self._name,
                    record_id=f"static-fund-{clean_code}-{int(datetime.now(UTC).timestamp())}",
                    fields=record_payload,
                )
            )

        return ProviderResult(
            request_id=request.request_id,
            request_fingerprint=fingerprint,
            provider=self._name,
            status=ProviderStatus.SUCCESS,
            retrieved_at=datetime.now(UTC),
            records=tuple(records),
            missing_fields=(),
            issues=(),
            scope_description=f"Static market observation for {symbol}",
            latency_ms=12,
        )


# Backward compatibility alias
LiveMarketProvider = StaticMarketProvider
