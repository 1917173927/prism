"""Fixture Wencai Provider for offline demo and testing environments.

Operates in MOCK mode with deterministic responses and explicit synthetic attribution.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.contracts.evidence import NonEmptyStr
from app.providers.contracts import (
    FinancialProvider,
    ProviderOperation,
    ProviderRecord,
    ProviderRequest,
    ProviderResult,
    ProviderServingMode,
    ProviderStatus,
)
from app.providers.fingerprint import compute_request_fingerprint

FIXTURE_WENCAI_DATABASE: dict[str, dict[str, Any]] = {
    "default": {
        "summary": "【模拟测试】全市场宏观流动性充裕，科技与高端制造板块交易活跃度处于历史中位数偏上水平。",
        "sentiment": "NEUTRAL",
        "confidence": "0.95",
        "items": [
            {"topic": "硬科技与半导体", "trend": "震荡向上", "sample_security": "688256.SH"},
            {"topic": "新能源与动力电池", "trend": "估值修复", "sample_security": "300750.SZ"},
            {"topic": "大消费与食品饮料", "trend": "分红稳健", "sample_security": "600519.SH"},
        ],
    },
    "半导体": {
        "summary": "【模拟测试】半导体产业链受先进制程与自主可控预期催化，估值分位数回升至近三年45%分位。",
        "sentiment": "BULLISH",
        "confidence": "0.92",
        "items": [
            {"topic": "AI芯片", "trend": "资金净流入", "sample_security": "688256.SH"},
            {"topic": "晶圆制造", "trend": "产能利用率回升", "sample_security": "688981.SH"},
        ],
    },
}


class FixtureWencaiProvider(FinancialProvider):
    """Fixture provider delivering synthetic Wencai semantic search observations."""

    def __init__(self, name: NonEmptyStr = "fixture_wencai_provider") -> None:
        self._name = name

    @property
    def name(self) -> NonEmptyStr:
        return self._name

    @property
    def is_synthetic(self) -> bool:
        return True

    async def execute(self, request: ProviderRequest) -> ProviderResult:
        fingerprint = compute_request_fingerprint(request)
        query = str(request.subject or request.parameters.get("query") or "")

        matched_data = FIXTURE_WENCAI_DATABASE.get("default")
        for k, v in FIXTURE_WENCAI_DATABASE.items():
            if k != "default" and k in query:
                matched_data = v
                break

        record_id = f"fixture-wencai-{int(datetime.now(UTC).timestamp())}"
        payload = {
            "query": query,
            "source": "iwencai.com / Fixture Sandbox (Mock Synthetic)",
            "retrieved_at": datetime.now(UTC).isoformat(),
            "summary": matched_data["summary"],
            "sentiment": matched_data["sentiment"],
            "confidence": matched_data["confidence"],
            "items": matched_data["items"],
            "is_synthetic": True,
        }

        records = (
            ProviderRecord(
                source=self._name,
                record_id=record_id,
                fields=payload,
            ),
        )

        return ProviderResult(
            request_id=request.request_id,
            request_fingerprint=fingerprint,
            provider=self._name,
            status=ProviderStatus.SUCCESS,
            serving_mode=ProviderServingMode.DIRECT,
            retrieved_at=datetime.now(UTC),
            records=records,
            missing_fields=(),
            issues=(),
            scope_description=f"Fixture Wencai synthetic result for {query}",
            latency_ms=2,
        )
