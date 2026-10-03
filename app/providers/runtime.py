"""Async provider budget execution with explicit cache/fallback handling."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import logging

from app.providers.contracts import (
    FinancialProvider,
    ProviderIssue,
    ProviderIssueCode,
    ProviderRequest,
    ProviderResult,
    ProviderServingMode,
    ProviderStatus,
    validate_result_for_request,
)
from app.providers.fingerprint import (
    compute_request_fingerprint,
    redact_sensitive_data,
)
from app.providers.resilience import ProviderExecutionPolicy, is_public_cache_request

logger = logging.getLogger(__name__)


async def _execute_direct_with_budget(
    provider: FinancialProvider,
    request: ProviderRequest,
) -> ProviderResult:
    """Execute one provider call and map all boundary failures safely."""

    timeout_sec = max(request.timeout_ms / 1000.0, 0.001)
    fingerprint = compute_request_fingerprint(request)

    try:
        async with asyncio.timeout(timeout_sec):
            result = await provider.execute(request)
        validate_result_for_request(request, result)
        return result
    except TimeoutError:
        return ProviderResult(
            request_id=request.request_id,
            request_fingerprint=fingerprint,
            provider=provider.name,
            status=ProviderStatus.FAILED,
            retrieved_at=datetime.now(UTC),
            records=(),
            missing_fields=(),
            issues=(
                ProviderIssue(
                    code=ProviderIssueCode.TIMEOUT,
                    stage="budget",
                    safe_message=f"Request timed out after {request.timeout_ms}ms",
                    retriable=True,
                    diagnostics={"timeout_ms": request.timeout_ms},
                ),
            ),
            scope_description=None,
            latency_ms=request.timeout_ms,
        )
    except asyncio.CancelledError:
        # Cancellation is a control signal from the task owner or total
        # deadline. Converting it to FAILED would start a fallback request
        # after its parent task has already stopped.
        raise
    except Exception as exc:
        safe_diagnostics = redact_sensitive_data(
            {"error_type": type(exc).__name__}
        )
        return ProviderResult(
            request_id=request.request_id,
            request_fingerprint=fingerprint,
            provider=provider.name,
            status=ProviderStatus.FAILED,
            retrieved_at=datetime.now(UTC),
            records=(),
            missing_fields=(),
            issues=(
                ProviderIssue(
                    code=ProviderIssueCode.INTERNAL_ERROR,
                    stage="runtime",
                    safe_message="Internal provider execution error",
                    retriable=False,
                    diagnostics=safe_diagnostics,
                ),
            ),
            scope_description=None,
        )


def _request_with_timeout(request: ProviderRequest, timeout_ms: int) -> ProviderRequest:
    payload = request.model_dump(mode="python")
    payload["timeout_ms"] = max(1, timeout_ms)
    return ProviderRequest.model_validate(payload)


def _identity_failure(
    provider: FinancialProvider,
    request: ProviderRequest,
) -> ProviderResult:
    """Map a provider identity drift to a safe FAILED result."""

    return ProviderResult(
        request_id=request.request_id,
        request_fingerprint=compute_request_fingerprint(request),
        provider=provider.name,
        status=ProviderStatus.FAILED,
        retrieved_at=datetime.now(UTC),
        records=(),
        missing_fields=(),
        issues=(
            ProviderIssue(
                code=ProviderIssueCode.INVALID_RESPONSE,
                stage="identity",
                safe_message="Provider response identity did not match the requested boundary",
                retriable=False,
            ),
        ),
        scope_description=None,
    )


def _rebind_serving_mode(
    result: ProviderResult,
    *,
    mode: ProviderServingMode,
    cache_age_ms: int | None = None,
    request_id: str | None = None,
) -> ProviderResult:
    payload = result.model_dump(mode="python")
    payload["serving_mode"] = mode
    payload["cache_age_ms"] = cache_age_ms
    if request_id is not None:
        payload["request_id"] = request_id
    return ProviderResult.model_validate(payload)


async def _execute_with_policy(
    provider: FinancialProvider,
    request: ProviderRequest,
    policy: ProviderExecutionPolicy,
) -> ProviderResult:
    """Execute primary/fallback providers within one total request budget."""

    counters = policy.counters()
    cache = policy.cache
    public_request = is_public_cache_request(request)

    if cache is not None:
        if not public_request:
            counters.increment("private_bypasses")
        else:
            try:
                hit = cache.get(provider.name, request, allow_stale=False)
            except Exception:
                logger.warning("provider cache lookup failed; bypassing cache")
                hit = None
            if hit is not None:
                counters.increment("cache_fresh")
                return _rebind_serving_mode(
                    hit.result,
                    mode=ProviderServingMode.CACHE_FRESH,
                    cache_age_ms=hit.age_ms,
                    request_id=request.request_id,
                )

    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(request.timeout_ms, 1) / 1000.0
    counters.increment("primary_calls")
    primary_result = await _execute_direct_with_budget(provider, request)
    if (
        primary_result.provider != provider.name
        or primary_result.serving_mode != ProviderServingMode.DIRECT
        or primary_result.cache_age_ms is not None
    ):
        primary_result = _identity_failure(provider, request)

    if primary_result.status in (ProviderStatus.SUCCESS, ProviderStatus.PARTIAL):
        if cache is not None:
            try:
                cache.put(provider.name, request, primary_result)
            except Exception:
                # A cache adapter must never turn a valid upstream response
                # into an execution failure. The next request simply misses.
                logger.warning("provider cache write failed; returning direct result")
        return _rebind_serving_mode(
            primary_result,
            mode=ProviderServingMode.DIRECT,
            cache_age_ms=None,
        )

    # EMPTY is a genuine provider answer. It is deliberately not masked by a
    # secondary source and is never written to cache.
    if primary_result.status == ProviderStatus.EMPTY:
        return primary_result

    fallback = policy.fallback
    if fallback is not None and fallback.name != provider.name:
        remaining_ms = int((deadline - loop.time()) * 1000)
        if remaining_ms > 0:
            counters.increment("fallback_calls")
            fallback_request = _request_with_timeout(
                request,
                min(request.timeout_ms, remaining_ms),
            )
            fallback_result = await _execute_direct_with_budget(
                fallback,
                fallback_request,
            )
            if (
                fallback_result.provider != fallback.name
                or fallback_result.serving_mode != ProviderServingMode.DIRECT
                or fallback_result.cache_age_ms is not None
            ):
                fallback_result = _identity_failure(fallback, fallback_request)
            if fallback_result.status != ProviderStatus.FAILED:
                counters.increment("fallback_results")
                return _rebind_serving_mode(
                    fallback_result,
                    mode=ProviderServingMode.FALLBACK_PROVIDER,
                    cache_age_ms=None,
                )

    if cache is not None and public_request and policy.allow_stale:
        try:
            stale_hit = cache.get(provider.name, request, allow_stale=True)
        except Exception:
            logger.warning("provider stale-cache lookup failed")
            stale_hit = None
        if stale_hit is not None:
            mode = (
                ProviderServingMode.CACHE_STALE_FALLBACK
                if stale_hit.stale
                else ProviderServingMode.CACHE_FRESH
            )
            if stale_hit.stale:
                counters.increment("stale_fallbacks")
            else:
                counters.increment("cache_fresh")
            return _rebind_serving_mode(
                stale_hit.result,
                mode=mode,
                cache_age_ms=stale_hit.age_ms,
                request_id=request.request_id,
            )

    counters.increment("failed_results")
    return primary_result


async def execute_with_budget(
    provider: FinancialProvider,
    request: ProviderRequest,
    *,
    policy: ProviderExecutionPolicy | None = None,
) -> ProviderResult:
    """Execute a provider request within its budget.

    With no policy this is the direct timeout/error boundary used by all
    existing callers. A policy adds an optional public-result cache and one
    explicitly marked fallback while preserving the total request budget.
    """

    if policy is None:
        return await _execute_direct_with_budget(provider, request)
    return await _execute_with_policy(provider, request, policy)


async def execute_with_resilience(
    provider: FinancialProvider,
    request: ProviderRequest,
    policy: ProviderExecutionPolicy,
) -> ProviderResult:
    """Named alias for callers that want policy use to be explicit."""

    return await execute_with_budget(provider, request, policy=policy)


__all__ = ["execute_with_budget", "execute_with_resilience"]
