"""Deterministic, owner-scoped live stock analysis orchestration.

The service deliberately keeps financial calculations outside the LLM.  It
queries the configured Wencai provider in parallel, decodes only rows whose
security code exactly matches the request, and preserves section-level
failures instead of replacing them with fixtures.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import StrEnum
import re
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.portfolio import PortfolioImportBundle
from app.profile import RiskProfile
from app.providers import (
    ProviderOperation,
    ProviderRequest,
    ProviderResult,
    ProviderStatus,
)
from app.providers.wencai_normalization import select_wencai_item
from app.providers.live_market import market_prefix
from app.risk import build_risk_budget


_Q2 = Decimal("0.01")
_YEAR = re.compile(r"(?<!\d)(20\d{2})(?!\d)")
_DATE8 = re.compile(r"(?<!\d)(20\d{6})(?!\d)")


class AnalysisStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


class StockAnalysisIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    retriable: bool = False


class StockAnalysisSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1)
    operation: str = Field(min_length=1)
    retrieved_at: datetime
    serving_mode: str


class StockAnalysisSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AnalysisStatus
    data: dict[str, Any] = Field(default_factory=dict)
    missing_fields: tuple[str, ...] = ()
    issues: tuple[StockAnalysisIssue, ...] = ()
    observed_at: str | None = None
    sources: tuple[StockAnalysisSource, ...] = ()


class SecurityIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    name: str
    industry: str | list[str] | None = None


class LiveStockAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["copilot-stock-analysis.v1"] = "copilot-stock-analysis.v1"
    status: AnalysisStatus
    security: SecurityIdentity
    generated_at: datetime
    missing_fields: tuple[str, ...] = ()
    issues: tuple[StockAnalysisIssue, ...] = ()
    observations: dict[str, list[dict[str, str]]] = Field(default_factory=dict)
    sections: dict[str, StockAnalysisSection]


def _decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    cleaned = str(value).strip().replace(",", "").replace("，", "")
    if cleaned.endswith("%"):
        cleaned = cleaned[:-1].strip()
    try:
        parsed = Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _q2(value: Decimal | None) -> Decimal | None:
    return value.quantize(_Q2, rounding=ROUND_HALF_UP) if value is not None else None


def _normalized(value: object) -> str:
    return re.sub(r"[\s_\-()（）\[\]【】%:：/\\]+", "", str(value or "")).casefold()


def _matches(key: object, aliases: tuple[str, ...], *, exclude: tuple[str, ...] = ()) -> bool:
    normalized = _normalized(key)
    return bool(normalized) and not any(_normalized(item) in normalized for item in exclude) and any(
        _normalized(alias) in normalized for alias in aliases
    )


def _first_decimal(
    row: Mapping[str, Any], aliases: tuple[str, ...], *, exclude: tuple[str, ...] = ()
) -> Decimal | None:
    matches: list[tuple[int, Decimal]] = []
    for key, raw in row.items():
        if not _matches(key, aliases, exclude=exclude):
            continue
        value = _decimal(raw)
        if value is not None:
            matches.append((len(str(key)), value))
    return sorted(matches, key=lambda item: item[0])[0][1] if matches else None


def _first_text(row: Mapping[str, Any], aliases: tuple[str, ...]) -> str | list[str] | None:
    matches: list[tuple[int, str | list[str]]] = []
    for key, raw in row.items():
        if raw in (None, "") or not _matches(key, aliases):
            continue
        value = list(raw) if isinstance(raw, (list, tuple)) else str(raw).strip()
        if value:
            matches.append((len(str(key)), value))
    return sorted(matches, key=lambda item: item[0])[0][1] if matches else None


def _source(result: ProviderResult, operation: ProviderOperation) -> StockAnalysisSource:
    return StockAnalysisSource(
        provider=result.provider,
        operation=operation.value,
        retrieved_at=result.retrieved_at,
        serving_mode=result.serving_mode.value,
    )


def _provider_issues(result: ProviderResult) -> tuple[StockAnalysisIssue, ...]:
    if result.status == ProviderStatus.EMPTY:
        return (StockAnalysisIssue(code="EMPTY_RESULT", message=result.scope_description or "信源未返回数据", retriable=True),)
    return tuple(
        StockAnalysisIssue(
            code=issue.code.value,
            message=issue.safe_message,
            retriable=issue.retriable,
        )
        for issue in result.issues
    )


async def _execute(
    provider: Any,
    *,
    operation: ProviderOperation,
    subject: str,
    parameters: dict[str, Any] | None = None,
    timeout_seconds: float = 8.0,
) -> ProviderResult | BaseException:
    request = ProviderRequest(
        request_id=f"stock-analysis-{uuid4().hex}",
        operation=operation,
        subject=subject,
        parameters=parameters or {"limit": 5},
        timeout_ms=int(timeout_seconds * 1000),
    )
    try:
        return await asyncio.wait_for(provider.execute(request), timeout=timeout_seconds)
    except asyncio.CancelledError:
        raise
    except BaseException as exc:  # converted to a safe section issue by the caller
        return exc


async def _execute_structured_finance(
    provider: Any | None,
    *,
    symbol: str,
    timeout_seconds: float = 8.0,
) -> Mapping[str, Any] | BaseException | None:
    """Read Fuyao's structured snapshot without coupling this service to its adapter."""
    if provider is None or not getattr(provider, "is_configured", False):
        return None
    try:
        result = await asyncio.wait_for(
            provider.get_stock_research(symbol), timeout=timeout_seconds
        )
        return result if isinstance(result, Mapping) else None
    except asyncio.CancelledError:
        raise
    except BaseException as exc:  # normalized to safe section issues below
        return exc


def _structured_issue(result: Mapping[str, Any] | BaseException | None) -> StockAnalysisIssue | None:
    if result is None:
        return StockAnalysisIssue(
            code="FUYAO_UNCONFIGURED",
            message="扶摇结构化财务信源未配置，已保留其他真实信源结果。",
            retriable=False,
        )
    if isinstance(result, BaseException):
        return StockAnalysisIssue(
            code=str(getattr(result, "code", "FUYAO_UPSTREAM_ERROR")),
            message=str(getattr(result, "safe_message", "扶摇结构化财务查询失败。")),
            retriable=True,
        )
    if isinstance(result, Mapping):
        return StockAnalysisIssue(
            code="FUYAO_SYMBOL_MISMATCH",
            message="扶摇结构化财务返回的证券身份与请求标的不一致，已拒绝使用该结果。",
            retriable=True,
        )
    return None


def _structured_row(
    result: Mapping[str, Any] | BaseException | None, symbol: str
) -> Mapping[str, Any] | None:
    if not isinstance(result, Mapping):
        return None
    returned = str(result.get("symbol") or "").strip().upper()
    return result if returned == symbol.upper() else None


def _structured_source(
    result: Mapping[str, Any], *, operation: str, fallback_time: datetime
) -> StockAnalysisSource:
    raw_time = result.get("retrieved_at") or result.get("observed_at")
    try:
        retrieved_at = datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        retrieved_at = fallback_time
    return StockAnalysisSource(
        provider="fuyao_finance_api",
        operation=operation,
        retrieved_at=retrieved_at,
        serving_mode=str(result.get("provider_tier") or "LIVE_PRIMARY"),
    )


def _values_conflict(first: Decimal | None, second: Decimal | None) -> bool:
    if first is None or second is None:
        return False
    baseline = max(abs(first), abs(second), Decimal("0.01"))
    return abs(first - second) / baseline > Decimal("0.001")


def _failure_section(
    result: ProviderResult | BaseException,
    *,
    missing: tuple[str, ...],
    operation: ProviderOperation,
) -> StockAnalysisSection:
    if isinstance(result, ProviderResult):
        issues = _provider_issues(result) or (
            StockAnalysisIssue(code="UPSTREAM_UNAVAILABLE", message="上游未返回可用数据", retriable=True),
        )
        sources = (_source(result, operation),)
    else:
        code = "TIMEOUT" if isinstance(result, TimeoutError) else "UPSTREAM_ERROR"
        message = "上游查询超时" if code == "TIMEOUT" else "上游查询失败"
        issues = (StockAnalysisIssue(code=code, message=message, retriable=True),)
        sources = ()
    return StockAnalysisSection(
        status=AnalysisStatus.UNAVAILABLE,
        missing_fields=missing,
        issues=issues,
        sources=sources,
    )


def _result_row(result: ProviderResult | BaseException, symbol: str) -> Mapping[str, Any] | None:
    if not isinstance(result, ProviderResult) or result.status not in {ProviderStatus.SUCCESS, ProviderStatus.PARTIAL}:
        return None
    return select_wencai_item(result, symbol)


async def resolve_live_stock_identity(provider: Any, query: str) -> list[dict[str, str]]:
    """Resolve an exact stock name to one or more traceable A-share identities."""
    clean_name = query.strip()
    if not clean_name:
        return []
    result = await _execute(
        provider,
        operation=ProviderOperation.COMPANY_DATA,
        subject=f"{clean_name} 股票代码 股票简称",
        parameters={"limit": 10},
        timeout_seconds=4.0,
    )
    if not isinstance(result, ProviderResult) or result.status not in {ProviderStatus.SUCCESS, ProviderStatus.PARTIAL} or not result.records:
        return []
    raw_items = dict(result.records[0].fields).get("items")
    if not isinstance(raw_items, (list, tuple)):
        return []
    expected = _normalized(clean_name)
    candidates: dict[str, dict[str, str]] = {}
    valid_prefixes = (
        "600", "601", "603", "605", "688", "689", "000", "001", "002", "003",
        "300", "301", "82", "83", "87", "88", "92",
    )
    for item in raw_items:
        if not isinstance(item, Mapping):
            continue
        name = _first_text(item, ("股票简称", "证券简称", "股票名称", "名称"))
        code = _first_text(item, ("股票代码", "证券代码", "代码", "thscode", "symbol"))
        if not isinstance(name, str) or not isinstance(code, str) or _normalized(name) != expected:
            continue
        clean_code = code.split(".")[0].strip()
        if not re.fullmatch(r"\d{6}", clean_code) or not clean_code.startswith(valid_prefixes):
            continue
        symbol = f"{clean_code}.{market_prefix(clean_code).upper()}"
        candidates[symbol] = {"symbol": symbol, "name": name}
    return [candidates[key] for key in sorted(candidates)]


def _observed_at(row: Mapping[str, Any]) -> str | None:
    explicit = _first_text(row, ("行情时间", "最新价时间", "更新时间", "报告日期", "数据时间"))
    if isinstance(explicit, str):
        return explicit
    dates = []
    for key in row:
        dates.extend(_DATE8.findall(str(key)))
    if not dates:
        return None
    value = sorted(dates)[-1]
    return f"{value[:4]}-{value[4:6]}-{value[6:]}"


def _performance_section(
    results: Mapping[int, ProviderResult | BaseException],
    symbol: str,
    current: ProviderResult | BaseException,
    structured: Mapping[str, Any] | BaseException | None,
    generated_at: datetime,
) -> StockAnalysisSection:
    current_row = _result_row(current, symbol) or {}
    values: dict[str, Decimal | None] = {
        "latest_price_cny": _q2(_first_decimal(current_row, ("最新价", "现价", "收盘价"))),
        "latest_change_pct": _q2(_first_decimal(current_row, ("最新涨跌幅", "涨跌幅"))),
        "market_cap_cny": _q2(_first_decimal(current_row, ("总市值", "市值"))),
    }
    issues: list[StockAnalysisIssue] = []
    sources: list[StockAnalysisSource] = []
    observed: list[str] = []
    if isinstance(current, ProviderResult):
        sources.append(_source(current, ProviderOperation.COMPANY_DATA))
    structured_row = _structured_row(structured, symbol)
    if structured_row is not None:
        fuyao_price = _q2(_decimal(structured_row.get("price_cny")))
        fuyao_change = _q2(_decimal(structured_row.get("change_pct")))
        if _values_conflict(values["latest_price_cny"], fuyao_price):
            issues.append(StockAnalysisIssue(
                code="SOURCE_CONFLICT",
                message="扶摇与问财最新价偏差超过 0.1%，当前价采用扶摇行情并保留冲突提示。",
            ))
        if fuyao_price is not None:
            values["latest_price_cny"] = fuyao_price
        if fuyao_change is not None:
            values["latest_change_pct"] = fuyao_change
        sources.append(_structured_source(
            structured_row, operation="stock_quote", fallback_time=generated_at
        ))
        if structured_row.get("observed_at"):
            observed.append(str(structured_row["observed_at"]))
    elif issue := _structured_issue(structured):
        issues.append(issue)
    if date := _observed_at(current_row):
        observed.append(date)
    for days, result in results.items():
        row = _result_row(result, symbol)
        if isinstance(result, ProviderResult):
            sources.append(_source(result, ProviderOperation.MARKET_DATA))
        if row is None:
            values[f"return_{days}d_pct"] = None
            if isinstance(result, ProviderResult):
                issues.extend(_provider_issues(result))
            else:
                issues.append(StockAnalysisIssue(code="UPSTREAM_ERROR", message=f"{days} 日表现查询失败", retriable=True))
            continue
        value = _first_decimal(row, ("涨跌幅", "区间涨跌", "阶段涨跌"), exclude=("最新涨跌幅", "日涨跌幅"))
        if value is None:
            value = _first_decimal(row, ("涨跌幅",))
        values[f"return_{days}d_pct"] = _q2(value)
        if date := _observed_at(row):
            observed.append(date)
    missing = tuple(key for key, value in values.items() if value is None)
    present = len(values) - len(missing)
    return StockAnalysisSection(
        status=(
            AnalysisStatus.COMPLETE
            if not missing and structured_row is not None
            else AnalysisStatus.PARTIAL if present else AnalysisStatus.UNAVAILABLE
        ),
        data={"adjustment": "前复权", **values},
        missing_fields=missing,
        issues=tuple(_dedupe_issues(issues)),
        observed_at=max(observed) if observed else None,
        sources=tuple(sources),
    )


_ANNUAL_ALIASES: dict[str, tuple[str, ...]] = {
    "revenue_cny": ("营业收入", "营业总收入"),
    "net_profit_cny": ("归属于母公司股东的净利润", "归母净利润", "归属母公司净利润"),
    "operating_cash_flow_cny": ("经营活动产生的现金流量净额", "经营现金流量净额", "经营现金流"),
    "roe_pct": ("净资产收益率ROE", "净资产收益率", "ROE"),
}


def _annual_series(row: Mapping[str, Any], lookback_years: int) -> list[dict[str, Any]]:
    by_year: dict[int, dict[str, Any]] = {}
    for key, raw in row.items():
        years = _YEAR.findall(str(key))
        if not years:
            continue
        year = int(years[-1])
        for field, aliases in _ANNUAL_ALIASES.items():
            if _matches(key, aliases, exclude=("同比", "增长率")):
                value = _decimal(raw)
                if value is not None:
                    by_year.setdefault(year, {"year": year})[field] = _q2(value)
                break
    years = sorted(by_year)[-lookback_years:]
    return [by_year[year] for year in years]


def _fundamentals_section(
    current: ProviderResult | BaseException,
    annual: ProviderResult | BaseException,
    structured: Mapping[str, Any] | BaseException | None,
    symbol: str,
    lookback_years: int,
    generated_at: datetime,
) -> tuple[StockAnalysisSection, SecurityIdentity]:
    current_row = _result_row(current, symbol)
    annual_row = _result_row(annual, symbol)
    base_row = current_row or annual_row or {}
    structured_row = _structured_row(structured, symbol)
    name = _first_text(base_row, ("股票简称", "证券简称", "股票名称", "名称"))
    if not name and structured_row is not None:
        name = str(structured_row.get("name") or "").strip() or None
    industry = _first_text(base_row, ("所属同花顺行业", "所属申万行业", "行业"))
    identity = SecurityIdentity(symbol=symbol, name=str(name or symbol), industry=industry)
    if not base_row and structured_row is None:
        result = current if isinstance(current, ProviderResult) else annual
        return _failure_section(
            result,
            missing=("security_identity", "annual_financials"),
            operation=ProviderOperation.COMPANY_DATA,
        ), identity

    latest = current_row or {}
    revenue = _first_decimal(latest, ("营业收入", "营业总收入"), exclude=("同比", "增长率"))
    net_profit = _first_decimal(latest, ("归属于母公司股东的净利润", "归母净利润", "净利润"), exclude=("同比", "增长率"))
    cash_flow = _first_decimal(latest, ("经营活动产生的现金流量净额", "经营现金流量净额", "经营现金流"), exclude=("同比", "增长率"))
    latest_data = {
        "report_period": _first_text(latest, ("最新报告期", "报告期", "报告日期")),
        "revenue_cny": _q2(revenue),
        "net_profit_cny": _q2(net_profit),
        "operating_cash_flow_cny": _q2(cash_flow),
        "roe_pct": _q2(_first_decimal(latest, ("净资产收益率", "ROE"))),
        "gross_margin_pct": _q2(_first_decimal(latest, ("销售毛利率", "毛利率"))),
        "debt_ratio_pct": _q2(_first_decimal(latest, ("资产负债率", "负债率"))),
        "revenue_yoy_pct": _q2(_first_decimal(latest, ("营业收入同比", "营业收入增长率"))),
        "net_profit_yoy_pct": _q2(_first_decimal(latest, ("归母净利润同比", "净利润同比", "净利润增长率"))),
    }
    issues: list[StockAnalysisIssue] = []
    if structured_row is not None:
        for field in ("roe_pct", "gross_margin_pct", "debt_ratio_pct"):
            fuyao_value = _q2(_decimal(structured_row.get(field)))
            if _values_conflict(latest_data[field], fuyao_value):
                issues.append(StockAnalysisIssue(
                    code="SOURCE_CONFLICT",
                    message=f"{field} 在扶摇与问财之间存在口径或观测期差异，采用扶摇结构化财务值。",
                ))
            if fuyao_value is not None:
                latest_data[field] = fuyao_value
        if structured_row.get("financial_report_period"):
            latest_data["report_period"] = structured_row["financial_report_period"]
    latest_data["net_margin_pct"] = _q2(net_profit / revenue * 100) if revenue and revenue > 0 and net_profit is not None else None
    latest_data["cash_conversion_pct"] = _q2(cash_flow / net_profit * 100) if net_profit and net_profit > 0 and cash_flow is not None else None
    series = _annual_series(annual_row or {}, lookback_years)
    missing = [key for key, value in latest_data.items() if value is None]
    if len(series) < lookback_years:
        missing.append("annual_financials")
    if structured_row is None and (issue := _structured_issue(structured)):
        issues.append(issue)
    if net_profit is None or net_profit <= 0:
        issues.append(StockAnalysisIssue(
            code="CASH_CONVERSION_UNAVAILABLE",
            message="净利润缺失或不为正，经营现金流/净利润不计算。",
        ))
    sources = tuple(
        _source(result, ProviderOperation.COMPANY_DATA)
        for result in (current, annual)
        if isinstance(result, ProviderResult)
    )
    if structured_row is not None:
        sources += (_structured_source(
            structured_row, operation="financial_statements_and_indicators",
            fallback_time=generated_at,
        ),)
    present = sum(value is not None for value in latest_data.values())
    return StockAnalysisSection(
        status=(
            AnalysisStatus.COMPLETE
            if not missing and structured_row is not None
            else AnalysisStatus.PARTIAL if present or series else AnalysisStatus.UNAVAILABLE
        ),
        data={"latest": latest_data, "annual": series, "lookback_years": lookback_years},
        missing_fields=tuple(dict.fromkeys(missing)),
        issues=tuple(issues),
        observed_at=_observed_at(latest),
        sources=sources,
    ), identity


def _valuation_section(
    result: ProviderResult | BaseException,
    structured: Mapping[str, Any] | BaseException | None,
    symbol: str,
    generated_at: datetime,
) -> StockAnalysisSection:
    row = _result_row(result, symbol)
    structured_row = _structured_row(structured, symbol)
    if row is None and structured_row is None:
        return _failure_section(result, missing=("pe_ttm", "pb", "historical_percentiles", "industry_averages"), operation=ProviderOperation.COMPANY_DATA)
    row = row or {}
    pe = _first_decimal(row, ("市盈率TTM", "PETTM", "市盈率"), exclude=("行业", "分位", "平均", "均值"))
    pb = _first_decimal(row, ("市净率", "PB"), exclude=("行业", "分位", "平均", "均值"))
    issues: list[StockAnalysisIssue] = []
    sources = [_source(result, ProviderOperation.COMPANY_DATA)] if isinstance(result, ProviderResult) else []
    if structured_row is not None:
        fuyao_pe = _decimal(structured_row.get("pe_ttm"))
        fuyao_pb = _decimal(structured_row.get("pb"))
        for field_name, current_value, fuyao_value in (
            ("pe_ttm", pe, fuyao_pe), ("pb", pb, fuyao_pb)
        ):
            if _values_conflict(current_value, fuyao_value):
                issues.append(StockAnalysisIssue(
                    code="SOURCE_CONFLICT",
                    message=f"{field_name} 在扶摇与问财之间存在差异，采用扶摇估值快照。",
                ))
        pe = fuyao_pe if fuyao_pe is not None else pe
        pb = fuyao_pb if fuyao_pb is not None else pb
        sources.append(_structured_source(
            structured_row, operation="valuation_snapshot", fallback_time=generated_at
        ))
    elif issue := _structured_issue(structured):
        issues.append(issue)
    pe_pct = _first_decimal(row, ("市盈率历史分位", "市盈率分位", "PE历史分位", "PE分位"))
    pb_pct = _first_decimal(row, ("市净率历史分位", "市净率分位", "PB历史分位", "PB分位"))
    if pe_pct is not None and 0 <= pe_pct <= 1:
        pe_pct *= 100
    if pb_pct is not None and 0 <= pb_pct <= 1:
        pb_pct *= 100
    industry_pe = _first_decimal(row, ("行业市盈率平均", "行业市盈率均值", "所属行业市盈率"), exclude=("分位",))
    industry_pb = _first_decimal(row, ("行业市净率平均", "行业市净率均值", "所属行业市净率"), exclude=("分位",))
    data = {
        "pe_ttm": _q2(pe),
        "pb": _q2(pb),
        "pe_historical_percentile_pct": _q2(pe_pct),
        "pb_historical_percentile_pct": _q2(pb_pct),
        "percentile_window": None,
        "industry_pe_ttm_mean": _q2(industry_pe),
        "industry_pb_mean": _q2(industry_pb),
        "pe_premium_to_industry_pct": _q2((pe / industry_pe - 1) * 100) if pe is not None and industry_pe and industry_pe > 0 else None,
        "pb_premium_to_industry_pct": _q2((pb / industry_pb - 1) * 100) if pb is not None and industry_pb and industry_pb > 0 else None,
    }
    missing = tuple(key for key, value in data.items() if value is None and key != "percentile_window")
    issues.append(StockAnalysisIssue(
        code="PERCENTILE_WINDOW_UNSPECIFIED",
        message="信源未说明历史分位窗口，分位仅按原始口径展示。",
    ))
    return StockAnalysisSection(
        status=(
            AnalysisStatus.COMPLETE
            if not missing and structured_row is not None
            else AnalysisStatus.PARTIAL
        ),
        data=data,
        missing_fields=missing,
        issues=tuple(issues),
        observed_at=_observed_at(row),
        sources=tuple(sources),
    )


def _safe_http_url(value: object) -> str | None:
    raw = str(value or "").strip()
    parsed = urlparse(raw)
    return raw if parsed.scheme.lower() in {"http", "https"} and parsed.netloc else None


def _evidence_items(result: ProviderResult | BaseException, symbol: str, kind: str) -> list[dict[str, Any]]:
    if not isinstance(result, ProviderResult) or not result.records:
        return []
    fields = dict(result.records[0].fields)
    raw_items = fields.get("items")
    if not isinstance(raw_items, (list, tuple)):
        return []
    expected = symbol.split(".")[0]
    items: list[dict[str, Any]] = []
    for raw in raw_items:
        if not isinstance(raw, Mapping):
            continue
        stock_infos = raw.get("stock_infos")
        if stock_infos:
            serialized = str(stock_infos)
            codes = re.findall(r"(?<!\d)\d{6}(?!\d)", serialized)
            if codes and expected not in codes:
                continue
        title = str(raw.get("title") or "").strip()
        if not title:
            continue
        items.append({
            "evidence_id": f"{kind}:{raw.get('id') or len(items) + 1}",
            "kind": kind,
            "title": title,
            "date": raw.get("publish_time") or raw.get("publish_date"),
            "source": raw.get("source_original") or raw.get("data_source") or result.provider,
            "url": _safe_http_url(raw.get("url")),
            "summary": str(raw.get("summary") or "").strip() or None,
        })
        if len(items) == 5:
            break
    return items


def _evidence_section(
    results: Mapping[str, tuple[ProviderResult | BaseException, ProviderOperation]],
    symbol: str,
) -> StockAnalysisSection:
    data: dict[str, Any] = {}
    missing: list[str] = []
    issues: list[StockAnalysisIssue] = []
    sources: list[StockAnalysisSource] = []
    for kind, (result, operation) in results.items():
        items = _evidence_items(result, symbol, kind)
        data[kind] = items
        if not items:
            missing.append(kind)
            if isinstance(result, ProviderResult):
                issues.extend(_provider_issues(result))
            else:
                issues.append(StockAnalysisIssue(code="UPSTREAM_ERROR", message=f"{kind} 查询失败", retriable=True))
        if isinstance(result, ProviderResult):
            sources.append(_source(result, operation))
    present = sum(bool(value) for value in data.values())
    return StockAnalysisSection(
        status=AnalysisStatus.COMPLETE if not missing else AnalysisStatus.PARTIAL if present else AnalysisStatus.UNAVAILABLE,
        data=data,
        missing_fields=tuple(missing),
        issues=tuple(_dedupe_issues(issues)),
        observed_at=max((str(item.get("date")) for values in data.values() for item in values if item.get("date")), default=None),
        sources=tuple(sources),
    )


def build_portfolio_fit_section(
    symbol: str,
    *,
    portfolio_data: Mapping[str, Any] | None,
    profile: RiskProfile | None,
) -> StockAnalysisSection:
    missing: list[str] = []
    issues: list[StockAnalysisIssue] = []
    data: dict[str, Any] = {
        "held": False,
        "quantity": None,
        "cost_price_cny": None,
        "current_price_cny": None,
        "market_value_cny": None,
        "unrealized_pnl_cny": None,
        "unrealized_pnl_pct": None,
        "weight_pct": None,
        "single_asset_limit_pct": None,
        "industry_limit_pct": None,
        "within_single_asset_limit": None,
    }
    bundle: PortfolioImportBundle | None = None
    if portfolio_data and portfolio_data.get("portfolio"):
        try:
            bundle = PortfolioImportBundle.model_validate(portfolio_data["portfolio"])
        except (TypeError, ValueError):
            issues.append(StockAnalysisIssue(code="PORTFOLIO_INVALID", message="已保存持仓无法校验", retriable=False))
    if bundle is None:
        missing.append("confirmed_portfolio")
    else:
        positions = [position for position in bundle.position_snapshot.positions if position.asset_id.upper() == symbol.upper()]
        total = sum((position.market_value for position in bundle.position_snapshot.positions), Decimal("0"))
        cash = _decimal(portfolio_data.get("cash_cny")) or Decimal("0")
        total += cash
        if positions:
            market_value = sum((position.market_value for position in positions), Decimal("0"))
            quantity = sum((position.quantity for position in positions), Decimal("0"))
            raw_position = next((row for row in portfolio_data.get("positions", []) if str(row.get("asset_id", "")).upper() == symbol.upper()), {})
            cost_price = _decimal(raw_position.get("cost_price"))
            cost_basis = cost_price * quantity if cost_price is not None else None
            unrealized = market_value - cost_basis if cost_basis is not None else None
            data.update(
                held=True,
                quantity=_q2(quantity),
                cost_price_cny=_q2(cost_price),
                current_price_cny=_q2(market_value / quantity) if quantity > 0 else None,
                market_value_cny=_q2(market_value),
                unrealized_pnl_cny=_q2(unrealized),
                unrealized_pnl_pct=_q2(unrealized / cost_basis * 100) if unrealized is not None and cost_basis and cost_basis > 0 else None,
                weight_pct=_q2(market_value / total * 100) if total > 0 else None,
            )
    if profile is None:
        missing.append("confirmed_profile")
    else:
        budget = build_risk_budget(profile)
        data["single_asset_limit_pct"] = budget.max_single_asset_weight_pct
        data["industry_limit_pct"] = budget.max_sector_weight_pct
        if data["weight_pct"] is not None:
            data["within_single_asset_limit"] = data["weight_pct"] <= budget.max_single_asset_weight_pct
    present = bundle is not None or profile is not None
    return StockAnalysisSection(
        status=AnalysisStatus.COMPLETE if not missing else AnalysisStatus.PARTIAL if present else AnalysisStatus.UNAVAILABLE,
        data=data,
        missing_fields=tuple(missing),
        issues=tuple(issues),
        observed_at=bundle.position_snapshot.as_of.isoformat() if bundle else None,
        sources=(),
    )


def _dedupe_issues(issues: list[StockAnalysisIssue]) -> list[StockAnalysisIssue]:
    seen: set[tuple[str, str]] = set()
    output: list[StockAnalysisIssue] = []
    for issue in issues:
        key = (issue.code, issue.message)
        if key not in seen:
            seen.add(key)
            output.append(issue)
    return output


def _fact(fact_id: str, text: str, evidence: str) -> dict[str, str]:
    return {"fact_id": fact_id, "text": text, "evidence": evidence}


def build_observations(sections: Mapping[str, StockAnalysisSection]) -> dict[str, list[dict[str, str]]]:
    """Build factual observations only; no rating or trade instruction."""
    support: list[dict[str, str]] = []
    risk: list[dict[str, str]] = []
    watch: list[dict[str, str]] = []
    performance = sections["performance"].data
    fundamentals = sections["fundamentals"].data.get("latest", {})
    valuation = sections["valuation"].data
    portfolio = sections["portfolio_fit"].data
    return_250 = _decimal(performance.get("return_250d_pct"))
    if return_250 is not None:
        target = support if return_250 >= 0 else risk
        target.append(_fact("PERF_250D", f"近 250 日前复权涨跌幅为 {_q2(return_250)}%。", "performance.return_250d_pct"))
    profit_yoy = _decimal(fundamentals.get("net_profit_yoy_pct"))
    if profit_yoy is not None:
        target = support if profit_yoy >= 0 else risk
        target.append(_fact("NET_PROFIT_YOY", f"最新报告期归母净利润同比为 {_q2(profit_yoy)}%。", "fundamentals.latest.net_profit_yoy_pct"))
    cash_flow = _decimal(fundamentals.get("operating_cash_flow_cny"))
    if cash_flow is not None:
        target = support if cash_flow >= 0 else risk
        target.append(_fact("OPERATING_CASH_FLOW", f"最新报告期经营现金流为 {_q2(cash_flow)} 元。", "fundamentals.latest.operating_cash_flow_cny"))
    pe_premium = _decimal(valuation.get("pe_premium_to_industry_pct"))
    if pe_premium is not None:
        target = support if pe_premium <= 0 else risk
        relation = "折价" if pe_premium <= 0 else "溢价"
        target.append(_fact("PE_INDUSTRY", f"PE（TTM）相对行业均值{relation} {abs(_q2(pe_premium))}%。", "valuation.pe_premium_to_industry_pct"))
    if portfolio.get("held"):
        if portfolio.get("within_single_asset_limit") is False:
            risk.append(_fact("POSITION_LIMIT", "当前账户该标的占比超过画像单一标的上限。", "portfolio_fit.within_single_asset_limit"))
        else:
            watch.append(_fact("POSITION_CONTEXT", f"当前账户持有该标的，占总资产 {portfolio.get('weight_pct')}%。", "portfolio_fit.weight_pct"))
    for section_name, section in sections.items():
        if section.status != AnalysisStatus.COMPLETE:
            missing = "、".join(section.missing_fields) or "上游数据"
            watch.append(_fact(f"MISSING_{section_name.upper()}", f"{section_name} 尚缺：{missing}。", f"sections.{section_name}.missing_fields"))
    return {"supporting_facts": support, "risk_facts": risk, "watch_items": watch}


async def build_live_stock_analysis(
    symbol: str,
    *,
    lookback_years: int,
    provider: Any,
    structured_provider: Any | None = None,
    portfolio_data: Mapping[str, Any] | None,
    profile: RiskProfile | None,
    generated_at: datetime | None = None,
) -> LiveStockAnalysisResponse:
    """Run all live sections concurrently without any fixture fallback."""
    effective_generated_at = generated_at or datetime.now(UTC)
    annual_years = " ".join(str(year) for year in range(effective_generated_at.year - lookback_years, effective_generated_at.year))
    tasks: dict[str, Any] = {
        "current": _execute(
            provider,
            operation=ProviderOperation.COMPANY_DATA,
            subject=(
                f"{symbol} 股票简称 所属同花顺行业 最新价 最新涨跌幅 总市值 最新报告期 营业收入 归母净利润 "
                "经营活动产生的现金流量净额 净资产收益率(ROE) 销售毛利率 资产负债率 "
                "营业收入同比 归母净利润同比"
            ),
        ),
        "annual": _execute(
            provider,
            operation=ProviderOperation.COMPANY_DATA,
            subject=f"{symbol} {annual_years}年报 营业收入 归母净利润 经营活动产生的现金流量净额 净资产收益率(ROE)",
        ),
        "valuation": _execute(
            provider,
            operation=ProviderOperation.COMPANY_DATA,
            subject=f"{symbol} 市盈率(TTM) 市净率 PE历史分位 PB历史分位 所属行业市盈率均值 所属行业市净率均值",
        ),
        "announcement": _execute(
            provider,
            operation=ProviderOperation.SEARCH_NEWS,
            subject=f"{symbol} 最新公告",
            parameters={"limit": 5, "channel": "announcement"},
        ),
        "news": _execute(
            provider,
            operation=ProviderOperation.SEARCH_NEWS,
            subject=f"{symbol} 最新新闻",
            parameters={"limit": 5, "channel": "news"},
        ),
        "report": _execute(
            provider,
            operation=ProviderOperation.SEARCH_REPORTS,
            subject=f"{symbol} 最新研报",
            parameters={"limit": 5, "channel": "report"},
        ),
        "structured": _execute_structured_finance(
            structured_provider, symbol=symbol
        ),
    }
    for days in (20, 60, 120, 250):
        tasks[f"performance_{days}"] = _execute(
            provider,
            operation=ProviderOperation.MARKET_DATA,
            subject=f"{symbol} 近{days}个交易日涨跌幅 前复权",
        )
    keys = tuple(tasks)
    values = await asyncio.gather(*(tasks[key] for key in keys))
    results = dict(zip(keys, values, strict=True))

    performance = _performance_section(
        {days: results[f"performance_{days}"] for days in (20, 60, 120, 250)},
        symbol,
        results["current"],
        results["structured"],
        effective_generated_at,
    )
    fundamentals, identity = _fundamentals_section(
        results["current"], results["annual"], results["structured"],
        symbol, lookback_years, effective_generated_at
    )
    valuation = _valuation_section(
        results["valuation"], results["structured"], symbol, effective_generated_at
    )
    evidence = _evidence_section({
        "announcements": (results["announcement"], ProviderOperation.SEARCH_NEWS),
        "news": (results["news"], ProviderOperation.SEARCH_NEWS),
        "reports": (results["report"], ProviderOperation.SEARCH_REPORTS),
    }, symbol)
    portfolio_fit = build_portfolio_fit_section(
        symbol, portfolio_data=portfolio_data, profile=profile
    )
    sections = {
        "performance": performance,
        "fundamentals": fundamentals,
        "valuation": valuation,
        "evidence": evidence,
        "portfolio_fit": portfolio_fit,
    }
    unavailable = [name for name, section in sections.items() if section.status == AnalysisStatus.UNAVAILABLE]
    partial = [name for name, section in sections.items() if section.status == AnalysisStatus.PARTIAL]
    status = AnalysisStatus.UNAVAILABLE if len(unavailable) == len(sections) else AnalysisStatus.PARTIAL if unavailable or partial else AnalysisStatus.COMPLETE
    top_issues = _dedupe_issues([issue for section in sections.values() for issue in section.issues])
    return LiveStockAnalysisResponse(
        status=status,
        security=identity,
        generated_at=effective_generated_at,
        missing_fields=tuple(f"{name}.{field}" for name, section in sections.items() for field in section.missing_fields),
        issues=tuple(top_issues),
        observations=build_observations(sections),
        sections=sections,
    )


__all__ = [
    "AnalysisStatus",
    "LiveStockAnalysisResponse",
    "StockAnalysisSection",
    "build_live_stock_analysis",
    "build_observations",
    "build_portfolio_fit_section",
    "resolve_live_stock_identity",
]
