"""Official Wencai SkillHub Financial Provider Adapter.

Adheres strictly to the architectural requirements:
- Reads configuration solely from server-side environment (WENCAI_SKILLHUB_API_KEY, WENCAI_SKILLHUB_BASE_URL).
- Zero client-side leakage of credentials.
- Zero financial math or exposure calculation inside provider.
- Strict 4-state mapping (SUCCESS, PARTIAL, EMPTY, FAILED).
- Never falls back to mock/synthetic data when live requests fail.
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
    ProviderServingMode,
    ProviderStatus,
)
from app.providers.fingerprint import compute_request_fingerprint

logger = logging.getLogger(__name__)


class WencaiSkillHubProvider(FinancialProvider):
    """Official adapter for Tonghuashun Wencai SkillHub enterprise API."""

    def __init__(
        self,
        name: NonEmptyStr = "wencai_skillhub_provider",
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float = 3.0,
    ) -> None:
        self._name = name
        self._api_key = api_key or os.getenv("WENCAI_SKILLHUB_API_KEY", "").strip()
        self._base_url = (
            base_url or os.getenv("WENCAI_SKILLHUB_BASE_URL", "https://api.iwencai.com/skillhub/v1")
        ).rstrip("/")
        self._timeout_seconds = timeout_seconds

    @property
    def name(self) -> NonEmptyStr:
        return self._name

    @property
    def is_configured(self) -> bool:
        """Check whether official SkillHub API credentials are configured."""
        return bool(self._api_key)

    async def execute(self, request: ProviderRequest) -> ProviderResult:
        """Execute request against official SkillHub endpoint.

        Returns 4-state ProviderResult without silent fallback to mock.
        """
        fingerprint = compute_request_fingerprint(request)
        start_time = datetime.now(UTC)

        # Hard Gate: If credentials are not configured, reject with explicit AUTH_FAILED.
        if not self.is_configured:
            return ProviderResult(
                request_id=request.request_id,
                request_fingerprint=fingerprint,
                provider=self._name,
                status=ProviderStatus.FAILED,
                serving_mode=ProviderServingMode.DIRECT,
                retrieved_at=start_time,
                records=(),
                missing_fields=("WENCAI_SKILLHUB_API_KEY",),
                issues=(
                    ProviderIssue(
                        code=ProviderIssueCode.AUTH_FAILED,
                        stage="execute",
                        safe_message="Official SkillHub API key (WENCAI_SKILLHUB_API_KEY) is unconfigured. "
                                     "Live mode execution refused.",
                        retriable=False,
                    ),
                ),
                scope_description=f"SkillHub live execution for {request.subject}",
                latency_ms=1,
            )

        query = str(request.subject or request.parameters.get("query") or "")
        endpoint = f"{self._base_url}/semantic/search"

        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                resp = await client.post(
                    endpoint,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                        "X-Request-ID": request.request_id,
                    },
                    json={
                        "query": query,
                        "operation": request.operation.value,
                        "parameters": dict(request.parameters),
                    },
                )
                latency_ms = max(1, int((datetime.now(UTC) - start_time).total_seconds() * 1000))

                if resp.status_code == 200:
                    data = resp.json()
                    raw_items = data.get("items") or []
                    if not raw_items and not data.get("summary"):
                        return ProviderResult(
                            request_id=request.request_id,
                            request_fingerprint=fingerprint,
                            provider=self._name,
                            status=ProviderStatus.EMPTY,
                            serving_mode=ProviderServingMode.DIRECT,
                            retrieved_at=datetime.now(UTC),
                            records=(),
                            missing_fields=(),
                            issues=(),
                            scope_description=f"SkillHub query yielded empty results for {query}",
                            latency_ms=latency_ms,
                        )

                    records: list[ProviderRecord] = []
                    record_id = f"skillhub-{int(datetime.now(UTC).timestamp())}"
                    record_payload = {
                        "query": query,
                        "source": "iwencai.com / SkillHub (Official Live)",
                        "retrieved_at": datetime.now(UTC).isoformat(),
                        "summary": data.get("summary", ""),
                        "sentiment": data.get("sentiment", "NEUTRAL"),
                        "confidence": str(data.get("confidence", "1.0")),
                        "items": raw_items,
                    }
                    records.append(
                        ProviderRecord(
                            source=self._name,
                            record_id=record_id,
                            fields=record_payload,
                        )
                    )

                    # Check required fields
                    missing_required = tuple(
                        field for field in request.required_fields if field not in record_payload
                    )
                    status = (
                        ProviderStatus.PARTIAL if missing_required else ProviderStatus.SUCCESS
                    )

                    return ProviderResult(
                        request_id=request.request_id,
                        request_fingerprint=fingerprint,
                        provider=self._name,
                        status=status,
                        serving_mode=ProviderServingMode.DIRECT,
                        retrieved_at=datetime.now(UTC),
                        records=tuple(records),
                        missing_fields=missing_required,
                        issues=(),
                        scope_description=f"SkillHub live execution for {query}",
                        latency_ms=latency_ms,
                    )

                if resp.status_code in (401, 403):
                    issue_code = (
                        ProviderIssueCode.AUTH_FAILED
                        if resp.status_code == 401
                        else ProviderIssueCode.PERMISSION_DENIED
                    )
                    return ProviderResult(
                        request_id=request.request_id,
                        request_fingerprint=fingerprint,
                        provider=self._name,
                        status=ProviderStatus.FAILED,
                        serving_mode=ProviderServingMode.DIRECT,
                        retrieved_at=datetime.now(UTC),
                        records=(),
                        missing_fields=(),
                        issues=(
                            ProviderIssue(
                                code=issue_code,
                                stage="execute",
                                safe_message=f"Official SkillHub authentication error HTTP {resp.status_code}.",
                                retriable=False,
                            ),
                        ),
                        scope_description=f"SkillHub authentication failure for {query}",
                        latency_ms=latency_ms,
                    )

                if resp.status_code == 429:
                    return ProviderResult(
                        request_id=request.request_id,
                        request_fingerprint=fingerprint,
                        provider=self._name,
                        status=ProviderStatus.FAILED,
                        serving_mode=ProviderServingMode.DIRECT,
                        retrieved_at=datetime.now(UTC),
                        records=(),
                        missing_fields=(),
                        issues=(
                            ProviderIssue(
                                code=ProviderIssueCode.RATE_LIMITED,
                                stage="execute",
                                safe_message="Official SkillHub rate limit reached (HTTP 429).",
                                retriable=True,
                            ),
                        ),
                        scope_description=f"SkillHub rate limited for {query}",
                        latency_ms=latency_ms,
                    )

                # Other HTTP non-200
                return ProviderResult(
                    request_id=request.request_id,
                    request_fingerprint=fingerprint,
                    provider=self._name,
                    status=ProviderStatus.FAILED,
                    serving_mode=ProviderServingMode.DIRECT,
                    retrieved_at=datetime.now(UTC),
                    records=(),
                    missing_fields=(),
                    issues=(
                        ProviderIssue(
                            code=ProviderIssueCode.INVALID_RESPONSE,
                            stage="execute",
                            safe_message=f"Official SkillHub server error HTTP {resp.status_code}.",
                            retriable=resp.status_code >= 500,
                        ),
                    ),
                    scope_description=f"SkillHub upstream error for {query}",
                    latency_ms=latency_ms,
                )

        except httpx.TimeoutException:
            latency_ms = max(1, int((datetime.now(UTC) - start_time).total_seconds() * 1000))
            return ProviderResult(
                request_id=request.request_id,
                request_fingerprint=fingerprint,
                provider=self._name,
                status=ProviderStatus.FAILED,
                serving_mode=ProviderServingMode.DIRECT,
                retrieved_at=datetime.now(UTC),
                records=(),
                missing_fields=(),
                issues=(
                    ProviderIssue(
                        code=ProviderIssueCode.TIMEOUT,
                        stage="execute",
                        safe_message=f"Official SkillHub request timed out after {self._timeout_seconds}s.",
                        retriable=True,
                    ),
                ),
                scope_description=f"SkillHub timeout for {query}",
                latency_ms=latency_ms,
            )

        except Exception as exc:
            latency_ms = max(1, int((datetime.now(UTC) - start_time).total_seconds() * 1000))
            logger.warning("SkillHub transport error: %s", exc)
            return ProviderResult(
                request_id=request.request_id,
                request_fingerprint=fingerprint,
                provider=self._name,
                status=ProviderStatus.FAILED,
                serving_mode=ProviderServingMode.DIRECT,
                retrieved_at=datetime.now(UTC),
                records=(),
                missing_fields=(),
                issues=(
                    ProviderIssue(
                        code=ProviderIssueCode.TRANSPORT_ERROR,
                        stage="execute",
                        safe_message=f"SkillHub transport exception: {type(exc).__name__}",
                        retriable=True,
                    ),
                ),
                scope_description=f"SkillHub transport failure for {query}",
                latency_ms=latency_ms,
            )
