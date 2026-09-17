"""Immutable contracts for owner-scoped historical trade records."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from app.contracts.evidence import ContractModel, NonEmptyStr


class TradeSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class TradeAssetType(StrEnum):
    STOCK = "STOCK"
    ETF = "ETF"
    MUTUAL_FUND = "MUTUAL_FUND"
    CONVERTIBLE_BOND = "CONVERTIBLE_BOND"
    OTHER = "OTHER"


class TradeRecordStatus(StrEnum):
    ACTIVE = "ACTIVE"
    WITHDRAWN = "WITHDRAWN"


class TradingStyleStatus(StrEnum):
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    PRELIMINARY = "PRELIMINARY"
    CALCULATED = "CALCULATED"


class HistoricalTradeRecord(ContractModel):
    schema_version: Literal["historical-trade-record.v1"] = "historical-trade-record.v1"
    trade_id: NonEmptyStr
    owner_id: NonEmptyStr
    batch_id: NonEmptyStr
    revision: int = Field(ge=1)
    status: TradeRecordStatus = TradeRecordStatus.ACTIVE
    traded_at: datetime
    security_code: NonEmptyStr | None = None
    security_name: NonEmptyStr | None = None
    side: TradeSide
    quantity: Decimal = Field(gt=0)
    price_cny: Decimal = Field(gt=0)
    gross_amount_cny: Decimal = Field(gt=0)
    fee_cny: Decimal = Field(default=Decimal("0"), ge=0)
    asset_type: TradeAssetType | None = None
    account_alias: NonEmptyStr = "默认账户"
    broker_trade_id: NonEmptyStr | None = None
    account_value_cny: Decimal | None = Field(default=None, gt=0)
    source_row: int = Field(ge=1)
    source_confidence: Decimal = Field(default=Decimal("1"), ge=0, le=1)
    created_at: datetime
    updated_at: datetime
    review_notes: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_record(self) -> Self:
        for value in (self.traded_at, self.created_at, self.updated_at):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("trade timestamps must be timezone-aware")
        if not self.security_code and not self.security_name:
            raise ValueError("security_code or security_name is required")
        expected = self.quantity * self.price_cny
        tolerance = max(Decimal("0.01"), expected * Decimal("0.001"))
        if abs(self.gross_amount_cny - expected) > tolerance:
            raise ValueError("gross amount differs from quantity times price beyond tolerance")
        if len(set(self.review_notes)) != len(self.review_notes):
            raise ValueError("review_notes must be unique")
        return self


class TradeImportBatch(ContractModel):
    schema_version: Literal["trade-import-batch.v1"] = "trade-import-batch.v1"
    batch_id: NonEmptyStr
    owner_id: NonEmptyStr
    source_type: Literal["CSV", "XLSX", "IMAGE"]
    source_digest: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    file_count: int = Field(ge=1, le=10)
    accepted_count: int = Field(ge=0)
    duplicate_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    confirmed_at: datetime

    @model_validator(mode="after")
    def validate_batch(self) -> Self:
        if self.confirmed_at.tzinfo is None or self.confirmed_at.utcoffset() is None:
            raise ValueError("confirmed_at must be timezone-aware")
        return self


class TradingStyleMetrics(ContractModel):
    trade_count: int = Field(ge=0)
    observed_span_days: Decimal = Field(ge=0)
    trades_per_month: Decimal = Field(ge=0)
    median_holding_days: Decimal | None = Field(default=None, ge=0)
    matched_sell_coverage: Decimal = Field(ge=0, le=1)
    median_trade_amount_cny: Decimal | None = Field(default=None, ge=0)
    q1_trade_amount_cny: Decimal | None = Field(default=None, ge=0)
    q3_trade_amount_cny: Decimal | None = Field(default=None, ge=0)
    symbol_hhi: Decimal | None = Field(default=None, ge=0, le=1)
    top3_symbol_share_pct: Decimal | None = Field(default=None, ge=0, le=100)
    turnover_90d_pct: Decimal | None = Field(default=None, ge=0)
    unmatched_sell_quantity: Decimal = Field(default=Decimal("0"), ge=0)


class TradingStyleProfile(ContractModel):
    schema_version: Literal["trading-style-profile.v1"] = "trading-style-profile.v1"
    profile_id: NonEmptyStr
    owner_id: NonEmptyStr
    profile_version: int = Field(ge=1)
    calculated_at: datetime
    ruleset_version: Literal["trading-style-rules.v1"] = "trading-style-rules.v1"
    status: TradingStyleStatus
    primary_style: NonEmptyStr | None = None
    confidence: Decimal = Field(ge=0, le=1)
    metrics: TradingStyleMetrics
    active_trade_ids: tuple[NonEmptyStr, ...]
    data_gaps: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_profile(self) -> Self:
        if self.calculated_at.tzinfo is None or self.calculated_at.utcoffset() is None:
            raise ValueError("calculated_at must be timezone-aware")
        if self.status == TradingStyleStatus.INSUFFICIENT_DATA and self.primary_style is not None:
            raise ValueError("insufficient data must not produce a style label")
        if self.status != TradingStyleStatus.INSUFFICIENT_DATA and self.primary_style is None:
            raise ValueError("usable data requires a style label")
        if len(set(self.active_trade_ids)) != len(self.active_trade_ids):
            raise ValueError("active trade IDs must be unique")
        return self


class TradePreviewRow(ContractModel):
    row_number: int = Field(ge=1)
    raw_values: dict[str, str | None]
    proposed: dict[str, Any]
    confidence: Decimal = Field(ge=0, le=1)
    status: Literal["PASS", "REVIEW_REQUIRED", "OVERBOUND"]
    issues: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)


class TradeImportPreview(ContractModel):
    schema_version: Literal["trade-import-preview.v1"] = "trade-import-preview.v1"
    source_type: Literal["CSV", "XLSX", "IMAGE"]
    source_digest: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    file_count: int = Field(ge=1, le=10)
    detected_columns: tuple[str, ...]
    suggested_mapping: dict[str, str]
    sheets: tuple[str, ...] = Field(default_factory=tuple)
    selected_sheet: str | None = None
    rows: tuple[TradePreviewRow, ...]
    accepted_count: int = Field(ge=0)
    review_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    original_files_persisted: Literal[False] = False


class TradeConfirmRow(ContractModel):
    traded_at: datetime
    security_code: NonEmptyStr | None = None
    security_name: NonEmptyStr | None = None
    side: TradeSide
    quantity: Decimal = Field(gt=0)
    price_cny: Decimal = Field(gt=0)
    gross_amount_cny: Decimal | None = Field(default=None, gt=0)
    fee_cny: Decimal = Field(default=Decimal("0"), ge=0)
    asset_type: TradeAssetType | None = None
    account_alias: NonEmptyStr = "默认账户"
    broker_trade_id: NonEmptyStr | None = None
    account_value_cny: Decimal | None = Field(default=None, gt=0)
    source_row: int = Field(ge=1)
    source_confidence: Decimal = Field(default=Decimal("1"), ge=0, le=1)
    review_notes: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_confirm_row(self) -> Self:
        if self.traded_at.tzinfo is None or self.traded_at.utcoffset() is None:
            raise ValueError("traded_at must be timezone-aware")
        if not self.security_code and not self.security_name:
            raise ValueError("security_code or security_name is required")
        if self.gross_amount_cny is not None:
            expected = self.quantity * self.price_cny
            tolerance = max(Decimal("0.01"), expected * Decimal("0.001"))
            if abs(self.gross_amount_cny - expected) > tolerance:
                raise ValueError("gross amount differs from quantity times price beyond tolerance")
        return self


class TradeImportConfirmRequest(ContractModel):
    schema_version: Literal["trade-import-confirm-request.v1"] = "trade-import-confirm-request.v1"
    owner_id: NonEmptyStr
    source_type: Literal["CSV", "XLSX", "IMAGE"]
    source_digest: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    file_count: int = Field(ge=1, le=10)
    rows: tuple[TradeConfirmRow, ...] = Field(min_length=1, max_length=20000)


class TradeImportConfirmResponse(ContractModel):
    schema_version: Literal["trade-import-confirm-response.v1"] = "trade-import-confirm-response.v1"
    batch: TradeImportBatch
    trades: tuple[HistoricalTradeRecord, ...]
    style_profile: TradingStyleProfile


class TradeUpdateRequest(ContractModel):
    schema_version: Literal["trade-update-request.v1"] = "trade-update-request.v1"
    expected_revision: int = Field(ge=1)
    traded_at: datetime | None = None
    security_code: str | None = None
    security_name: str | None = None
    side: TradeSide | None = None
    quantity: Decimal | None = Field(default=None, gt=0)
    price_cny: Decimal | None = Field(default=None, gt=0)
    gross_amount_cny: Decimal | None = Field(default=None, gt=0)
    fee_cny: Decimal | None = Field(default=None, ge=0)
    asset_type: TradeAssetType | None = None
    account_alias: str | None = None
    broker_trade_id: str | None = None
    account_value_cny: Decimal | None = Field(default=None, gt=0)


class TradeRevisionRequest(ContractModel):
    schema_version: Literal["trade-revision-request.v1"] = "trade-revision-request.v1"
    expected_revision: int = Field(ge=1)


class TradeMutationResponse(ContractModel):
    schema_version: Literal["trade-mutation-response.v1"] = "trade-mutation-response.v1"
    trade: HistoricalTradeRecord
    style_profile: TradingStyleProfile


class TradeListResponse(ContractModel):
    schema_version: Literal["trade-list-response.v1"] = "trade-list-response.v1"
    items: tuple[HistoricalTradeRecord, ...]
    next_cursor: int | None = Field(default=None, ge=0)
    total: int = Field(ge=0)


class TradeBatchListResponse(ContractModel):
    schema_version: Literal["trade-batch-list-response.v1"] = "trade-batch-list-response.v1"
    items: tuple[TradeImportBatch, ...]
    next_cursor: int | None = Field(default=None, ge=0)
    total: int = Field(ge=0)


class TradingStyleLookupResponse(ContractModel):
    schema_version: Literal["trading-style-lookup-response.v1"] = "trading-style-lookup-response.v1"
    profile: TradingStyleProfile
