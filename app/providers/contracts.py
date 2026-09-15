"""Provider protocol contracts and four-state result invariants."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, Self

from pydantic import (
    Field,
    GetCoreSchemaHandler,
    JsonValue,
    model_validator,
)
from pydantic_core import core_schema

from app.contracts.evidence import ContractModel, NonEmptyStr


class FrozenDict(dict):
    """Immutable dictionary that deep-freezes nested mappings and collections."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raw = dict(*args, **kwargs)
        dict.__init__(self)
        for key, value in raw.items():
            dict.__setitem__(self, key, _freeze_json_value(value))

    def __setitem__(self, key: Any, value: Any) -> None:
        raise TypeError("FrozenDict is immutable")

    def __delitem__(self, key: Any) -> None:
        raise TypeError("FrozenDict is immutable")

    def clear(self) -> None:
        raise TypeError("FrozenDict is immutable")

    def update(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError("FrozenDict is immutable")

    def __ior__(self, other: Any) -> Self:
        raise TypeError("FrozenDict is immutable")

    def setdefault(self, key: Any, default: Any = None) -> Any:
        raise TypeError("FrozenDict is immutable")

    def pop(self, *args: Any, **kwargs: Any) -> Any:
        raise TypeError("FrozenDict is immutable")

    def popitem(self) -> Any:
        raise TypeError("FrozenDict is immutable")

    def __reduce__(self) -> Any:
        return (FrozenDict, (dict(self),))

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        json_value_schema = handler.generate_schema(JsonValue)
        return core_schema.no_info_after_validator_function(
            lambda v: FrozenDict(v),
            core_schema.dict_schema(
                core_schema.str_schema(),
                json_value_schema,
            ),
            serialization=core_schema.plain_serializer_function_ser_schema(
                _thaw_json_value,
                return_schema=core_schema.any_schema(),
            ),
        )


def _freeze_json_value(value: Any) -> Any:
    if isinstance(value, FrozenDict):
        return value
    if isinstance(value, Mapping):
        return FrozenDict(value)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json_value(item) for item in value)
    return value


def _thaw_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json_value(item) for item in value]
    return value


class ProviderOperation(StrEnum):
    """Supported financial data provider operations."""

    MARKET_DATA = "MARKET_DATA"
    COMPANY_DATA = "COMPANY_DATA"
    INDUSTRY_DATA = "INDUSTRY_DATA"
    MACRO_DATA = "MACRO_DATA"
    FUND_DATA = "FUND_DATA"
    CONVERTIBLE_BOND_DATA = "CONVERTIBLE_BOND_DATA"
    SEARCH_NEWS = "SEARCH_NEWS"
    SEARCH_REPORTS = "SEARCH_REPORTS"


class ProviderStatus(StrEnum):
    """Four-state provider execution status."""

    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    EMPTY = "EMPTY"
    FAILED = "FAILED"


class ProviderServingMode(StrEnum):
    """How a provider result was served to the caller.

    The four provider statuses describe the payload itself.  This orthogonal
    mode records whether that payload came from the requested provider, a
    fresh cache, a secondary provider, or a deliberately stale cache fallback.
    Keeping the dimensions separate prevents availability handling from
    silently changing the meaning of SUCCESS/PARTIAL/EMPTY/FAILED.
    """

    DIRECT = "DIRECT"
    CACHE_FRESH = "CACHE_FRESH"
    FALLBACK_PROVIDER = "FALLBACK_PROVIDER"
    CACHE_STALE_FALLBACK = "CACHE_STALE_FALLBACK"


class ProviderIssueCode(StrEnum):
    """Categorized provider issue code."""

    TIMEOUT = "TIMEOUT"
    RATE_LIMITED = "RATE_LIMITED"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    AUTH_FAILED = "AUTH_FAILED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    TRANSPORT_ERROR = "TRANSPORT_ERROR"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    UNSUPPORTED_OPERATION = "UNSUPPORTED_OPERATION"
    CANCELLED = "CANCELLED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


FORBIDDEN_PARAMETER_KEYWORDS = frozenset({
    "token",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "secret",
    "password",
    "credential",
})


def _is_forbidden_key(key: str) -> bool:
    normalized = key.strip().lower().replace("-", "_")
    return normalized in FORBIDDEN_PARAMETER_KEYWORDS or any(
        secret in normalized for secret in FORBIDDEN_PARAMETER_KEYWORDS
    )


def _find_forbidden_key(data: Any) -> str | None:
    """Recursively find any forbidden sensitive key in nested structures."""
    if isinstance(data, (dict, Mapping)):
        for k, v in data.items():
            if _is_forbidden_key(str(k)):
                return str(k)
            found = _find_forbidden_key(v)
            if found is not None:
                return found
    elif isinstance(data, (list, tuple, set, frozenset)):
        for item in data:
            found = _find_forbidden_key(item)
            if found is not None:
                return found
    return None


class ProviderRequest(ContractModel):
    """Attributable provider request parameters."""

    request_id: NonEmptyStr
    operation: ProviderOperation
    subject: NonEmptyStr
    as_of: datetime | None = None
    required_fields: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    parameters: FrozenDict = Field(default_factory=FrozenDict)
    timeout_ms: int = Field(default=3000, ge=1)

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        if self.as_of is not None and (
            self.as_of.tzinfo is None or self.as_of.utcoffset() is None
        ):
            raise ValueError("as_of must be timezone-aware when provided")

        if len(set(self.required_fields)) != len(self.required_fields):
            raise ValueError("required_fields must not contain duplicates")

        forbidden = _find_forbidden_key(self.parameters)
        if forbidden is not None:
            raise ValueError(
                f"parameters contains forbidden sensitive key: {forbidden!r}"
            )

        return self


class ProviderRecord(ContractModel):
    """One observation record from provider response."""

    source: NonEmptyStr
    record_id: NonEmptyStr | None = None
    fields: FrozenDict = Field(default_factory=FrozenDict)
    units: FrozenDict = Field(default_factory=FrozenDict)
    period: str | None = None
    observed_at: datetime | None = None
    lineage_id: str | None = None

    @model_validator(mode="after")
    def validate_record(self) -> Self:
        if self.observed_at is not None and (
            self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None
        ):
            raise ValueError("observed_at must be timezone-aware when provided")

        if not self.fields:
            raise ValueError("record fields must not be empty")

        invalid_units = [
            field_name
            for field_name, unit in self.units.items()
            if not isinstance(unit, str)
        ]
        if invalid_units:
            raise ValueError(
                "record units must be strings for fields: "
                + ", ".join(sorted(invalid_units))
            )

        return self


class ProviderIssue(ContractModel):
    """Structured, safe diagnostic issue description."""

    code: ProviderIssueCode
    stage: NonEmptyStr
    safe_message: NonEmptyStr
    retriable: bool
    retry_after_ms: int | None = Field(default=None, ge=0)
    diagnostics: FrozenDict = Field(default_factory=FrozenDict)

    @model_validator(mode="after")
    def validate_issue(self) -> Self:
        forbidden = _find_forbidden_key(self.diagnostics)
        if forbidden is not None:
            raise ValueError(
                f"diagnostics contains forbidden sensitive key: {forbidden!r}"
            )
        return self


class ProviderResult(ContractModel):
    """Attributable provider execution result respecting four-state invariants."""

    request_id: NonEmptyStr
    request_fingerprint: NonEmptyStr
    provider: NonEmptyStr
    status: ProviderStatus
    retrieved_at: datetime
    records: tuple[ProviderRecord, ...] = Field(default_factory=tuple)
    missing_fields: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    issues: tuple[ProviderIssue, ...] = Field(default_factory=tuple)
    scope_description: str | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    serving_mode: ProviderServingMode = ProviderServingMode.DIRECT
    cache_age_ms: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_status_invariants(self) -> Self:
        if self.retrieved_at.tzinfo is None or self.retrieved_at.utcoffset() is None:
            raise ValueError("retrieved_at must be timezone-aware")

        if len(set(self.missing_fields)) != len(self.missing_fields):
            raise ValueError("missing_fields must not contain duplicates")

        if self.status == ProviderStatus.SUCCESS:
            if not self.records:
                raise ValueError("SUCCESS result requires at least one record")
            if self.missing_fields:
                raise ValueError("SUCCESS result must not have missing_fields")
            if self.issues:
                raise ValueError("SUCCESS result must not contain issues")
        elif self.status == ProviderStatus.PARTIAL:
            if not self.records:
                raise ValueError("PARTIAL result requires at least one record")
            if not self.missing_fields and not self.issues:
                raise ValueError(
                    "PARTIAL result requires at least one missing field or issue"
                )
        elif self.status == ProviderStatus.EMPTY:
            if self.records:
                raise ValueError("EMPTY result must not contain records")
            if not self.scope_description or not self.scope_description.strip():
                raise ValueError(
                    "EMPTY result requires a non-empty scope_description"
                )
            if self.issues:
                raise ValueError("EMPTY result must not contain error issues")
        elif self.status == ProviderStatus.FAILED:
            if self.records:
                raise ValueError("FAILED result must not contain records")
            if not self.issues:
                raise ValueError("FAILED result requires at least one issue")

        cache_mode = self.serving_mode in (
            ProviderServingMode.CACHE_FRESH,
            ProviderServingMode.CACHE_STALE_FALLBACK,
        )
        if cache_mode and self.cache_age_ms is None:
            raise ValueError(
                f"{self.serving_mode.value} result requires cache_age_ms"
            )
        if not cache_mode and self.cache_age_ms is not None:
            raise ValueError(
                f"{self.serving_mode.value} result must not contain cache_age_ms"
            )
        if cache_mode and self.status not in (
            ProviderStatus.SUCCESS,
            ProviderStatus.PARTIAL,
        ):
            raise ValueError(
                f"{self.serving_mode.value} result requires SUCCESS or PARTIAL status"
            )

        return self


class FinancialProvider(Protocol):
    """Single asynchronous execution entrypoint for financial data providers."""

    @property
    def name(self) -> str:
        ...

    async def execute(self, request: ProviderRequest) -> ProviderResult:
        ...


def validate_result_for_request(
    request: ProviderRequest, result: ProviderResult
) -> None:
    """Validate result integrity against originating request contracts and records."""
    from app.providers.fingerprint import compute_request_fingerprint

    if result.request_id != request.request_id:
        raise ValueError(
            f"Result request_id {result.request_id!r} does not match "
            f"request {request.request_id!r}"
        )

    expected_fp = compute_request_fingerprint(request)
    if result.request_fingerprint != expected_fp:
        raise ValueError(
            f"Result fingerprint {result.request_fingerprint!r} does not match "
            f"expected fingerprint {expected_fp!r}"
        )

    if result.status == ProviderStatus.SUCCESS:
        for idx, record in enumerate(result.records):
            for req_field in request.required_fields:
                if req_field not in record.fields or record.fields[req_field] is None:
                    raise ValueError(
                        f"SUCCESS result record {idx} ({record.source}) is missing "
                        f"required field {req_field!r} (or has None value)"
                    )
    elif result.status == ProviderStatus.PARTIAL:
        requested_fields = set(request.required_fields)
        declared_missing = set(result.missing_fields)
        actual_missing = {
            req_field
            for req_field in request.required_fields
            if any(
                req_field not in record.fields or record.fields[req_field] is None
                for record in result.records
            )
        }

        phantom_fields = declared_missing - requested_fields
        if phantom_fields:
            field_list = ", ".join(sorted(phantom_fields))
            raise ValueError(
                "PARTIAL result claims missing field(s) not in "
                f"request.required_fields: {field_list}"
            )

        declared_but_present = declared_missing - actual_missing
        if declared_but_present:
            field_list = ", ".join(sorted(declared_but_present))
            raise ValueError(
                "PARTIAL result claims missing field(s) "
                f"{field_list!r} but all records contain valid values"
            )

        omitted_actual = actual_missing - declared_missing
        if omitted_actual:
            field_list = ", ".join(sorted(omitted_actual))
            raise ValueError(
                "PARTIAL result omits actual missing required field(s): "
                f"{field_list}"
            )
