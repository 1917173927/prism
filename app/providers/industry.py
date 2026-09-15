"""Bounded automatic industry metadata from Eastmoney's public stock profile.

Uses the company profile's EM2016 classification, matched by full SECUCODE.
Metadata retrieval time is not a quote timestamp.
"""
from datetime import UTC, datetime
from time import monotonic
import re

import httpx

from app.providers.wencai_normalization import canonical_sector_from_wencai


class EastmoneyIndustryProvider:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self.transport = transport
        self._cache: dict[str, tuple[float, dict]] = {}

    async def get_industry(self, asset_id: str) -> dict | None:
        match = re.fullmatch(r"(\d{6})\.(SH|SZ|BJ)", asset_id)
        if not match:
            return None
        cached = self._cache.get(asset_id)
        if cached and monotonic() - cached[0] < 1800:
            return dict(cached[1])
        try:
            async with httpx.AsyncClient(timeout=2, transport=self.transport) as client:
                response = await client.get("https://datacenter.eastmoney.com/securities/api/data/v1/get", params={
                    "reportName": "RPT_F10_BASIC_ORGINFO",
                    "columns": "SECUCODE,SECURITY_NAME_ABBR,EM2016",
                    "filter": f'(SECUCODE="{asset_id}")',
                    "pageNumber": 1, "pageSize": 1, "source": "HSF10", "client": "PC",
                })
                response.raise_for_status()
                payload = response.json()
            rows = (payload.get("result") or {}).get("data")
            if payload.get("success") is not True or payload.get("code") != 0 or not isinstance(rows, list) or len(rows) != 1:
                return None
            row = rows[0]
            if not isinstance(row, dict) or row.get("SECUCODE") != asset_id:
                return None
            industry = row.get("EM2016")
            if not isinstance(industry, str):
                return None
            sector = canonical_sector_from_wencai(industry)
            if sector is None:
                return None
            result = {"asset_id": asset_id, "industry": industry, "sector": sector,
                      "name": row.get("SECURITY_NAME_ABBR"), "source": "Eastmoney public stock industry",
                      "retrieved_at": datetime.now(UTC).isoformat()}
            if len(self._cache) >= 2048:
                self._cache.clear()
            self._cache[asset_id] = (monotonic(), result)
            return dict(result)
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            return None
