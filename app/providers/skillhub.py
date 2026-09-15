"""Official Wencai SkillHub financial provider adapter.

Adheres strictly to the architectural requirements:
- Loads the official Skill routes from a manifest shipped with the project.
- Accepts server-side environment or OS-protected project configuration.
- Zero client-side leakage of credentials.
- Zero financial math or exposure calculation inside provider.
- Strict 4-state mapping (SUCCESS, PARTIAL, EMPTY, FAILED).
- Never falls back to mock/synthetic data when live requests fail.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import json
import logging
import os
from pathlib import Path
import secrets
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

_MANIFEST_PATH = Path(__file__).with_name("iwencai_skills.json")


def load_iwencai_skill_manifest() -> dict[str, Any]:
    """Load the versioned SkillHub contract bundled in the installed package."""
    document = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    if document.get("schema_version") != "prism-iwencai-skills.v1":
        raise ValueError("unsupported Wencai skill manifest")
    skills = document.get("skills")
    if not isinstance(skills, list) or len(skills) != 9:
        raise ValueError("Wencai skill manifest must contain nine skills")
    return document


class WencaiSkillHubProvider(FinancialProvider):
    """Official adapter for Tonghuashun Wencai SkillHub enterprise API."""

    def __init__(
        self,
        name: NonEmptyStr = "wencai_skillhub_provider",
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float = 8.0,
    ) -> None:
        manifest = load_iwencai_skill_manifest()
        self._name = name
        self._api_key = (
            api_key
            or os.getenv("WENCAI_SKILLHUB_API_KEY", "").strip()
            or os.getenv("IWENCAI_API_KEY", "").strip()
        )
        self._base_url = (
            base_url
            or os.getenv("WENCAI_SKILLHUB_BASE_URL", "").strip()
            or os.getenv("IWENCAI_BASE_URL", "").strip()
            or str(manifest["base_url"])
        ).rstrip("/")
        self._timeout_seconds = min(max(timeout_seconds, 0.001), 30.0)
        self._skills = tuple(manifest["skills"])

    @property
    def name(self) -> NonEmptyStr:
        return self._name

    @property
    def is_configured(self) -> bool:
        """Check whether official SkillHub API credentials are configured."""
        return bool(self._api_key)

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def installed_skills(self) -> tuple[dict[str, Any], ...]:
        """Return non-secret project-bundled Skill metadata."""
        return tuple(dict(skill) for skill in self._skills)

    def configure(self, *, api_key: str, base_url: str | None = None) -> None:
        """Rotate the in-process credential after protected settings are saved."""
        self._api_key = api_key.strip()
        if base_url:
            self._base_url = base_url.strip().rstrip("/")

    def _skill_for(self, request: ProviderRequest) -> dict[str, Any]:
        channel = str(request.parameters.get("channel", "announcement")).lower()
        for skill in self._skills:
            if skill["operation"] != request.operation.value:
                continue
            if request.operation == ProviderOperation.SEARCH_NEWS:
                if skill.get("channel") == channel:
                    return skill
                continue
            return skill
        raise ValueError(
            f"unsupported Wencai route: {request.operation.value}/{channel}"
        )

    async def probe_installed_skills(self) -> tuple[dict[str, Any], ...]:
        """Run one bounded real request through every bundled Skill contract."""
        query_by_skill = {
            "announcement-search": "贵州茅台最新公告",
            "news-search": "贵州茅台最新新闻",
            "report-search": "贵州茅台最新研报",
            "hithink-market-query": "贵州茅台最新价",
            "hithink-finance-query": "贵州茅台2025年营业收入",
            "hithink-industry-query": "白酒行业市盈率",
            "hithink-macro-query": "中国最新CPI同比",
            "hithink-fund-query": "沪深300ETF最新净值",
            "hithink-cb-selector": "可转债价格低于130元",
        }

        async def probe(skill: dict[str, Any]) -> dict[str, Any]:
            parameters: dict[str, Any] = {"limit": 1}
            if skill.get("channel"):
                parameters["channel"] = skill["channel"]
            result = await self.execute(ProviderRequest(
                request_id=f"wencai-probe-{secrets.token_hex(8)}",
                operation=ProviderOperation(skill["operation"]),
                subject=query_by_skill[skill["skill_id"]],
                parameters=parameters,
            ))
            fields = dict(result.records[0].fields) if result.records else {}
            items = fields.get("items")
            item_count = (
                sum(1 for item in items if isinstance(item, dict) and item)
                if isinstance(items, (list, tuple))
                else 0
            )
            return {
                "name": skill["name"],
                "skill_id": skill["skill_id"],
                "status": result.status.value,
                "record_count": len(result.records),
                "item_count": item_count,
                "error_code": result.issues[0].code.value if result.issues else None,
            }

        return tuple(await asyncio.gather(*(probe(skill) for skill in self._skills)))

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
        try:
            result_limit = int(request.parameters.get("limit", 10))
        except (TypeError, ValueError):
            result_limit = 10
        try:
            skill = self._skill_for(request)
        except ValueError as exc:
            return ProviderResult(
                request_id=request.request_id,
                request_fingerprint=fingerprint,
                provider=self._name,
                status=ProviderStatus.FAILED,
                serving_mode=ProviderServingMode.DIRECT,
                retrieved_at=start_time,
                records=(),
                missing_fields=(),
                issues=(ProviderIssue(
                    code=ProviderIssueCode.INVALID_RESPONSE,
                    stage="route",
                    safe_message=str(exc),
                    retriable=False,
                ),),
                scope_description=f"Unsupported SkillHub route for {request.subject}",
                latency_ms=1,
            )
        is_comprehensive_search = skill["endpoint"] == "/v1/comprehensive/search"
        endpoint = f"{self._base_url}{skill['endpoint']}"
        if is_comprehensive_search:
            payload = {
                "query": query,
                "channels": [skill["channel"]],
                "app_id": "AIME_SKILL",
                "size": min(max(result_limit, 1), 100),
            }
        else:
            payload = {
                "query": query,
                "page": str(request.parameters.get("page", "1")),
                "limit": str(request.parameters.get("limit", "10")),
                "is_cache": str(request.parameters.get("is_cache", "1")),
                "expand_index": str(request.parameters.get("expand_index", "true")).lower(),
            }

        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                headers = {
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "X-Request-ID": request.request_id,
                    "X-Claw-Call-Type": "normal",
                    "X-Claw-Skill-Id": skill["skill_id"],
                    "X-Claw-Skill-Version": skill["version"],
                    "X-Claw-Plugin-Id": "none",
                    "X-Claw-Plugin-Version": "none",
                    "X-Claw-Trace-Id": secrets.token_hex(32),
                }
                resp = await client.post(
                    endpoint,
                    headers=headers,
                    json=payload,
                )
                latency_ms = max(1, int((datetime.now(UTC) - start_time).total_seconds() * 1000))

                if resp.status_code == 200:
                    data = resp.json()
                    if not isinstance(data, dict):
                        return ProviderResult(
                            request_id=request.request_id,
                            request_fingerprint=fingerprint,
                            provider=self._name,
                            status=ProviderStatus.FAILED,
                            serving_mode=ProviderServingMode.DIRECT,
                            retrieved_at=datetime.now(UTC),
                            records=(),
                            missing_fields=(),
                            issues=(ProviderIssue(
                                code=ProviderIssueCode.INVALID_RESPONSE,
                                stage="execute",
                                safe_message="Wencai returned a non-object JSON response.",
                                retriable=False,
                            ),),
                            scope_description=f"Wencai invalid response for {query}",
                            latency_ms=latency_ms,
                        )
                    invalid_status = data.get("status_code") != 0
                    if invalid_status:
                        return ProviderResult(
                            request_id=request.request_id,
                            request_fingerprint=fingerprint,
                            provider=self._name,
                            status=ProviderStatus.FAILED,
                            serving_mode=ProviderServingMode.DIRECT,
                            retrieved_at=datetime.now(UTC),
                            records=(),
                            missing_fields=(),
                            issues=(ProviderIssue(
                                code=ProviderIssueCode.INVALID_RESPONSE,
                                stage="execute",
                                safe_message=f"Wencai query rejected: {data.get('status_msg', 'unknown error')}",
                                retriable=False,
                            ),),
                            scope_description=f"Wencai query rejected for {query}",
                            latency_ms=latency_ms,
                        )

                    raw_items = data.get("data") if is_comprehensive_search else data.get("datas")
                    raw_items = raw_items or data.get("items") or []
                    upstream_summary = data.get("summary")
                    if not raw_items and not upstream_summary:
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
                        "summary": upstream_summary or f"问财查询完成：{query}",
                        "sentiment": data.get("sentiment", "NEUTRAL"),
                        "confidence": str(data.get("confidence", "1.0")),
                        "items": raw_items,
                        "columns": data.get("columns", []),
                        "row_count": data.get("row_count", len(raw_items)),
                        "code_count": data.get("code_count", len(raw_items)),
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
                    # The upstream sends a plain-text daily-quota notice with
                    # HTTP 401 and application/json. Do not mislabel it as a bad key.
                    exhausted = "今天的次数已用完" in resp.text or "今日额度已用完" in resp.text
                    issue_code = (
                        ProviderIssueCode.QUOTA_EXHAUSTED if exhausted else (
                            ProviderIssueCode.AUTH_FAILED if resp.status_code == 401
                            else ProviderIssueCode.PERMISSION_DENIED
                        )
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
                                safe_message=("问财当日查询额度已耗尽。请在 https://www.iwencai.com/skillhub 查看剩余额度，等待额度重置或按需升级权益；无需重新填写 Key。"
                                              if exhausted else f"Official SkillHub authentication error HTTP {resp.status_code}."),
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
