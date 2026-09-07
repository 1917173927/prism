"""Owner-scoped portfolio market-data refresh contracts and execution."""

from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Literal, Self

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
    ProviderOperation,
    ProviderRequest,
    ProviderResult,
    ProviderStatus,
)


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


def _record_fields(result: ProviderResult) -> dict[str, object]:
    if not result.records:
        return {}
    return dict(result.records[0].fields)


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
        subject=position.asset_id,
        as_of=request.as_of,
        required_fields=("price_cny", "observed_at", "sector"),
        parameters={"asset_id": position.asset_id, "asset_type": position.asset_type.value},
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

    fields = _record_fields(result)
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
    try:
        price = _parse_decimal(fields.get("price_cny"), "price_cny")
        observed_at = _parse_datetime(fields.get("observed_at"), "observed_at")
        sector = str(fields.get("sector") or "").strip()
        if not sector:
            raise ValueError("sector is missing")
    except ValueError as exc:
        issues.append(str(exc))
        if "price_cny" not in missing:
            missing.append("price_cny")
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
            "source": "iwencai_skillhub_live",
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
