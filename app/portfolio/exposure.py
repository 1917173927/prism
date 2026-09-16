"""Deterministic look-through exposure calculations.

The calculation consumes only the raw Phase 2 portfolio contracts.  It keeps
unlooked-through value explicit and never performs FX conversion, weight
normalisation, risk scoring, or recommendation generation.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum
from hashlib import sha256
from typing import Literal, Self

from pydantic import Field, model_validator

from app.contracts.evidence import ContractModel, NonEmptyStr
from app.portfolio.contracts import (
    AssetType,
    CurrencyCode,
    FundHoldingSnapshot,
    PortfolioImportBundle,
    Position,
)


class ExposureBasis(StrEnum):
    DIRECT = "DIRECT"
    LOOK_THROUGH = "LOOK_THROUGH"
    UNLOOKED_THROUGH = "UNLOOKED_THROUGH"


class ExposureStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class ExposureIssueCode(StrEnum):
    MISSING_LOOK_THROUGH = "MISSING_LOOK_THROUGH"
    INCOMPLETE_LOOK_THROUGH = "INCOMPLETE_LOOK_THROUGH"
    FUTURE_HOLDINGS = "FUTURE_HOLDINGS"
    NON_BASE_CURRENCY = "NON_BASE_CURRENCY"
    ZERO_PORTFOLIO_VALUE = "ZERO_PORTFOLIO_VALUE"


def _require_timezone(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _is_technology_sector(sector: str | None) -> bool:
    if sector is None:
        return False
    normalized = sector.strip().casefold()
    if normalized in {
        "technology",
        "information technology",
        "tech",
    }:
        return True
    return any(keyword in normalized for keyword in (
        "半导体", "电子", "计算机", "通信", "软件", "互联网",
    ))


def _percentage_of(value: Decimal, total: Decimal) -> Decimal:
    if total <= Decimal("0"):
        return Decimal("0.00")
    return (value / total * Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def _stable_id(*parts: str) -> str:
    payload = "\x1f".join(parts).encode("utf-8")
    return "exposure:" + sha256(payload).hexdigest()[:32]


class ExposureIssue(ContractModel):
    """Safe explanation for a partial or failed exposure calculation."""

    code: ExposureIssueCode
    safe_message: NonEmptyStr
    asset_id: NonEmptyStr | None = None
    position_id: NonEmptyStr | None = None


class ExposureContribution(ContractModel):
    """One auditable value contribution to an exposure report."""

    exposure_id: NonEmptyStr
    owner_id: NonEmptyStr
    asset_id: NonEmptyStr
    asset_name: NonEmptyStr
    asset_type: AssetType
    sector: NonEmptyStr | None = None
    basis: ExposureBasis
    market_value: Decimal = Field(ge=Decimal("0"))
    portfolio_weight_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    parent_asset_id: NonEmptyStr | None = None
    source_position_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    source_holding_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    source_fund_snapshot_id: NonEmptyStr | None = None
    is_attributed: bool
    is_technology: bool

    @model_validator(mode="after")
    def validate_contribution(self) -> Self:
        if len(set(self.source_position_ids)) != len(self.source_position_ids):
            raise ValueError("source_position_ids must not contain duplicates")
        if len(set(self.source_holding_ids)) != len(self.source_holding_ids):
            raise ValueError("source_holding_ids must not contain duplicates")

        expected_attributed = self.basis != ExposureBasis.UNLOOKED_THROUGH
        if self.is_attributed != expected_attributed:
            raise ValueError("is_attributed does not match contribution basis")
        if self.is_technology != _is_technology_sector(self.sector):
            raise ValueError("is_technology does not match the sector rule")

        if self.basis == ExposureBasis.DIRECT:
            if self.asset_type in {AssetType.ETF, AssetType.MUTUAL_FUND}:
                raise ValueError("fund/ETF values must use look-through or residual basis")
            if self.parent_asset_id is not None:
                raise ValueError("DIRECT contribution must not have a parent_asset_id")
            if self.source_holding_ids or self.source_fund_snapshot_id is not None:
                raise ValueError("DIRECT contribution must not reference fund holdings")
        elif self.basis == ExposureBasis.LOOK_THROUGH:
            if self.parent_asset_id is None:
                raise ValueError("LOOK_THROUGH contribution requires parent_asset_id")
            if not self.source_holding_ids:
                raise ValueError("LOOK_THROUGH contribution requires holding IDs")
            if self.source_fund_snapshot_id is None:
                raise ValueError("LOOK_THROUGH contribution requires fund snapshot ID")
        elif self.basis == ExposureBasis.UNLOOKED_THROUGH:
            if self.parent_asset_id is None:
                raise ValueError("UNLOOKED_THROUGH contribution requires parent_asset_id")
            if self.source_holding_ids:
                raise ValueError("UNLOOKED_THROUGH contribution must not use holding IDs")

        return self


class ExposureReport(ContractModel):
    """Closed deterministic exposure report for one imported bundle."""

    schema_version: Literal["portfolio-exposure.v1"] = "portfolio-exposure.v1"
    report_id: NonEmptyStr
    owner_id: NonEmptyStr
    bundle_id: NonEmptyStr
    calculated_at: datetime
    base_currency: CurrencyCode
    total_market_value: Decimal = Field(gt=Decimal("0"))
    attributed_market_value: Decimal = Field(ge=Decimal("0"))
    unclassified_market_value: Decimal = Field(ge=Decimal("0"))
    technology_market_value: Decimal = Field(ge=Decimal("0"))
    technology_weight_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    contributions: tuple[ExposureContribution, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        _require_timezone(self.calculated_at, "calculated_at")
        if any(
            contribution.owner_id != self.owner_id
            for contribution in self.contributions
        ):
            raise ValueError("contribution owner_id does not match report owner_id")
        contribution_ids = [
            contribution.exposure_id for contribution in self.contributions
        ]
        if len(set(contribution_ids)) != len(contribution_ids):
            raise ValueError("contributions must not contain duplicate exposure_id")

        total_from_contributions = sum(
            (contribution.market_value for contribution in self.contributions),
            Decimal("0"),
        )
        if total_from_contributions != self.total_market_value:
            raise ValueError("contribution market values must close total_market_value")

        attributed = sum(
            (
                contribution.market_value
                for contribution in self.contributions
                if contribution.is_attributed
            ),
            Decimal("0"),
        )
        unclassified = sum(
            (
                contribution.market_value
                for contribution in self.contributions
                if not contribution.is_attributed
            ),
            Decimal("0"),
        )
        if attributed != self.attributed_market_value:
            raise ValueError("attributed_market_value does not close contributions")
        if unclassified != self.unclassified_market_value:
            raise ValueError("unclassified_market_value does not close contributions")
        if attributed + unclassified != self.total_market_value:
            raise ValueError("attributed and unclassified values must close total")

        technology = sum(
            (
                contribution.market_value
                for contribution in self.contributions
                if contribution.is_technology
            ),
            Decimal("0"),
        )
        if technology != self.technology_market_value:
            raise ValueError("technology_market_value does not close contributions")
        if self.technology_weight_pct != _percentage_of(
            self.technology_market_value, self.total_market_value
        ):
            raise ValueError("technology_weight_pct does not match market values")

        for contribution in self.contributions:
            expected_weight = _percentage_of(
                contribution.market_value, self.total_market_value
            )
            if contribution.portfolio_weight_pct != expected_weight:
                raise ValueError(
                    f"contribution {contribution.exposure_id!r} has an invalid portfolio weight"
                )
        return self


class ExposureResult(ContractModel):
    """Three-state calculation result with explicit partial/failure semantics."""

    schema_version: Literal["portfolio-exposure-result.v1"] = (
        "portfolio-exposure-result.v1"
    )
    request_id: NonEmptyStr
    owner_id: NonEmptyStr
    bundle_id: NonEmptyStr
    status: ExposureStatus
    calculated_at: datetime
    report: ExposureReport | None = None
    issues: tuple[ExposureIssue, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        _require_timezone(self.calculated_at, "calculated_at")
        if self.report is not None:
            if self.report.owner_id != self.owner_id:
                raise ValueError("report owner_id does not match result owner_id")
            if self.report.bundle_id != self.bundle_id:
                raise ValueError("report bundle_id does not match result bundle_id")
        issue_keys = [
            (issue.code, issue.asset_id, issue.position_id) for issue in self.issues
        ]
        if len(set(issue_keys)) != len(issue_keys):
            raise ValueError("issues must not contain duplicate context")

        if self.status == ExposureStatus.COMPLETE:
            if self.report is None:
                raise ValueError("COMPLETE exposure requires a report")
            if self.issues:
                raise ValueError("COMPLETE exposure must not carry issues")
            if self.report.unclassified_market_value != Decimal("0"):
                raise ValueError(
                    "COMPLETE exposure must not contain unclassified market value"
                )
        elif self.status == ExposureStatus.PARTIAL:
            if self.report is None:
                raise ValueError("PARTIAL exposure requires a report")
            if not self.issues:
                raise ValueError("PARTIAL exposure requires at least one issue")
        elif self.status == ExposureStatus.FAILED:
            if self.report is not None:
                raise ValueError("FAILED exposure must not carry a report")
            if not self.issues:
                raise ValueError("FAILED exposure requires at least one issue")
        return self


def _issue(
    code: ExposureIssueCode,
    message: str,
    *,
    asset_id: str | None = None,
    position_id: str | None = None,
) -> ExposureIssue:
    return ExposureIssue(
        code=code,
        safe_message=message,
        asset_id=asset_id,
        position_id=position_id,
    )


def _residual_contribution(
    bundle: PortfolioImportBundle,
    position: Position,
    value: Decimal,
    *,
    fund_snapshot: FundHoldingSnapshot | None,
) -> ExposureContribution:
    return ExposureContribution(
        exposure_id=_stable_id(
            bundle.bundle_id,
            position.position_id,
            ExposureBasis.UNLOOKED_THROUGH.value,
            "residual",
        ),
        owner_id=bundle.owner_id,
        asset_id=position.asset_id,
        asset_name=position.asset_name,
        asset_type=position.asset_type,
        basis=ExposureBasis.UNLOOKED_THROUGH,
        market_value=value,
        portfolio_weight_pct=Decimal("0"),
        parent_asset_id=position.asset_id,
        source_position_ids=(position.position_id,),
        source_fund_snapshot_id=(
            fund_snapshot.snapshot_id if fund_snapshot is not None else None
        ),
        is_attributed=False,
        is_technology=False,
    )


def _direct_contribution(
    bundle: PortfolioImportBundle,
    position: Position,
    value: Decimal,
) -> ExposureContribution:
    return ExposureContribution(
        exposure_id=_stable_id(
            bundle.bundle_id,
            position.position_id,
            ExposureBasis.DIRECT.value,
        ),
        owner_id=bundle.owner_id,
        asset_id=position.asset_id,
        asset_name=position.asset_name,
        asset_type=position.asset_type,
        sector=position.sector,
        basis=ExposureBasis.DIRECT,
        market_value=value,
        portfolio_weight_pct=Decimal("0"),
        source_position_ids=(position.position_id,),
        is_attributed=True,
        is_technology=_is_technology_sector(position.sector),
    )


def _look_through_contribution(
    bundle: PortfolioImportBundle,
    position: Position,
    holding_snapshot: FundHoldingSnapshot,
    holding_id: str,
    underlying_asset_id: str,
    underlying_name: str,
    asset_type: AssetType,
    sector: str | None,
    value: Decimal,
) -> ExposureContribution:
    return ExposureContribution(
        exposure_id=_stable_id(
            bundle.bundle_id,
            position.position_id,
            holding_snapshot.snapshot_id,
            holding_id,
            ExposureBasis.LOOK_THROUGH.value,
        ),
        owner_id=bundle.owner_id,
        asset_id=underlying_asset_id,
        asset_name=underlying_name,
        asset_type=asset_type,
        sector=sector,
        basis=ExposureBasis.LOOK_THROUGH,
        market_value=value,
        portfolio_weight_pct=Decimal("0"),
        parent_asset_id=position.asset_id,
        source_position_ids=(position.position_id,),
        source_holding_ids=(holding_id,),
        source_fund_snapshot_id=holding_snapshot.snapshot_id,
        is_attributed=True,
        is_technology=_is_technology_sector(sector),
    )


def _normalise_contributions(
    contributions: Iterable[ExposureContribution],
    total_market_value: Decimal,
) -> tuple[ExposureContribution, ...]:
    return tuple(
        contribution.model_copy(
            update={
                "portfolio_weight_pct": _percentage_of(
                    contribution.market_value, total_market_value
                )
            }
        )
        for contribution in contributions
    )


def calculate_exposure(
    bundle: PortfolioImportBundle,
    *,
    request_id: str | None = None,
    calculated_at: datetime | None = None,
) -> ExposureResult:
    """Calculate direct/look-through values without FX or weight extrapolation."""
    if calculated_at is None:
        calculated_at = bundle.created_at
    _require_timezone(calculated_at, "calculated_at")

    request_id = request_id or f"exposure-request:{bundle.bundle_id}"
    positions = bundle.position_snapshot.positions
    base_currency = bundle.position_snapshot.base_currency
    snapshots_by_parent = {
        snapshot.parent_asset_id: snapshot for snapshot in bundle.fund_holdings
    }
    contributions: list[ExposureContribution] = []
    issues: list[ExposureIssue] = []
    seen_issue_contexts: set[tuple[ExposureIssueCode, str | None, str | None]] = set()
    total_market_value = Decimal("0")

    def add_issue(issue: ExposureIssue) -> None:
        context = (issue.code, issue.asset_id, issue.position_id)
        if context not in seen_issue_contexts:
            seen_issue_contexts.add(context)
            issues.append(issue)

    for position in positions:
        if position.currency != base_currency:
            add_issue(
                _issue(
                    ExposureIssueCode.NON_BASE_CURRENCY,
                    "position currency differs from snapshot base currency; FX was not applied",
                    asset_id=position.asset_id,
                    position_id=position.position_id,
                )
            )
            continue

        value = position.market_value
        total_market_value += value
        if position.asset_type not in {AssetType.ETF, AssetType.MUTUAL_FUND}:
            contributions.append(_direct_contribution(bundle, position, value))
            continue

        holding_snapshot = snapshots_by_parent.get(position.asset_id)
        if holding_snapshot is None:
            add_issue(
                _issue(
                    ExposureIssueCode.MISSING_LOOK_THROUGH,
                    "fund/ETF look-through snapshot is unavailable; value kept as residual",
                    asset_id=position.asset_id,
                    position_id=position.position_id,
                )
            )
            contributions.append(
                _residual_contribution(bundle, position, value, fund_snapshot=None)
            )
            continue

        if holding_snapshot.as_of > bundle.position_snapshot.as_of or any(
            holding.as_of > bundle.position_snapshot.as_of
            for holding in holding_snapshot.holdings
        ):
            add_issue(
                _issue(
                    ExposureIssueCode.FUTURE_HOLDINGS,
                    "fund/ETF holdings snapshot is later than the position snapshot",
                    asset_id=position.asset_id,
                    position_id=position.position_id,
                )
            )
            contributions.append(
                _residual_contribution(
                    bundle, position, value, fund_snapshot=holding_snapshot
                )
            )
            continue

        represented_value = Decimal("0")
        for holding in holding_snapshot.holdings:
            holding_value = value * holding.weight_pct / Decimal("100")
            represented_value += holding_value
            contributions.append(
                _look_through_contribution(
                    bundle,
                    position,
                    holding_snapshot,
                    holding.holding_id,
                    holding.underlying_asset_id,
                    holding.underlying_name,
                    holding.asset_type,
                    holding.sector,
                    holding_value,
                )
            )

        residual_value = value - represented_value
        if residual_value > Decimal("0"):
            add_issue(
                _issue(
                    ExposureIssueCode.INCOMPLETE_LOOK_THROUGH,
                    "fund/ETF holdings do not cover the full parent value; residual was retained",
                    asset_id=position.asset_id,
                    position_id=position.position_id,
                )
            )
            contributions.append(
                _residual_contribution(
                    bundle, position, residual_value, fund_snapshot=holding_snapshot
                )
            )
        elif holding_snapshot.coverage_pct < Decimal("100"):
            add_issue(
                _issue(
                    ExposureIssueCode.INCOMPLETE_LOOK_THROUGH,
                    "fund/ETF source coverage is below 100 percent",
                    asset_id=position.asset_id,
                    position_id=position.position_id,
                )
            )

    if total_market_value <= Decimal("0"):
        add_issue(
            _issue(
                ExposureIssueCode.ZERO_PORTFOLIO_VALUE,
                "no positive base-currency market value was available for exposure calculation",
            )
        )
        return ExposureResult(
            request_id=request_id,
            owner_id=bundle.owner_id,
            bundle_id=bundle.bundle_id,
            status=ExposureStatus.FAILED,
            calculated_at=calculated_at,
            issues=tuple(issues),
        )

    normalised = _normalise_contributions(contributions, total_market_value)
    attributed_value = sum(
        (contribution.market_value for contribution in normalised if contribution.is_attributed),
        Decimal("0"),
    )
    unclassified_value = sum(
        (contribution.market_value for contribution in normalised if not contribution.is_attributed),
        Decimal("0"),
    )
    technology_value = sum(
        (contribution.market_value for contribution in normalised if contribution.is_technology),
        Decimal("0"),
    )
    report = ExposureReport(
        report_id=_stable_id(bundle.bundle_id, "report"),
        owner_id=bundle.owner_id,
        bundle_id=bundle.bundle_id,
        calculated_at=calculated_at,
        base_currency=base_currency,
        total_market_value=total_market_value,
        attributed_market_value=attributed_value,
        unclassified_market_value=unclassified_value,
        technology_market_value=technology_value,
        technology_weight_pct=_percentage_of(technology_value, total_market_value),
        contributions=normalised,
    )
    return ExposureResult(
        request_id=request_id,
        owner_id=bundle.owner_id,
        bundle_id=bundle.bundle_id,
        status=ExposureStatus.PARTIAL if issues else ExposureStatus.COMPLETE,
        calculated_at=calculated_at,
        report=report,
        issues=tuple(issues),
    )
