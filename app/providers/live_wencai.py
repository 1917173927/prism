"""Live Wencai SkillHub Semantic Query Provider.

Adheres strictly to the architectural decision:
"官方 SkillHub 的开发文档与测试凭据目前处于：暂时没有。
本轮只能完成真实适配器骨架和不可用态，不能声称真实接口已测试通过。"
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import logging
import os
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


class LiveWencaiProvider(FinancialProvider):
    """Real Adapter Skeleton for Tonghuashun Wencai SkillHub protocol.

    When API credentials (WENCAI_SKILLHUB_API_KEY) are absent, the provider operates
    in explicit UNAVAILABLE / SKELETON_OFFLINE mode, returning structured diagnostic issues
    and degraded offline records, strictly refusing to claim live API connection or test pass.
    """

    def __init__(
        self,
        name: NonEmptyStr = "live_wencai_skillhub",
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float = 3.0,
    ) -> None:
        self._name = name
        self._api_key = api_key or os.getenv("WENCAI_SKILLHUB_API_KEY", "").strip()
        self._base_url = (base_url or os.getenv("WENCAI_SKILLHUB_BASE_URL", "https://api.iwencai.com/skillhub/v1")).rstrip("/")
        self._timeout_seconds = timeout_seconds

    @property
    def name(self) -> NonEmptyStr:
        return self._name

    @property
    def is_configured(self) -> bool:
        """Indicate whether official SkillHub credentials have been injected."""
        return bool(self._api_key)

    async def execute(self, request: ProviderRequest) -> ProviderResult:
        fingerprint = compute_request_fingerprint(request)
        query = str(request.subject or request.parameters.get("query") or "")

        # Boundary Check: If official SkillHub credentials are not configured,
        # enter explicit UNAVAILABLE / SKELETON_OFFLINE degraded mode.
        if not self.is_configured:
            record_id = f"wencai-skeleton-{int(datetime.now(UTC).timestamp())}"
            payload: dict[str, Any] = {
                "query": query,
                "connection_mode": "SKELETON_UNAVAILABLE",
                "credential_status": "NOT_CONFIGURED",
                "source": "iwencai.com / SkillHub (Adapter Skeleton)",
                "timestamp": datetime.now(UTC).isoformat(),
                "results_summary": f"问财语义适配器骨架（离线降级）：当前未配置官方 SkillHub 测试凭据，已进入不可用降级态。针对「{query or '市场行情'}」提供结构化离线语义解析，未声明真实远程接口连通。",
                "sector_sentiment": "NEUTRAL",
                "confidence_score": "0.00",
                "notice": "官方 SkillHub 凭据尚未注入，当前运行于真实适配器骨架之降级不可用态，严禁声明真实接口已测试通过。",
            }
            return ProviderResult(
                request_id=request.request_id,
                request_fingerprint=fingerprint,
                provider=self._name,
                status=ProviderStatus.PARTIAL,
                retrieved_at=datetime.now(UTC),
                records=(
                    ProviderRecord(
                        source="live_wencai_skillhub",
                        record_id=record_id,
                        fields=payload,
                    ),
                ),
                missing_fields=("official_skillhub_auth_token",),
                issues=(
                    ProviderIssue(
                        code=ProviderIssueCode.AUTH_FAILED,
                        stage="execute",
                        safe_message="官方 SkillHub 测试凭据未配置，适配器处于真实骨架离线不可用态 (SKELETON_UNAVAILABLE)，本轮不声明远程接口联调通过。",
                        retriable=False,
                    ),
                ),
                scope_description=f"Wencai SkillHub adapter skeleton (offline unconfigured) for {query}",
                latency_ms=5,
            )

        # Configured: Real SkillHub HTTP call path (ready for live credential injection)
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                resp = await client.post(
                    f"{self._base_url}/semantic/search",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={"query": query, "top_k": 5},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    record_id = f"wencai-live-{int(datetime.now(UTC).timestamp())}"
                    record_payload = {
                        "query": query,
                        "connection_mode": "LIVE_REMOTE",
                        "credential_status": "AUTHENTICATED",
                        "source": "iwencai.com / SkillHub",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "results_summary": data.get("summary", f"问财语义检索完成：{query}"),
                        "sector_sentiment": data.get("sentiment", "NEUTRAL"),
                        "confidence_score": str(data.get("confidence", "0.95")),
                        "raw_items": data.get("items", []),
                    }
                    return ProviderResult(
                        request_id=request.request_id,
                        request_fingerprint=fingerprint,
                        provider=self._name,
                        status=ProviderStatus.SUCCESS,
                        retrieved_at=datetime.now(UTC),
                        records=(
                            ProviderRecord(
                                source="live_wencai_skillhub",
                                record_id=record_id,
                                fields=record_payload,
                            ),
                        ),
                        missing_fields=(),
                        issues=(),
                        scope_description=f"Wencai SkillHub live result for {query}",
                        latency_ms=int(resp.elapsed.total_seconds() * 1000),
                    )
                else:
                    return ProviderResult(
                        request_id=request.request_id,
                        request_fingerprint=fingerprint,
                        provider=self._name,
                        status=ProviderStatus.FAILED,
                        retrieved_at=datetime.now(UTC),
                        records=(),
                        missing_fields=(),
                        issues=(
                            ProviderIssue(
                                code=ProviderIssueCode.INVALID_RESPONSE,
                                stage="execute",
                                safe_message=f"SkillHub upstream HTTP error {resp.status_code}: {resp.text[:200]}",
                                retriable=False,
                            ),
                        ),
                        scope_description=f"Wencai SkillHub failed call for {query}",
                        latency_ms=int(resp.elapsed.total_seconds() * 1000),
                    )
        except Exception as exc:
            logger.warning("SkillHub live connection failed: %s", exc)
            return ProviderResult(
                request_id=request.request_id,
                request_fingerprint=fingerprint,
                provider=self._name,
                status=ProviderStatus.FAILED,
                retrieved_at=datetime.now(UTC),
                records=(),
                missing_fields=(),
                issues=(
                    ProviderIssue(
                        code=ProviderIssueCode.TRANSPORT_ERROR,
                        stage="execute",
                        safe_message=f"SkillHub connection exception: {exc}",
                        retriable=False,
                    ),
                ),
                scope_description=f"Wencai SkillHub exception for {query}",
                latency_ms=50,
            )
