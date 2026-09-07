"""Immutable contracts for raw portfolio and fund look-through imports.

This module deliberately stops at the import boundary.  It records what was
observed, when it was observed, and for which owner; it does not calculate
exposure, concentration, risk, or allocation recommendations.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from app.contracts.evidence import ContractModel, NonEmptyStr


CurrencyCode = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_upper=True,
        min_length=3,
        max_length=3,
        pattern=r"^[A-Za-z]{3}$",
    ),
]


class AssetType(StrEnum):
    STOCK = "STOCK"
    ETF = "ETF"
    MUTUAL_FUND = "MUTUAL_FUND"
    BOND = "BOND"
    CASH = "CASH"
    OTHER = "OTHER"


class PositionImportStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    EMPTY = "EMPTY"
    FAILED = "FAILED"


class PositionImportIssueCode(StrEnum):
    INVALID_ROW = "INVALID_ROW"
    DUPLICATE_ID = "DUPLICATE_ID"
    UNSUPPORTED_ASSET = "UNSUPPORTED_ASSET"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    PARSE_ERROR = "PARSE_ERROR"


def _require_timezone(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


class Position(ContractModel):
    """One raw position observed for an owner."""

    position_id: NonEmptyStr
    owner_id: NonEmptyStr
    asset_id: NonEmptyStr
    asset_type: AssetType
    asset_name: NonEmptyStr
    sector: NonEmptyStr | None = None
    quantity: Decimal = Field(gt=Decimal("0"))
    market_value: Decimal = Field(ge=Decimal("0"))
    currency: CurrencyCode
    as_of: datetime
    source: NonEmptyStr

    @model_validator(mode="after")
    def validate_timestamp(self) -> Self:
        _require_timezone(self.as_of, "as_of")
        return self


class PositionSnapshot(ContractModel):
    """A non-empty point-in-time position snapshot for one owner."""

    schema_version: Literal["position-snapshot.v1"] = "position-snapshot.v1"
    snapshot_id: NonEmptyStr
    owner_id: NonEmptyStr
    as_of: datetime
    base_currency: CurrencyCode
    source: NonEmptyStr
    positions: tuple[Position, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_snapshot(self) -> Self:
        _require_timezone(self.as_of, "as_of")
        position_ids = [position.position_id for position in self.positions]
        if len(set(position_ids)) != len(position_ids):
            raise ValueError("positions must not contain duplicate position_id")
        if any(position.owner_id != self.owner_id for position in self.positions):
            raise ValueError("position owner_id does not match snapshot owner_id")
        return self


class PositionImportIssue(ContractModel):
    """Safe, structured import failure information without raw provider data."""

    code: PositionImportIssueCode
    safe_message: NonEmptyStr
    retriable: bool = False
    row_reference: NonEmptyStr | None = None


class PositionImportResult(ContractModel):
    """Four-state result separating empty, incomplete, and failed imports."""

    schema_version: Literal["position-import.v1"] = "position-import.v1"
    request_id: NonEmptyStr
    owner_id: NonEmptyStr
    status: PositionImportStatus
    imported_at: datetime
    snapshot: PositionSnapshot | None = None
    missing_fields: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    issues: tuple[PositionImportIssue, ...] = Field(default_factory=tuple)
    scope_description: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        _require_timezone(self.imported_at, "imported_at")
        if len(set(self.missing_fields)) != len(self.missing_fields):
            raise ValueError("missing_fields must not contain duplicates")
        if self.snapshot is not None and self.snapshot.owner_id != self.owner_id:
            raise ValueError("snapshot owner_id does not match import owner_id")

        if self.status == PositionImportStatus.COMPLETE:
            if self.snapshot is None:
                raise ValueError("COMPLETE import requires a snapshot")
            if self.missing_fields or self.issues:
                raise ValueError("COMPLETE import must not carry missing_fields or issues")
        elif self.status == PositionImportStatus.PARTIAL:
            if self.snapshot is None:
                raise ValueError("PARTIAL import requires a usable snapshot")
            if not self.missing_fields and not self.issues:
                raise ValueError("PARTIAL import requires missing_fields or issues")
        elif self.status == PositionImportStatus.EMPTY:
            if self.snapshot is not None:
                raise ValueError("EMPTY import must not carry a snapshot")
            if self.missing_fields or self.issues:
                raise ValueError("EMPTY import must not carry missing_fields or issues")
            if self.scope_description is None:
                raise ValueError("EMPTY import requires an explicit scope_description")
        elif self.status == PositionImportStatus.FAILED:
            if self.snapshot is not None:
                raise ValueError("FAILED import must not carry a snapshot")
            if not self.issues:
                raise ValueError("FAILED import requires at least one issue")
        return self


class LookThroughHolding(ContractModel):
    """One raw constituent row from a fund or ETF report."""

    holding_id: NonEmptyStr
    parent_asset_id: NonEmptyStr
    underlying_asset_id: NonEmptyStr
    underlying_name: NonEmptyStr
    asset_type: AssetType
    weight_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    sector: NonEmptyStr | None = None
    as_of: datetime
    source: NonEmptyStr

    @model_validator(mode="after")
    def validate_timestamp(self) -> Self:
        _require_timezone(self.as_of, "as_of")
        return self


class FundHoldingSnapshot(ContractModel):
    """Raw look-through holdings for one ETF or mutual fund parent."""

    schema_version: Literal["fund-holdings-snapshot.v1"] = "fund-holdings-snapshot.v1"
    snapshot_id: NonEmptyStr
    owner_id: NonEmptyStr
    parent_asset_id: NonEmptyStr
    parent_asset_type: AssetType
    as_of: datetime
    source: NonEmptyStr
    coverage_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    holdings: tuple[LookThroughHolding, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_holdings(self) -> Self:
        _require_timezone(self.as_of, "as_of")
        if self.parent_asset_type not in {
            AssetType.ETF,
            AssetType.MUTUAL_FUND,
        }:
            raise ValueError("parent_asset_type must be ETF or MUTUAL_FUND")

        holding_ids = [holding.holding_id for holding in self.holdings]
        if len(set(holding_ids)) != len(holding_ids):
            raise ValueError("holdings must not contain duplicate holding_id")
        if any(
            holding.parent_asset_id != self.parent_asset_id
            for holding in self.holdings
        ):
            raise ValueError("holding parent_asset_id does not match snapshot parent")

        weight_total = sum(
            (holding.weight_pct for holding in self.holdings),
            Decimal("0"),
        )
        if weight_total > Decimal("100"):
            raise ValueError("holding weights must sum to at most 100 percent")
        return self


class PortfolioImportBundle(ContractModel):
    """Owner-closed raw positions plus optional fund look-through snapshots."""

    schema_version: Literal["portfolio-import-bundle.v1"] = "portfolio-import-bundle.v1"
    bundle_id: NonEmptyStr
    owner_id: NonEmptyStr
    created_at: datetime
    position_snapshot: PositionSnapshot
    fund_holdings: tuple[FundHoldingSnapshot, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_bundle(self) -> Self:
        _require_timezone(self.created_at, "created_at")
        if self.position_snapshot.owner_id != self.owner_id:
            raise ValueError("position snapshot owner_id does not match bundle owner_id")

        positions_by_asset = {}
        for position in self.position_snapshot.positions:
            positions_by_asset.setdefault(position.asset_id, []).append(position)

        parent_ids = [snapshot.parent_asset_id for snapshot in self.fund_holdings]
        if len(set(parent_ids)) != len(parent_ids):
            raise ValueError("fund_holdings must not contain duplicate parent assets")
        snapshot_ids = [snapshot.snapshot_id for snapshot in self.fund_holdings]
        if len(set(snapshot_ids)) != len(snapshot_ids):
            raise ValueError("fund_holdings must not contain duplicate snapshot_id")

        for snapshot in self.fund_holdings:
            if snapshot.owner_id != self.owner_id:
                raise ValueError("fund holding owner_id does not match bundle owner_id")
            parent_positions = positions_by_asset.get(snapshot.parent_asset_id, [])
            if not parent_positions:
                raise ValueError(
                    "fund holding parent_asset_id is not present in position snapshot"
                )
            if any(
                position.asset_type != snapshot.parent_asset_type
                for position in parent_positions
            ):
                raise ValueError("fund holding parent_asset_type does not match position")
        return self
