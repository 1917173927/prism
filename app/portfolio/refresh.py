"""Owner-scoped portfolio market-data refresh contracts and execution."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal, Protocol, Self

from pydantic import Field, model_validator

from app.contracts.evidence import ContractModel, NonEmptyStr
from app.portfolio.contracts import (
    AssetType,
    FundHoldingSnapshot,
    LookThroughHolding,
    PortfolioImportBundle,
    Position,
    PositionSnapshot,
)
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
from app.providers.wencai_normalization import (
    decode_stock_identity,
    decode_stock_quote_fields,
    source_industry_label,
)


class StructuredFinanceProvider(Protocol):
    async def get_quote(self, code: str) -> dict[str, Any] | None: ...

    async def get_fund_lookthrough(self, code: str) -> dict[str, Any] | None: ...


class LivePortfolioProviderAdapter:
    """Normalize real Fuyao data and optionally fall back to real SkillHub data."""

    name = "live_portfolio_sources"

    def __init__(
        self,
        finance_provider: StructuredFinanceProvider,
        *,
        wencai_provider: FinancialProvider | None = None,
        stock_quote_available: bool = False,
        fund_lookthrough_available: bool = False,
        wencai_available: bool = False,
        industry_provider=None,
    ) -> None:
        self._finance_provider = finance_provider
        self._wencai_provider = wencai_provider
        self._stock_quote_available = stock_quote_available
        self._fund_lookthrough_available = fund_lookthrough_available
        self._wencai_available = wencai_available
        self._industry_provider = industry_provider
        self.industry_metadata: dict[str, dict] = {}
        self.wencai_failure_codes: set[str] = set()
        self.wencai_metadata_succeeded = False
        self._prefetched_quotes: dict[str, dict[str, Any] | None] = {}

    async def prefetch_quotes(self, asset_ids: list[str]) -> None:
        """Use a provider batch endpoint when available to avoid rate bursts."""
        self._prefetched_quotes = {}
        getter = getattr(self._finance_provider, "get_quotes", None)
        if not callable(getter) or not asset_ids:
            return
        requested = tuple(dict.fromkeys(str(asset_id).strip().upper() for asset_id in asset_ids))
        try:
            result = await getter(requested)
        except Exception:
            # A batch timeout is not evidence that every symbol is missing.
            # Clear the cache so _execute_fuyao can perform its bounded,
            # independently validated per-symbol request below.
            self._prefetched_quotes = {}
            return
        if isinstance(result, dict):
            prefetched: dict[str, dict[str, Any] | None] = {}
            for asset_id, quote in result.items():
                if quote is None or isinstance(quote, dict):
                    prefetched[str(asset_id).strip().upper()] = quote
                    if isinstance(quote, dict) and quote.get("symbol"):
                        prefetched[str(quote["symbol"]).strip().upper()] = quote
            # A batch response is authoritative for every requested key.  A
            # missing row is a reviewable missing quote, not permission to
            # silently fan out into old per-position calls.
            self._prefetched_quotes = {}
            for asset_id in requested:
                alias = next(
                    (key for key in prefetched if key.startswith(f"{asset_id}.")),
                    None,
                )
                self._prefetched_quotes[asset_id] = prefetched.get(
                    asset_id if asset_id in prefetched else alias
                )
            self._prefetched_quotes.update(prefetched)

    @staticmethod
    def _confirmed_sector(request: ProviderRequest) -> str | None:
        """Return only an explicitly user-confirmed sector for this position.

        A failed industry enrichment must not turn a confirmed portfolio row
        into a fabricated classification.  The persisted OCR/import flow
        records the user's confirmation in ``source``; rows without that
        provenance remain fail-closed and still require live metadata.
        """
        sector = str(request.parameters.get("existing_sector") or "").strip()
        source = str(request.parameters.get("existing_sector_source") or "").casefold()
        if not sector or "user-confirmed" not in source:
            return None
        if sector.casefold() in {"unknown", "unclassified"}:
            return None
        return sector

    @staticmethod
    def _failed(request: ProviderRequest, error: BaseException) -> ProviderResult:
        return ProviderResult(
            request_id=request.request_id,
            request_fingerprint=compute_request_fingerprint(request),
            provider="fuyao_finance_api",
            status=ProviderStatus.FAILED,
            retrieved_at=datetime.now(UTC),
            serving_mode=ProviderServingMode.DIRECT,
            issues=(ProviderIssue(
                code=ProviderIssueCode.TRANSPORT_ERROR,
                stage="portfolio_refresh",
                safe_message=f"real portfolio data provider failed: {type(error).__name__}",
                retriable=True,
            ),),
        )

    @staticmethod
    def _empty(request: ProviderRequest, provider: str) -> ProviderResult:
        return ProviderResult(
            request_id=request.request_id,
            request_fingerprint=compute_request_fingerprint(request),
            provider=provider,
            status=ProviderStatus.EMPTY,
            retrieved_at=datetime.now(UTC),
            serving_mode=ProviderServingMode.DIRECT,
            scope_description=f"No live portfolio data was returned for {request.parameters.get('asset_id', request.subject)}",
        )

    @staticmethod
    def _result(
        request: ProviderRequest,
        fields: dict[str, object],
        *,
        source: str,
        missing_fields: tuple[str, ...] = (),
        issues: tuple[ProviderIssue, ...] = (),
    ) -> ProviderResult:
        return ProviderResult(
            request_id=request.request_id,
            request_fingerprint=compute_request_fingerprint(request),
            provider="fuyao_finance_api",
            status=ProviderStatus.PARTIAL if missing_fields or issues else ProviderStatus.SUCCESS,
            retrieved_at=datetime.now(UTC),
            serving_mode=ProviderServingMode.DIRECT,
            records=(ProviderRecord(source=source, fields=fields),),
            missing_fields=missing_fields,
            issues=issues,
        )

    async def _query_industry(
        self,
        asset_id: str,
        *,
        request_id: str,
        as_of: datetime | None,
        timeout_ms: int,
        stage: str,
    ) -> tuple[str | None, str | None, str | None, tuple[ProviderIssue, ...], bool]:
        """Fetch and decode one real industry row without binding another asset."""
        if self._industry_provider is not None:
            metadata = await self._industry_provider.get_industry(asset_id)
            if metadata:
                self.industry_metadata[asset_id] = metadata
                return metadata["sector"], metadata.get("name"), metadata["source"], (), False
        if not self._wencai_available or self._wencai_provider is None:
            return None, None, None, (), False
        enrichment_request = ProviderRequest(
            request_id=request_id,
            operation=ProviderOperation.INDUSTRY_DATA,
            subject=f"{asset_id} 所属同花顺行业 股票简称",
            as_of=as_of,
            parameters={"asset_id": asset_id},
            timeout_ms=timeout_ms,
        )
        try:
            enrichment = await self._wencai_provider.execute(enrichment_request)
        except Exception as exc:
            self.wencai_failure_codes.add(ProviderIssueCode.TRANSPORT_ERROR.value)
            return (
                None,
                None,
                None,
                (ProviderIssue(
                    code=ProviderIssueCode.TRANSPORT_ERROR,
                    stage=stage,
                    safe_message=f"Wencai industry enrichment failed: {type(exc).__name__}",
                    retriable=True,
                ),),
                False,
            )

        if enrichment.status == ProviderStatus.FAILED:
            failure_code = (
                enrichment.issues[0].code
                if enrichment.issues
                else ProviderIssueCode.INVALID_RESPONSE
            )
            self.wencai_failure_codes.add(failure_code.value)
            issues = enrichment.issues or (ProviderIssue(
                code=ProviderIssueCode.INVALID_RESPONSE,
                stage=stage,
                safe_message="Wencai industry enrichment returned a failed response",
                retriable=True,
            ),)
            return None, None, None, tuple(issues), False

        identity = decode_stock_identity(enrichment, asset_id)
        industry = identity.get("industry")
        if not industry:
            return None, None, None, (), False
        sector = source_industry_label(industry)
        name = identity.get("name")
        source = enrichment.records[0].source if enrichment.records else None
        if sector is not None:
            self.industry_metadata[asset_id] = {
                "asset_id": asset_id,
                "industry": industry,
                "sector": sector,
                "name": str(name) if name not in (None, "") else None,
                "source": source or "iwencai.com / SkillHub (Official Live)",
                "retrieved_at": enrichment.retrieved_at.isoformat(),
            }
        return sector, str(name) if name not in (None, "") else None, source, (), sector is not None

    async def _execute_fuyao(self, request: ProviderRequest) -> ProviderResult | None:
        asset_id = str(request.parameters.get("asset_id") or request.subject).split()[0]
        if request.operation == ProviderOperation.MARKET_DATA and self._stock_quote_available:
            if asset_id in self._prefetched_quotes:
                quote = self._prefetched_quotes[asset_id]
            else:
                quote = await self._finance_provider.get_quote(asset_id)
            if quote is None:
                return self._empty(request, "fuyao_finance_api")
            if quote.get("is_synthetic") is not False:
                raise ValueError("Fuyao quote did not prove a non-synthetic source")
            sector = None
            enriched_name = None
            enrichment_source = None
            enrichment_issues: list[ProviderIssue] = []
            (
                sector,
                enriched_name,
                enrichment_source,
                industry_issues,
                metadata_succeeded,
            ) = await self._query_industry(
                asset_id,
                request_id=f"{request.request_id}:industry",
                as_of=request.as_of,
                timeout_ms=request.timeout_ms,
                stage="portfolio_industry_enrichment",
            )
            confirmed_sector = self._confirmed_sector(request)
            if not sector and confirmed_sector:
                # The quote remains externally observed and non-synthetic;
                # only the missing enrichment field is retained from the
                # user's explicitly confirmed portfolio classification.  The
                # failed Wencai request is still recorded in
                # ``wencai_failure_codes`` by ``_query_industry`` so runtime
                # capability status does not falsely become READY.
                sector = confirmed_sector
                enrichment_source = "user-confirmed sector"
                industry_issues = ()
            enrichment_issues.extend(industry_issues)
            self.wencai_metadata_succeeded = self.wencai_metadata_succeeded or metadata_succeeded
            fields = {
                "price_cny": quote.get("price_cny"),
                "observed_at": quote.get("observed_at"),
                "sector": sector,
                "name": enriched_name or quote.get("name"),
                "source": " + ".join(filter(None, (
                    quote.get("source") or "Fuyao structured financial data API",
                    enrichment_source,
                ))),
            }
            missing = tuple(
                name for name in ("price_cny", "observed_at", "sector")
                if fields.get(name) in (None, "")
            )
            return self._result(
                request,
                fields,
                source=str(fields["source"]),
                missing_fields=missing,
                issues=tuple(enrichment_issues),
            )

        if request.operation == ProviderOperation.FUND_DATA and self._fund_lookthrough_available:
            fund = await self._finance_provider.get_fund_lookthrough(asset_id)
            if fund is None:
                return self._empty(request, "fuyao_finance_api")
            if fund.get("is_synthetic") is not False:
                raise ValueError("Fuyao fund data did not prove a non-synthetic source")
            raw_holdings = fund.get("top_holdings")
            holdings = [
                {
                    "underlying_asset_id": item.get("asset_id"),
                    "underlying_name": item.get("name"),
                    "weight_pct": item.get("weight_pct"),
                    "sector": item.get("sector"),
                }
                for item in raw_holdings
                if isinstance(item, dict)
            ] if isinstance(raw_holdings, list) else []
            if holdings and self._wencai_available and self._wencai_provider is not None:
                semaphore = asyncio.Semaphore(4)

                async def enrich_holding(index: int, holding: dict[str, Any]) -> dict[str, Any]:
                    async with semaphore:
                        sector, _, source, issues, metadata_succeeded = await self._query_industry(
                            str(holding.get("underlying_asset_id") or ""),
                            request_id=f"{request.request_id}:industry:{index + 1}",
                            as_of=request.as_of,
                            timeout_ms=request.timeout_ms,
                            stage="portfolio_fund_industry_enrichment",
                        )
                    if issues:
                        self.wencai_failure_codes.update(issue.code.value for issue in issues)
                    if metadata_succeeded:
                        self.wencai_metadata_succeeded = True
                    return {
                        **holding,
                        "sector": sector or holding.get("sector"),
                        "source": source,
                    }

                holdings = list(await asyncio.gather(
                    *(enrich_holding(index, holding) for index, holding in enumerate(holdings))
                ))
            coverage = sum(
                (Decimal(str(item["weight_pct"])) for item in holdings if item.get("weight_pct") is not None),
                Decimal("0"),
            )
            fields = {
                "price_cny": fund.get("net_asset_value_cny"),
                "observed_at": fund.get("observed_at"),
                "sector": None,
                "name": fund.get("fund_name"),
                "top_holdings": holdings,
                # ProviderRecord fields are JSON values; keep Decimal math
                # local to the adapter and serialize the derived coverage.
                "coverage_pct": float(coverage),
                "source": fund.get("source") or "Fuyao fund periodic disclosure API",
            }
            missing = tuple(
                name for name in ("price_cny", "observed_at", "top_holdings")
                if fields.get(name) in (None, "", [])
            )
            if holdings and any(not item.get("sector") for item in holdings):
                missing = (*missing, "holding_sector")
            return self._result(request, fields, source=str(fields["source"]), missing_fields=missing)
        return None

    async def execute(self, request: ProviderRequest) -> ProviderResult:
        try:
            result = await self._execute_fuyao(request)
            if result is not None and result.status != ProviderStatus.FAILED:
                return result
        except Exception as exc:
            result = self._failed(request, exc)
        if self._wencai_available and self._wencai_provider is not None:
            wencai_request = request
            if request.operation == ProviderOperation.MARKET_DATA:
                # The portfolio contract needs industry classification.  A
                # generic market query can be unauthorized even when the
                # official industry Skill is available, so route the fallback
                # to the operation that actually supplies the required field.
                wencai_request = request.model_copy(
                    update={"operation": ProviderOperation.INDUSTRY_DATA}
                )
            return await self._wencai_provider.execute(wencai_request)
        if result is not None:
            return result
        return self._failed(request, RuntimeError("no verified live provider capability"))


class PortfolioRefreshRequest(ContractModel):
    schema_version: Literal["portfolio-refresh-request.v1"] = "portfolio-refresh-request.v1"
    request_id: NonEmptyStr
    owner_id: NonEmptyStr
    as_of: datetime
    portfolio: PortfolioImportBundle

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        if self.portfolio.owner_id != self.owner_id:
            raise ValueError("portfolio owner_id does not match request owner_id")
        return self


class PortfolioPositionRefresh(ContractModel):
    position_id: NonEmptyStr
    asset_id: NonEmptyStr
    status: Literal["REFRESHED", "SKIPPED", "REVIEW_REQUIRED", "FAILED"]
    provider: NonEmptyStr
    source: NonEmptyStr | None = None
    provider_status: NonEmptyStr
    price_cny: Decimal | None = Field(default=None, gt=0)
    market_value_cny: Decimal | None = Field(default=None, ge=0)
    observed_at: datetime | None = None
    retrieved_at: datetime
    staleness_seconds: Decimal | None = Field(default=None, ge=0)
    is_synthetic: bool
    missing_fields: tuple[NonEmptyStr, ...] = ()
    issues: tuple[NonEmptyStr, ...] = ()


class PortfolioRefreshResponse(ContractModel):
    schema_version: Literal["portfolio-refresh-response.v1"] = "portfolio-refresh-response.v1"
    request_id: NonEmptyStr
    owner_id: NonEmptyStr
    as_of: datetime
    data_mode: Literal["MOCK", "LIVE"]
    status: Literal["COMPLETE", "REVIEW_REQUIRED", "BLOCKED"]
    portfolio: PortfolioImportBundle | None = None
    positions: tuple[PortfolioPositionRefresh, ...] = Field(min_length=1)
    provider: NonEmptyStr
    is_synthetic: bool
    missing_fields: tuple[NonEmptyStr, ...] = ()
    issues: tuple[NonEmptyStr, ...] = ()


def _parse_decimal(value: object, field_name: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"{field_name} is not a valid decimal") from exc
    if not parsed.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return parsed


def _parse_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is missing")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return parsed


def _wencai_observed_at(fields: dict[str, object], item: dict[str, object]) -> str | None:
    for key in ("最新价时间", "行情时间", "更新时间", "数据时间"):
        value = item.get(key) or fields.get(key)
        if isinstance(value, str) and value.strip():
            try:
                parsed = datetime.fromisoformat(value.strip())
            except ValueError:
                continue
            if parsed.tzinfo is not None and parsed.utcoffset() is not None:
                return parsed.isoformat()
    return None


def _record_fields(result: ProviderResult, position: Position) -> dict[str, object]:
    if not result.records:
        return {}
    fields = dict(result.records[0].fields)
    if all(key in fields for key in ("price_cny", "observed_at", "sector")):
        return fields

    identity = decode_stock_identity(result, position.asset_id)
    quote = decode_stock_quote_fields(result, position.asset_id)
    if not identity and not quote:
        return fields
    return {
        "price_cny": quote.get("price_cny"),
        "observed_at": quote.get("observed_at") or _wencai_observed_at(fields, {}),
        "sector": source_industry_label(identity.get("industry")),
        "name": identity.get("name") or position.asset_name,
        "source": "iwencai.com / SkillHub (Official Live)",
    }


def _provider_issue_messages(result: ProviderResult) -> tuple[str, ...]:
    return tuple(issue.safe_message for issue in result.issues)


def _fund_snapshot(
    position: Position,
    fields: dict[str, object],
    owner_id: str,
    observed_at: datetime,
) -> FundHoldingSnapshot:
    raw_holdings = fields.get("top_holdings")
    if not isinstance(raw_holdings, list) or not raw_holdings:
        raise ValueError("top_holdings is missing or not a non-empty list")

    coverage = _parse_decimal(fields.get("coverage_pct"), "coverage_pct")
    holdings: list[LookThroughHolding] = []
    for index, raw in enumerate(raw_holdings):
        if not isinstance(raw, dict):
            raise ValueError(f"top_holdings[{index}] is not an object")
        asset_id = str(raw.get("underlying_asset_id") or raw.get("asset_id") or "").strip()
        name = str(raw.get("underlying_name") or raw.get("name") or "").strip()
        sector = str(raw.get("sector") or "").strip() or None
        if not asset_id or not name or sector is None:
            raise ValueError(f"top_holdings[{index}] lacks canonical asset fields")
        holdings.append(
            LookThroughHolding(
                holding_id=f"{position.asset_id}:holding:{index + 1}",
                parent_asset_id=position.asset_id,
                underlying_asset_id=asset_id,
                underlying_name=name,
                asset_type=AssetType.STOCK,
                weight_pct=_parse_decimal(raw.get("weight_pct"), f"top_holdings[{index}].weight_pct"),
                sector=sector,
                as_of=observed_at,
                source=position.source,
            )
        )
    return FundHoldingSnapshot(
        snapshot_id=f"live:{position.asset_id}:{observed_at.isoformat()}",
        owner_id=owner_id,
        parent_asset_id=position.asset_id,
        parent_asset_type=position.asset_type,
        as_of=observed_at,
        source=position.source,
        coverage_pct=coverage,
        holdings=tuple(holdings),
    )


async def _refresh_position(
    request: PortfolioRefreshRequest,
    position: Position,
    provider: FinancialProvider,
) -> tuple[Position, PortfolioPositionRefresh, FundHoldingSnapshot | None]:
    retrieved_at = datetime.now(request.as_of.tzinfo)
    operation = (
        ProviderOperation.FUND_DATA
        if position.asset_type in {AssetType.ETF, AssetType.MUTUAL_FUND}
        else ProviderOperation.MARKET_DATA
    )
    provider_request = ProviderRequest(
        request_id=f"{request.request_id}:{position.position_id}",
        operation=operation,
        subject=(
            f"{position.asset_id} 最新价 所属同花顺行业"
            if position.asset_type == AssetType.STOCK
            else position.asset_id
        ),
        as_of=request.as_of,
        # The generic SkillHub adapter returns raw items/columns.  Canonical
        # refresh fields are validated below after operation-specific decoding.
        required_fields=(),
        parameters={
            "asset_id": position.asset_id,
            "asset_type": position.asset_type.value,
            "existing_sector": position.sector,
            "existing_sector_source": position.source,
        },
        timeout_ms=2000,
    )
    try:
        result = await provider.execute(provider_request)
    except Exception as exc:
        row = PortfolioPositionRefresh(
            position_id=position.position_id,
            asset_id=position.asset_id,
            status="FAILED",
            provider=getattr(provider, "name", "unknown_provider"),
            provider_status=ProviderStatus.FAILED.value,
            retrieved_at=retrieved_at,
            is_synthetic=False,
            issues=(f"provider execution failed: {type(exc).__name__}",),
        )
        return position, row, None

    fields = _record_fields(result, position)
    provider_name = result.provider
    if result.status not in {ProviderStatus.SUCCESS, ProviderStatus.PARTIAL} or not fields:
        row = PortfolioPositionRefresh(
            position_id=position.position_id,
            asset_id=position.asset_id,
            status="FAILED" if result.status == ProviderStatus.FAILED else "REVIEW_REQUIRED",
            provider=provider_name,
            provider_status=result.status.value,
            retrieved_at=result.retrieved_at,
            is_synthetic=False,
            missing_fields=result.missing_fields,
            issues=_provider_issue_messages(result),
        )
        return position, row, None

    missing: list[str] = list(result.missing_fields)
    issues: list[str] = list(_provider_issue_messages(result))
    is_fund = position.asset_type in {AssetType.ETF, AssetType.MUTUAL_FUND}
    price: Decimal | None = None
    observed_at: datetime | None = None
    sector = ""
    try:
        price = _parse_decimal(fields.get("price_cny"), "price_cny")
        if price <= 0:
            price = None
            raise ValueError("price_cny must be positive")
    except ValueError as exc:
        issues.append(str(exc))
        missing.append("price_cny")
    try:
        observed_at = _parse_datetime(fields.get("observed_at"), "observed_at")
    except ValueError as exc:
        issues.append(str(exc))
        missing.append("observed_at")
    sector = str(fields.get("sector") or "").strip()
    if not sector and not is_fund:
        issues.append("sector is missing")
        missing.append("sector")
    if price is None or observed_at is None:
        row = PortfolioPositionRefresh(
            position_id=position.position_id,
            asset_id=position.asset_id,
            status="REVIEW_REQUIRED",
            provider=provider_name,
            source=str(fields.get("source") or provider_name),
            provider_status=result.status.value,
            retrieved_at=result.retrieved_at,
            is_synthetic=False,
            missing_fields=tuple(dict.fromkeys(missing)),
            issues=tuple(dict.fromkeys(issues)),
        )
        return position, row, None

    market_value = (price * position.quantity).quantize(Decimal("0.01"))
    refreshed = position.model_copy(
        update={
            "asset_name": str(fields.get("name") or position.asset_name),
            "sector": sector or (position.sector if is_fund else "Unclassified"),
            "market_value": market_value,
            "as_of": observed_at,
            "source": str(fields.get("source") or provider_name),
        }
    )
    fund_snapshot = None
    if is_fund and not any(
        field in missing for field in ("top_holdings", "holding_sector")
    ):
        try:
            fund_snapshot = _fund_snapshot(position, fields, request.owner_id, observed_at)
        except ValueError as exc:
            missing.append("top_holdings")
            issues.append(str(exc))

    staleness = max(Decimal("0"), Decimal(str((request.as_of - observed_at).total_seconds())))
    status = (
        "REFRESHED"
        if not missing
        and not issues
        and (
            fund_snapshot is not None
            or position.asset_type not in {AssetType.ETF, AssetType.MUTUAL_FUND}
        )
        else "REVIEW_REQUIRED"
    )
    row = PortfolioPositionRefresh(
        position_id=position.position_id,
        asset_id=position.asset_id,
        status=status,
        provider=provider_name,
        source=refreshed.source,
        provider_status=result.status.value,
        price_cny=price,
        market_value_cny=market_value,
        observed_at=observed_at,
        retrieved_at=result.retrieved_at,
        staleness_seconds=staleness,
        is_synthetic=False,
        missing_fields=tuple(dict.fromkeys(missing)),
        issues=tuple(dict.fromkeys(issues)),
    )
    return refreshed, row, fund_snapshot


async def refresh_portfolio_live(
    request: PortfolioRefreshRequest,
    provider: FinancialProvider,
) -> PortfolioRefreshResponse:
    positions = request.portfolio.position_snapshot.positions
    non_cash = [position for position in positions if position.asset_type != AssetType.CASH]
    if isinstance(provider, LivePortfolioProviderAdapter):
        await provider.prefetch_quotes([
            position.asset_id
            for position in non_cash
            if position.asset_type == AssetType.STOCK
        ])
    results = await asyncio.gather(
        *(_refresh_position(request, position, provider) for position in non_cash)
    )
    refreshed_by_id = {position.position_id: position for position, _, _ in results}
    rows = [row for _, row, _ in results]
    rows.extend(
        PortfolioPositionRefresh(
            position_id=position.position_id,
            asset_id=position.asset_id,
            status="SKIPPED",
            provider="prism-deterministic",
            provider_status="SKIPPED",
            market_value_cny=position.market_value,
            observed_at=position.as_of,
            retrieved_at=request.as_of,
            staleness_seconds=Decimal("0"),
            is_synthetic=False,
        )
        for position in positions
        if position.asset_type == AssetType.CASH
    )
    rows = sorted(rows, key=lambda row: row.position_id)
    all_ready = all(row.status in {"REFRESHED", "SKIPPED"} for row in rows)
    fund_snapshots = [snapshot for _, _, snapshot in results if snapshot is not None]
    issues = tuple(issue for row in rows for issue in row.issues)
    missing = tuple(dict.fromkeys(field for row in rows for field in row.missing_fields))
    # Equity-only reports can show verified prices while retaining unknown
    # sectors. Such a bundle is REVIEW_REQUIRED and never authorizes trading
    # targets. Missing prices or fund disclosures still return no bundle.
    partial_equity_report = bool(non_cash) and all(
        position.asset_type == AssetType.STOCK for position in non_cash
    ) and all(
        row.status == "SKIPPED" or (row.price_cny is not None and row.observed_at is not None)
        for row in rows
    )
    if not all_ready and not partial_equity_report:
        return PortfolioRefreshResponse(
            request_id=request.request_id,
            owner_id=request.owner_id,
            as_of=request.as_of,
            data_mode="LIVE",
            status="REVIEW_REQUIRED",
            positions=tuple(rows),
            provider=getattr(provider, "name", "unknown_provider"),
            is_synthetic=False,
            missing_fields=missing,
            issues=issues or ("live portfolio refresh was not complete",),
        )

    position_snapshot = request.portfolio.position_snapshot.model_copy(
        update={
            "as_of": max(
                (position.as_of for position in refreshed_by_id.values()),
                default=request.as_of,
            ),
            "source": "live_portfolio_sources",
            "positions": tuple(
                refreshed_by_id.get(position.position_id, position) for position in positions
            ),
        }
    )
    portfolio = request.portfolio.model_copy(
        update={
            "created_at": request.as_of,
            "position_snapshot": position_snapshot,
            "fund_holdings": tuple(fund_snapshots),
        }
    )
    return PortfolioRefreshResponse(
        request_id=request.request_id,
        owner_id=request.owner_id,
        as_of=request.as_of,
        data_mode="LIVE",
        status="COMPLETE" if all_ready else "REVIEW_REQUIRED",
        portfolio=portfolio,
        positions=tuple(rows),
        provider=getattr(provider, "name", "unknown_provider"),
        is_synthetic=False,
        missing_fields=missing,
        issues=issues,
    )


def refresh_portfolio_mock(request: PortfolioRefreshRequest) -> PortfolioRefreshResponse:
    rows = tuple(
        PortfolioPositionRefresh(
            position_id=position.position_id,
            asset_id=position.asset_id,
            status="SKIPPED",
            provider="static_fixture",
            provider_status="SUCCESS",
            market_value_cny=position.market_value,
            observed_at=position.as_of,
            retrieved_at=request.as_of,
            staleness_seconds=max(
                Decimal("0"), Decimal(str((request.as_of - position.as_of).total_seconds()))
            ),
            is_synthetic=True,
        )
        for position in request.portfolio.position_snapshot.positions
    )
    return PortfolioRefreshResponse(
        request_id=request.request_id,
        owner_id=request.owner_id,
        as_of=request.as_of,
        data_mode="MOCK",
        status="COMPLETE",
        portfolio=request.portfolio,
        positions=rows,
        provider="static_fixture",
        is_synthetic=True,
    )
