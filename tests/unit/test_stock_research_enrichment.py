import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from app.providers.fuyao import FuyaoFinanceProvider, FuyaoProviderError


def provider_for(*, mismatched=False, failed=False, ambiguous=False):
    def handler(request):
        path = request.url.path
        if path.endswith('/search'):
            rows = [{"thscode": "300750.SZ", "name": "宁德时代", "asset_type": "a-share"}]
            if ambiguous:
                rows.append({**rows[0], "thscode": "600519.SH"})
            data = {"item": rows}
        elif failed:
            return httpx.Response(200, json={"code": 2003, "data": None})
        elif path.endswith('/snapshot'):
            data = {"timestamp": 1789473113000, "item": [{"thscode": "600519.SH" if mismatched else "300750.SZ", "pe_ttm": -5, "pb_mrq": 0}]}
        elif path.endswith('/income-statements'):
            assert request.url.params["period"] == "quarterly"
            data = {"item": [{"thscode": "300750.SZ", "currency": "CNY", "period_end_ms": 1782748800000, "report_date_ms": 1784908800000}]}
        else:
            assert path.endswith('/indicators')
            assert request.url.params['report'] == '2026-2'
            data = {"thscode": "300750.SZ", "report": "2025-4" if mismatched else "2026-2", "abilities": [
                {"indicators": [{"index_id": "index_weighted_avg_roe", "value": "12.08"},
                                {"index_id": "sale_gross_margin", "value": None},
                                {"index_id": "assets_debt_ratio", "value": "NaN"}]},
                {"indicators": None}, None,
            ]}
        return httpx.Response(200, json={"code": 0, "data": data})
    provider = FuyaoFinanceProvider(api_key='test-key', transport=httpx.MockTransport(handler))
    provider.get_quote = AsyncMock(return_value={"symbol": "300750.SZ", "name": "宁德时代", "price_cny": 100,
        "pe_ttm": None, "pb": None, "roe_pct": None, "valuation_quantile_pct": None,
        "missing_fields": ["pe_ttm", "pb", "roe_pct", "valuation_quantile_pct"]})
    return provider


def test_name_resolution_and_report_bound_values():
    provider = provider_for()
    data = asyncio.run(provider.get_stock_research('宁德时代'))
    provider.get_quote.assert_awaited_once_with('300750.SZ')
    assert data['pe_ttm'] == -5 and data['pb'] == 0
    assert data['roe_pct'] == 12.08
    assert data['financial_report_period'] == '2026-2'
    assert data.get('gross_margin_pct') is None and data.get('debt_ratio_pct') is None
    assert data['valuation_quantile_pct'] is None
    assert data['missing_fields'] == ['valuation_quantile_pct']


def test_wrong_security_or_report_never_leaks_values():
    data = asyncio.run(provider_for(mismatched=True).get_stock_research('300750'))
    assert data['pe_ttm'] is None and data['roe_pct'] is None


def test_financial_failure_preserves_quote_and_safe_reason():
    data = asyncio.run(provider_for(failed=True).get_stock_research('300750'))
    assert data['price_cny'] == 100 and data['roe_pct'] is None
    assert data['financial_issues'][0]['code'] == 'FUYAO_2003'


def test_ambiguous_name_does_not_query_arbitrary_quote():
    provider = provider_for(ambiguous=True)
    with pytest.raises(FuyaoProviderError, match='唯一匹配'):
        asyncio.run(provider.get_stock_research('宁德时代'))
    provider.get_quote.assert_not_awaited()
