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
    ) -> None:
        self._finance_provider = finance_provider
        self._wencai_provider = wencai_provider
        self._stock_quote_available = stock_quote_available
        self._fund_lookthrough_available = fund_lookthrough_available
        self._wencai_available = wencai_available
        self.wencai_failure_codes: set[str] = set()
        self.wencai_metadata_succeeded = False

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

    async def _execute_fuyao(self, request: ProviderRequest) -> ProviderResult | None:
        asset_id = str(request.parameters.get("asset_id") or request.subject).split()[0]
        if request.operation == ProviderOperation.MARKET_DATA and self._stock_quote_available:
            quote = await self._finance_provider.get_quote(asset_id)
            if quote is None:
                return self._empty(request, "fuyao_finance_api")
            if quote.get("is_synthetic") is not False:
                raise ValueError("Fuyao quote did not prove a non-synthetic source")
            sector = None
            enriched_name = None
            enrichment_source = None
            enrichment_issues: list[ProviderIssue] = []
            if self._wencai_available and self._wencai_provider is not None:
                enrichment_request = ProviderRequest(
                    request_id=f"{request.request_id}:industry",
                    operation=ProviderOperation.COMPANY_DATA,
                    subject=f"{asset_id} 所属同花顺行业 股票简称",
                    as_of=request.as_of,
                    parameters={"asset_id": asset_id},
                    timeout_ms=request.timeout_ms,
                )
                try:
                    enrichment = await self._wencai_provider.execute(enrichment_request)
                except Exception as exc:
                    enrichment = None
                    self.wencai_failure_codes.add(ProviderIssueCode.TRANSPORT_ERROR.value)
                    enrichment_issues.append(ProviderIssue(
                        code=ProviderIssueCode.TRANSPORT_ERROR,
                        stage="portfolio_industry_enrichment",
                        safe_message=f"Wencai industry enrichment failed: {type(exc).__name__}",
                        retriable=True,
                    ))
                if enrichment is not None and enrichment.status == ProviderStatus.FAILED:
                    failure_code = (
                        enrichment.issues[0].code
                        if enrichment.issues
                        else ProviderIssueCode.INVALID_RESPONSE
                    )
                    self.wencai_failure_codes.add(failure_code.value)
                    enrichment_issues.extend(enrichment.issues or (ProviderIssue(
                        code=ProviderIssueCode.INVALID_RESPONSE,
                        stage="portfolio_industry_enrichment",
                        safe_message="Wencai industry enrichment returned a failed response",
                        retriable=True,
                    ),))
                if enrichment is not None and enrichment.status in {
                    ProviderStatus.SUCCESS,
                    ProviderStatus.PARTIAL,
                }:
                    for record in enrichment.records:
                        items = record.fields.get("items")
                        if not isinstance(items, (list, tuple)):
                            continue
                        match = next(
                            (
                                item for item in items
                                if isinstance(item, dict)
                                and str(item.get("股票代码") or "").split(".")[0]
                                == asset_id.split(".")[0]
                            ),
                            None,
                        )
                        if match is None:
                            continue
                        sector = _canonical_sector_from_wencai(
                            match.get("所属同花顺行业") or match.get("所属申万行业")
                        )
                        if sector is not None:
                            self.wencai_metadata_succeeded = True
                        enriched_name = match.get("股票简称")
                        enrichment_source = record.source
                        break
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
                "coverage_pct": coverage,
                "source": fund.get("source") or "Fuyao fund periodic disclosure API",
            }
            missing = tuple(
                name for name in ("price_cny", "observed_at", "sector", "top_holdings")
                if fields.get(name) in (None, "", [])
            )
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
            return await self._wencai_provider.execute(request)
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


def _canonical_sector_from_wencai(value: object) -> str | None:
    if isinstance(value, (list, tuple)):
        labels = " ".join(str(item) for item in value)
    else:
        labels = str(value or "")
    mappings = (
        (("半导体", "电子", "计算机", "通信", "软件", "互联网"), "Technology"),
        (("电力设备", "电池", "机械", "汽车", "军工", "制造"), "Industrials"),
        (("食品", "饮料", "白酒", "消费", "医药", "生物", "医疗"), "Consumer"),
        (("银行", "保险", "金融", "煤炭", "石油", "有色", "钢铁", "化工", "公用", "房地产"), "Finance"),
    )
    for keywords, canonical in mappings:
        if any(keyword in labels for keyword in keywords):
            return canonical
    return None


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

    raw_items = fields.get("items")
    if not isinstance(raw_items, (list, tuple)):
        return fields
    expected_code = position.asset_id.split(".")[0]
    item = next(
        (
            dict(candidate)
            for candidate in raw_items
            if isinstance(candidate, dict)
            and str(candidate.get("股票代码") or "").split(".")[0] == expected_code
        ),
        None,
    )
    if item is None:
        return fields
    industry = item.get("所属同花顺行业") or item.get("所属申万行业")
    observed_at = _wencai_observed_at(fields, item)
    return {
        "price_cny": item.get("最新价"),
        "observed_at": observed_at,
        "sector": _canonical_sector_from_wencai(industry),
        "name": item.get("股票简称") or position.asset_name,
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
    price: Decimal | None = None
    observed_at: datetime | None = None
    sector = ""
    try:
        price = _parse_decimal(fields.get("price_cny"), "price_cny")
    except ValueError as exc:
        issues.append(str(exc))
        missing.append("price_cny")
    try:
        observed_at = _parse_datetime(fields.get("observed_at"), "observed_at")
    except ValueError as exc:
        issues.append(str(exc))
        missing.append("observed_at")
    sector = str(fields.get("sector") or "").strip()
    if not sector:
        issues.append("sector is missing")
        missing.append("sector")
    if price is None or observed_at is None or not sector:
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
            "sector": sector,
            "market_value": market_value,
            "as_of": observed_at,
            "source": str(fields.get("source") or provider_name),
        }
    )
    fund_snapshot = None
    if position.asset_type in {AssetType.ETF, AssetType.MUTUAL_FUND}:
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
    if not all_ready:
        issues = tuple(issue for row in rows for issue in row.issues)
        missing = tuple(dict.fromkeys(field for row in rows for field in row.missing_fields))
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
        status="COMPLETE",
        portfolio=portfolio,
        positions=tuple(rows),
        provider=getattr(provider, "name", "unknown_provider"),
        is_synthetic=False,
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
