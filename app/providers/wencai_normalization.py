"""Deterministic decoding for raw Wencai SkillHub rows.

The official endpoint returns dynamic Chinese column names.  This module keeps
that decoding outside the LLM and only binds a row after its security code has
been matched exactly (ignoring the exchange suffix).
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
import math
import re
from typing import Any

from app.providers.contracts import ProviderResult


STOCK_METRIC_ALIASES: dict[str, tuple[str, ...]] = {
    "pe_ttm": (
        "pe_ttm",
        "PE(TTM)",
        "市盈率(TTM)",
        "市盈率（TTM）",
        "市盈率TTM",
    ),
    "pb": (
        "pb",
        "PB",
        "市净率",
    ),
    "roe_pct": (
        "roe_pct",
        "ROE",
        "净资产收益率",
        "净资产收益率(ROE)",
        "净资产收益率（ROE）",
    ),
    "valuation_quantile_pct": (
        "valuation_quantile_pct",
        "估值分位",
        "估值分位数",
        "估值百分位",
        "综合估值百分位",
        "市盈率分位",
        "市盈率分位数",
        "市盈率历史分位",
        "市盈率相对历史百分位",
        "PE(TTM)历史分位",
    ),
    "gross_margin_pct": (
        "gross_margin_pct",
        "毛利率",
        "销售毛利率",
    ),
    "debt_ratio_pct": (
        "debt_ratio_pct",
        "资产负债率",
        "负债率",
    ),
    "market_cap_cny": (
        "market_cap_cny",
        "总市值",
        "总市值(元)",
        "总市值（元）",
    ),
}

_CODE_ALIASES = ("股票代码", "证券代码", "代码", "thscode", "symbol", "code")
_NAME_ALIASES = ("股票简称", "证券简称", "名称", "股票名称", "name")
_INDUSTRY_ALIASES = ("所属同花顺行业", "所属申万行业", "行业", "industry")
_PRICE_ALIASES = ("price_cny", "最新价", "现价", "最新价格", "收盘价", "价格")


def _normalized_key(value: object) -> str:
    return re.sub(r"[\s_\-()（）\[\]【】%:：/\\]+", "", str(value or "")).casefold()


def _matches_alias(key: object, alias: str) -> bool:
    normalized_key = _normalized_key(key)
    normalized_alias = _normalized_key(alias)
    return bool(normalized_key and normalized_alias) and (
        normalized_key == normalized_alias
        or normalized_key.startswith(normalized_alias)
        or normalized_alias in normalized_key
    )


def _first_value(row: Mapping[str, Any], aliases: tuple[str, ...]) -> tuple[Any, str | None]:
    candidates: list[tuple[int, str, Any]] = []
    for key, value in row.items():
        if value in (None, ""):
            continue
        normalized_key = _normalized_key(key)
        for alias in aliases:
            normalized_alias = _normalized_key(alias)
            if normalized_key == normalized_alias:
                candidates.append((0, str(key), value))
                break
            if _matches_alias(key, alias):
                candidates.append((len(normalized_key) - len(normalized_alias) + 1, str(key), value))
                break
    if not candidates:
        return None, None
    _, key, value = sorted(candidates, key=lambda item: (item[0], len(item[1])))[0]
    return value, key


def _items(result: ProviderResult) -> tuple[Mapping[str, Any], ...]:
    if not result.records:
        return ()
    raw_items = dict(result.records[0].fields).get("items")
    if not isinstance(raw_items, (list, tuple)):
        return ()
    return tuple(item for item in raw_items if isinstance(item, Mapping))


def select_wencai_item(result: ProviderResult, security_code: str) -> Mapping[str, Any] | None:
    """Select a raw row only when its security code matches the requested code."""
    expected = security_code.split(".")[0].strip().upper()
    for item in _items(result):
        value, _ = _first_value(item, _CODE_ALIASES)
        if str(value or "").split(".")[0].strip().upper() == expected:
            return item
    return None


def _column_units(result: ProviderResult) -> dict[str, str]:
    if not result.records:
        return {}
    raw_columns = dict(result.records[0].fields).get("columns")
    if not isinstance(raw_columns, (list, tuple)):
        return {}
    units: dict[str, str] = {}
    for column in raw_columns:
        if not isinstance(column, Mapping):
            continue
        key = column.get("key")
        unit = column.get("unit")
        if key and isinstance(unit, str):
            units[_normalized_key(key)] = unit
    return units


def _finite_number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "").replace("，", "")
        if cleaned.endswith("%"):
            cleaned = cleaned[:-1].strip()
    else:
        cleaned = value
    try:
        parsed = Decimal(str(cleaned))
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite():
        return None
    number = float(parsed)
    return number if math.isfinite(number) else None


def decode_stock_metrics(result: ProviderResult, security_code: str) -> dict[str, Any]:
    """Decode supported stock financial fields from one matched Wencai row."""
    if result.status.value not in {"SUCCESS", "PARTIAL"}:
        return {}
    item = select_wencai_item(result, security_code)
    if item is None:
        return {}
    units = _column_units(result)
    decoded: dict[str, Any] = {}
    for field_name, aliases in STOCK_METRIC_ALIASES.items():
        raw_value, source_key = _first_value(item, aliases)
        value = _finite_number(raw_value)
        if value is None:
            continue
        if (
            field_name == "valuation_quantile_pct"
            and source_key
            and "分位点" in str(source_key)
            and 0 <= value <= 1
        ):
            value *= 100
        if field_name == "valuation_quantile_pct" and not 0 <= value <= 100:
            continue
        decoded[field_name] = value
        if source_key and units.get(_normalized_key(source_key)):
            decoded.setdefault("field_units", {})[field_name] = units[_normalized_key(source_key)]
    return decoded


def decode_stock_identity(result: ProviderResult, security_code: str) -> dict[str, Any]:
    """Decode name, industry and optional observation time from one matched row."""
    item = select_wencai_item(result, security_code)
    if item is None:
        return {}
    name, _ = _first_value(item, _NAME_ALIASES)
    industry, _ = _first_value(item, _INDUSTRY_ALIASES)
    observed_at, _ = _first_value(item, ("最新价时间", "行情时间", "更新时间", "数据时间"))
    return {
        key: value
        for key, value in {
            "name": name,
            "industry": industry,
            "observed_at": observed_at,
        }.items()
        if value not in (None, "")
    }


def decode_stock_quote_fields(result: ProviderResult, security_code: str) -> dict[str, Any]:
    """Decode a matched Wencai row's price and observation time, if present."""
    item = select_wencai_item(result, security_code)
    if item is None:
        return {}
    price, _ = _first_value(item, _PRICE_ALIASES)
    decoded_price = _finite_number(price)
    identity = decode_stock_identity(result, security_code)
    decoded: dict[str, Any] = {}
    if decoded_price is not None:
        decoded["price_cny"] = decoded_price
    if identity.get("observed_at"):
        decoded["observed_at"] = identity["observed_at"]
    return decoded


def source_industry_label(value: object) -> str | None:
    """Return the provider's primary industry label without replacing it.

    Some official responses expose an industry hierarchy as a list.  The first
    non-empty value is the provider's primary classification and is the label
    persisted in the portfolio.  Policy bucketing remains a separate,
    deterministic calculation and must never overwrite this source field.
    """
    values = value if isinstance(value, (list, tuple)) else (value,)
    for item in values:
        label = str(item or "").strip()
        if label and label.casefold() not in {
            "未知", "未知行业", "其他", "unknown", "unclassified", "n/a", "-",
        }:
            return label
    return None


def canonical_sector_from_wencai(value: object) -> str | None:
    """Map a source industry into the internal policy taxonomy only."""
    labels = " ".join(str(item) for item in value) if isinstance(value, (list, tuple)) else str(value or "")
    mappings = (
        (("半导体", "电子", "计算机", "通信", "软件", "互联网"), "Technology"),
        (("电力设备", "电气设备", "电池", "机械", "汽车", "军工", "制造"), "Industrials"),
        (("食品", "饮料", "白酒", "消费", "医药", "制药", "生物", "医疗", "家用电器", "家电"), "Consumer"),
        (("银行", "保险", "金融", "煤炭", "石油", "有色", "钢铁", "化工", "公用", "房地产"), "Finance"),
    )
    for keywords, canonical in mappings:
        if any(keyword in labels for keyword in keywords):
            return canonical
    return None


__all__ = [
    "canonical_sector_from_wencai",
    "decode_stock_identity",
    "decode_stock_metrics",
    "decode_stock_quote_fields",
    "select_wencai_item",
    "source_industry_label",
]
