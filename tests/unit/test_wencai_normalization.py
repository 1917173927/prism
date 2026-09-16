from __future__ import annotations

from datetime import UTC, datetime

from app.providers.contracts import ProviderRecord, ProviderResult, ProviderStatus
from app.providers.wencai_normalization import (
    canonical_sector_from_wencai,
    decode_stock_identity,
    decode_stock_metrics,
    source_industry_label,
)


def _result(items: list[dict[str, object]]) -> ProviderResult:
    return ProviderResult(
        request_id="wencai-normalization-test",
        request_fingerprint="test-fingerprint",
        provider="wencai_skillhub_provider",
        status=ProviderStatus.SUCCESS,
        retrieved_at=datetime(2026, 9, 15, tzinfo=UTC),
        records=(ProviderRecord(
            source="wencai_skillhub_provider",
            fields={
                "items": items,
                "columns": [
                    {"key": "市盈率(TTM)", "unit": "倍"},
                    {"key": "净资产收益率(ROE)", "unit": "%"},
                ],
            },
        ),),
    )


def test_stock_decoder_matches_security_code_and_normalizes_financial_aliases() -> None:
    result = _result([
        {
            "股票代码": "600519.SH",
            "股票简称": "贵州茅台",
            "市盈率(TTM)": "28.4",
            "市净率": "8.10",
            "净资产收益率(ROE)": "24.6%",
            "市盈率相对历史百分位": "42.0%",
            "所属同花顺行业": "白酒",
        },
        {
            "股票代码": "300750.SZ",
            "股票简称": "宁德时代",
            "市盈率(TTM)": "25.1",
            "市净率": "4.20",
            "净资产收益率(ROE)": "18.5%",
            "市盈率相对历史百分位": "55.0%",
            "所属同花顺行业": "电力设备",
        },
    ])

    metrics = decode_stock_metrics(result, "300750.SZ")
    identity = decode_stock_identity(result, "300750.SZ")

    assert metrics["pe_ttm"] == 25.1
    assert metrics["pb"] == 4.2
    assert metrics["roe_pct"] == 18.5
    assert metrics["valuation_quantile_pct"] == 55.0
    assert metrics["field_units"]["pe_ttm"] == "倍"
    assert identity == {"name": "宁德时代", "industry": "电力设备"}


def test_stock_decoder_does_not_bind_an_unrelated_wencai_row() -> None:
    result = _result([{
        "股票代码": "600519.SH",
        "市盈率(TTM)": "28.4",
        "市净率": "8.10",
        "净资产收益率(ROE)": "24.6%",
        "市盈率相对历史百分位": "42.0%",
    }])

    assert decode_stock_metrics(result, "300750.SZ") == {}
    assert decode_stock_identity(result, "300750.SZ") == {}


def test_canonical_sector_covers_common_household_appliance_industry() -> None:
    assert canonical_sector_from_wencai("家用电器") == "Consumer"


def test_source_industry_keeps_provider_label_separate_from_policy_bucket() -> None:
    assert source_industry_label(["电力设备", "电池", "锂电池"]) == "电力设备"
    assert source_industry_label("农林牧渔") == "农林牧渔"
    assert canonical_sector_from_wencai("电力设备") == "Industrials"
