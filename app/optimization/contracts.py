"""Strict contracts for deterministic portfolio target proposals.

The optimization card is intentionally a target-structure proposal.  It is
not a recommendation, order, or claim of return/risk optimality.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, model_validator

from app.contracts.evidence import ContractModel, NonEmptyStr
from app.portfolio import PortfolioImportBundle
from app.profile import RiskLevel, RiskProfile, RiskQuestionnaire
from app.providers import FrozenDict
from app.risk import BudgetAssessmentStatus


METHODOLOGY_VERSION = "CAP_AND_REDISTRIBUTE_V1"
_SENSITIVE_SUBSTRINGS = (
    "api_key",
    "apikey",
    "authorization",
    "password",
    "private_key",
    "secret",
    "token",
    "credential",
    "cookie",
)


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _sensitive(serialized: str) -> bool:
    normalized = serialized.casefold().replace("-", "_")
    return any(token in normalized for token in _SENSITIVE_SUBSTRINGS)


def _pct(value: Decimal, field_name: str) -> None:
    if value < Decimal("0") or value > Decimal("100"):
        raise ValueError(f"{field_name} must be between 0 and 100")


class OptimizationScenarioId(StrEnum):
    BASELINE_READY = "BASELINE_READY"
    SOURCE_PARTIAL = "SOURCE_PARTIAL"
    INFEASIBLE = "INFEASIBLE"


class OptimizationStatus(StrEnum):
    READY = "READY"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"


class OptimizationIssueCode(StrEnum):
    INPUT_PARTIAL = "INPUT_PARTIAL"
    INPUT_FAILED = "INPUT_FAILED"
    INPUT_UNCLASSIFIED = "INPUT_UNCLASSIFIED"
    NON_BASE_CURRENCY = "NON_BASE_CURRENCY"
    INFEASIBLE_CONSTRAINTS = "INFEASIBLE_CONSTRAINTS"
    INVALID_SCENARIO = "INVALID_SCENARIO"


class OptimizationDimension(StrEnum):
    ASSET = "ASSET"
    SECTOR = "SECTOR"
    TECHNOLOGY = "TECHNOLOGY"
    UNCLASSIFIED = "UNCLASSIFIED"


class OptimizationDisposition(StrEnum):
    WITHIN_LIMIT = "WITHIN_LIMIT"
    REPAIRED = "REPAIRED"
    OVER_LIMIT = "OVER_LIMIT"
    UNRESOLVED = "UNRESOLVED"


class OptimizationScenarioDefinition(ContractModel):
    scenario_id: OptimizationScenarioId
    label: NonEmptyStr
    description: NonEmptyStr

    @model_validator(mode="after")
    def validate_definition(self) -> Self:
        if _sensitive(self.model_dump_json()):
            raise ValueError("optimization scenario must not contain sensitive metadata")
        return self


class OptimizationRuleResponse(ContractModel):
    dimension: OptimizationDimension
    label: NonEmptyStr
    description: NonEmptyStr
    limit_by_risk_level: FrozenDict

    @model_validator(mode="after")
    def validate_rule(self) -> Self:
        normalized_levels = {RiskLevel(str(key)) for key in self.limit_by_risk_level}
        if normalized_levels != set(RiskLevel):
            raise ValueError("optimization rule must define every risk level")
        for risk_level, value in self.limit_by_risk_level.items():
            _pct(Decimal(str(value)), f"limit_by_risk_level[{risk_level}]")
        if _sensitive(self.model_dump_json()):
            raise ValueError("optimization rule must not contain sensitive metadata")
        return self


class PortfolioOptimizationRequest(ContractModel):
    schema_version: Literal["portfolio-optimization-request.v1"] = (
        "portfolio-optimization-request.v1"
    )
    request_id: NonEmptyStr
    owner_id: NonEmptyStr
    generated_at: datetime
    questionnaire: RiskQuestionnaire
    portfolio: PortfolioImportBundle
    scenario_id: OptimizationScenarioId = OptimizationScenarioId.BASELINE_READY
    minimum_cash_pct: Decimal = Field(default=Decimal("0.00"), ge=0, le=100)
    confirmed_profile: RiskProfile | None = None

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        _aware(self.generated_at, "generated_at")
        if self.questionnaire.owner_id != self.owner_id:
            raise ValueError("questionnaire owner_id does not match request owner_id")
        if self.confirmed_profile is not None and self.confirmed_profile.owner_id != self.owner_id:
            raise ValueError("confirmed profile owner does not match request owner")
        if self.portfolio.owner_id != self.owner_id:
            raise ValueError("portfolio owner_id does not match request owner_id")
        if _sensitive(self.model_dump_json()):
            raise ValueError("optimization request must not contain sensitive fields")
        return self


class OptimizationIssue(ContractModel):
    code: OptimizationIssueCode
    safe_message: NonEmptyStr
    dimension: OptimizationDimension | None = None
    target_id: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_issue(self) -> Self:
        if self.dimension in {
            OptimizationDimension.ASSET,
            OptimizationDimension.SECTOR,
        } and self.target_id is None:
            raise ValueError("asset/sector optimization issue requires target_id")
        if _sensitive(self.model_dump_json()):
            raise ValueError("optimization issue must not contain sensitive fields")
        return self


class OptimizationConstraint(ContractModel):
    """One current/target view of a deterministic budget constraint."""

    constraint_id: NonEmptyStr
    owner_id: NonEmptyStr
    dimension: OptimizationDimension
    target_id: NonEmptyStr | None = None
    label: NonEmptyStr
    current_weight_pct: Decimal
    target_weight_pct: Decimal
    allowed_max_weight_pct: Decimal
    delta_pct: Decimal
    disposition: OptimizationDisposition
    rationale: NonEmptyStr

    @model_validator(mode="after")
    def validate_constraint(self) -> Self:
        for name, value in (
            ("current_weight_pct", self.current_weight_pct),
            ("target_weight_pct", self.target_weight_pct),
            ("allowed_max_weight_pct", self.allowed_max_weight_pct),
        ):
            _pct(value, name)
        if self.delta_pct != self.target_weight_pct - self.current_weight_pct:
            raise ValueError("optimization constraint delta does not close weights")
        if self.dimension in {
            OptimizationDimension.ASSET,
            OptimizationDimension.SECTOR,
        } and self.target_id is None:
            raise ValueError("asset/sector constraint requires target_id")
        if self.dimension in {
            OptimizationDimension.TECHNOLOGY,
            OptimizationDimension.UNCLASSIFIED,
        } and self.target_id is not None:
            raise ValueError("aggregate constraint must not have target_id")
        if self.disposition in {
            OptimizationDisposition.WITHIN_LIMIT,
            OptimizationDisposition.REPAIRED,
        } and self.target_weight_pct > self.allowed_max_weight_pct:
            raise ValueError("resolved constraint target exceeds its limit")
        if self.disposition == OptimizationDisposition.REPAIRED and (
            self.current_weight_pct <= self.allowed_max_weight_pct
        ):
            raise ValueError("REPAIRED constraint must have exceeded its current limit")
        if self.disposition == OptimizationDisposition.WITHIN_LIMIT and (
            self.current_weight_pct > self.allowed_max_weight_pct
        ):
            raise ValueError("WITHIN_LIMIT constraint must not exceed current limit")
        if _sensitive(self.model_dump_json()):
            raise ValueError("optimization constraint must not contain sensitive fields")
        return self


class OptimizationTarget(ContractModel):
    """Target percentage for one observed exposure asset."""

    target_id: NonEmptyStr
    owner_id: NonEmptyStr
    asset_name: NonEmptyStr
    sector: NonEmptyStr | None = None
    current_weight_pct: Decimal
    target_weight_pct: Decimal
    delta_pct: Decimal
    allowed_max_weight_pct: Decimal
    constraint_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    rationale: NonEmptyStr

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        for name, value in (
            ("current_weight_pct", self.current_weight_pct),
            ("target_weight_pct", self.target_weight_pct),
            ("allowed_max_weight_pct", self.allowed_max_weight_pct),
        ):
            _pct(value, name)
        if self.delta_pct != self.target_weight_pct - self.current_weight_pct:
            raise ValueError("optimization target delta does not close weights")
        if self.target_weight_pct > self.allowed_max_weight_pct:
            raise ValueError("optimization target exceeds single-asset limit")
        if len(set(self.constraint_ids)) != len(self.constraint_ids):
            raise ValueError("optimization target constraint IDs must be unique")
        if _sensitive(self.model_dump_json()):
            raise ValueError("optimization target must not contain sensitive fields")
        return self


class OptimizationTrace(ContractModel):
    schema_version: Literal["portfolio-optimization-trace.v1"] = (
        "portfolio-optimization-trace.v1"
    )
    owner_id: NonEmptyStr
    profile_id: NonEmptyStr
    portfolio_bundle_id: NonEmptyStr
    position_snapshot_id: NonEmptyStr
    exposure_report_id: NonEmptyStr | None = None
    concentration_report_id: NonEmptyStr | None = None
    assessment_id: NonEmptyStr | None = None
    methodology_version: Literal["CAP_AND_REDISTRIBUTE_V1"] = METHODOLOGY_VERSION
    source_contribution_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    calculation_steps: tuple[NonEmptyStr, ...] = Field(min_length=1)
    invalidation_conditions: tuple[NonEmptyStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_trace(self) -> Self:
        if self.exposure_report_id is None and self.source_contribution_ids:
            raise ValueError("trace contributions require an exposure report")
        if len(set(self.source_contribution_ids)) != len(self.source_contribution_ids):
            raise ValueError("trace contribution IDs must be unique")
        if _sensitive(self.model_dump_json()):
            raise ValueError("optimization trace must not contain sensitive fields")
        return self


class PortfolioOptimizationResponse(ContractModel):
    schema_version: Literal["portfolio-optimization-response.v1"] = (
        "portfolio-optimization-response.v1"
    )
    request_id: NonEmptyStr
    owner_id: NonEmptyStr
    generated_at: datetime
    scenario: OptimizationScenarioDefinition
    profile_id: NonEmptyStr
    profile_version: int = Field(ge=1)
    risk_level: RiskLevel
    portfolio_bundle_id: NonEmptyStr
    position_snapshot_id: NonEmptyStr
    exposure_report_id: NonEmptyStr | None = None
    concentration_report_id: NonEmptyStr | None = None
    assessment_id: NonEmptyStr | None = None
    assessment_status: BudgetAssessmentStatus | None = None
    methodology_version: Literal["CAP_AND_REDISTRIBUTE_V1"] = METHODOLOGY_VERSION
    status: OptimizationStatus
    summary: NonEmptyStr
    targets: tuple[OptimizationTarget, ...] = Field(default_factory=tuple)
    constraints: tuple[OptimizationConstraint, ...] = Field(default_factory=tuple)
    issues: tuple[OptimizationIssue, ...] = Field(default_factory=tuple)
    invalidation_conditions: tuple[NonEmptyStr, ...] = Field(min_length=1)
    trace: OptimizationTrace

    @model_validator(mode="after")
    def validate_response(self) -> Self:
        _aware(self.generated_at, "generated_at")
        if self.trace.owner_id != self.owner_id:
            raise ValueError("optimization trace owner does not match response")
        if self.trace.profile_id != self.profile_id:
            raise ValueError("optimization trace profile does not match response")
        if self.trace.portfolio_bundle_id != self.portfolio_bundle_id:
            raise ValueError("optimization trace bundle does not match response")
        if self.trace.position_snapshot_id != self.position_snapshot_id:
            raise ValueError("optimization trace snapshot does not match response")
        if self.trace.exposure_report_id != self.exposure_report_id:
            raise ValueError("optimization trace exposure does not match response")
        if self.trace.concentration_report_id != self.concentration_report_id:
            raise ValueError("optimization trace concentration does not match response")
        if self.trace.assessment_id != self.assessment_id:
            raise ValueError("optimization trace assessment does not match response")
        if tuple(self.invalidation_conditions) != tuple(self.trace.invalidation_conditions):
            raise ValueError("response invalidation conditions do not match trace")

        target_ids = [item.target_id for item in self.targets]
        if target_ids != sorted(target_ids) or len(target_ids) != len(set(target_ids)):
            raise ValueError("optimization targets must be unique and sorted")
        if any(tuple(item.constraint_ids) != tuple(sorted(item.constraint_ids)) for item in self.targets):
            raise ValueError("optimization target constraint IDs must be sorted")
        constraint_ids = [item.constraint_id for item in self.constraints]
        if constraint_ids != sorted(constraint_ids) or len(constraint_ids) != len(set(constraint_ids)):
            raise ValueError("optimization constraints must be unique and sorted")
        if any(item.owner_id != self.owner_id for item in (*self.targets, *self.constraints)):
            raise ValueError("optimization row owner does not match response")
        if self.status == OptimizationStatus.READY:
            if not self.targets:
                raise ValueError("READY optimization requires targets")
            if self.issues:
                raise ValueError("READY optimization must not carry issues")
            target_total = sum((item.target_weight_pct for item in self.targets), Decimal("0"))
            if target_total != Decimal("100.00"):
                raise ValueError("READY optimization targets must sum to 100.00 percent")
            if self.exposure_report_id is None or self.concentration_report_id is None or self.assessment_id is None:
                raise ValueError("READY optimization requires closed report identities")
            if self.assessment_status is None:
                raise ValueError("READY optimization requires assessment status")
            constraints_by_id = {item.constraint_id: item for item in self.constraints}
            targets_by_id = {item.target_id: item for item in self.targets}
            asset_constraints = {
                item.target_id: item
                for item in self.constraints
                if item.dimension == OptimizationDimension.ASSET and item.target_id is not None
            }
            sector_constraints = {
                item.target_id: item
                for item in self.constraints
                if item.dimension == OptimizationDimension.SECTOR and item.target_id is not None
            }
            aggregate_constraints = {
                item.dimension: item
                for item in self.constraints
                if item.dimension in {
                    OptimizationDimension.TECHNOLOGY,
                    OptimizationDimension.UNCLASSIFIED,
                }
            }
            if set(asset_constraints) != set(targets_by_id):
                raise ValueError("optimization asset constraints must cover every target")
            if set(aggregate_constraints) != {
                OptimizationDimension.TECHNOLOGY,
                OptimizationDimension.UNCLASSIFIED,
            }:
                raise ValueError("optimization aggregate constraints are incomplete")
            if not sector_constraints:
                raise ValueError("optimization sector constraints are required")

            def _sector_key(value: str | None) -> str:
                if not value or not value.strip():
                    return "UNCLASSIFIED"
                normalized = value.strip().casefold()
                return "UNCLASSIFIED" if normalized == "unclassified" else normalized

            target_sector_totals: dict[str, Decimal] = {}
            for target in self.targets:
                key = _sector_key(target.sector)
                target_sector_totals[key] = target_sector_totals.get(key, Decimal("0")) + target.target_weight_pct
            target_current_sector_totals: dict[str, Decimal] = {}
            for target in self.targets:
                key = _sector_key(target.sector)
                target_current_sector_totals[key] = target_current_sector_totals.get(key, Decimal("0")) + target.current_weight_pct

            technology = aggregate_constraints[OptimizationDimension.TECHNOLOGY]
            unclassified = aggregate_constraints[OptimizationDimension.UNCLASSIFIED]

            if set(sector_constraints) != set(target_sector_totals):
                raise ValueError("optimization sector constraints must cover every target sector")

            for target_id, target in targets_by_id.items():
                constraint = asset_constraints[target_id]
                if (
                    constraint.current_weight_pct != target.current_weight_pct
                    or constraint.target_weight_pct != target.target_weight_pct
                    or constraint.allowed_max_weight_pct != target.allowed_max_weight_pct
                    or constraint.delta_pct != target.delta_pct
                ):
                    raise ValueError("asset constraint does not close its target row")
                if any(item_id not in constraints_by_id for item_id in target.constraint_ids):
                    raise ValueError("optimization target references an unknown constraint")
                if constraint.constraint_id not in target.constraint_ids:
                    raise ValueError("optimization target must reference its asset constraint")
                sector_key = _sector_key(target.sector)
                sector_constraint = sector_constraints.get(sector_key)
                if sector_constraint is None or sector_constraint.constraint_id not in target.constraint_ids:
                    raise ValueError("optimization target must reference its sector constraint")
                expected_constraint_ids = {
                    constraint.constraint_id,
                    sector_constraint.constraint_id,
                }
                if sector_key in {"technology", "information technology", "tech"}:
                    if technology.constraint_id not in target.constraint_ids:
                        raise ValueError("technology target must reference its aggregate constraint")
                    expected_constraint_ids.add(technology.constraint_id)
                if sector_key == "UNCLASSIFIED":
                    if unclassified.constraint_id not in target.constraint_ids:
                        raise ValueError("unclassified target must reference its aggregate constraint")
                    expected_constraint_ids.add(unclassified.constraint_id)
                if set(target.constraint_ids) != expected_constraint_ids:
                    raise ValueError("optimization target constraint references are not exact")

            for sector_key, constraint in sector_constraints.items():
                if constraint.target_weight_pct != target_sector_totals.get(sector_key, Decimal("0")):
                    raise ValueError("sector constraint target does not close target rows")
                if constraint.current_weight_pct != target_current_sector_totals.get(sector_key, Decimal("0")):
                    raise ValueError("sector constraint current weight does not close target rows")

            expected_technology_target = sum(
                (target.target_weight_pct for target in self.targets if _sector_key(target.sector) in {"technology", "information technology", "tech"}),
                Decimal("0"),
            )
            expected_technology_current = sum(
                (target.current_weight_pct for target in self.targets if _sector_key(target.sector) in {"technology", "information technology", "tech"}),
                Decimal("0"),
            )
            expected_unclassified_target = sum(
                (target.target_weight_pct for target in self.targets if _sector_key(target.sector) == "UNCLASSIFIED"),
                Decimal("0"),
            )
            expected_unclassified_current = sum(
                (target.current_weight_pct for target in self.targets if _sector_key(target.sector) == "UNCLASSIFIED"),
                Decimal("0"),
            )
            if (
                technology.target_weight_pct != expected_technology_target
                or technology.current_weight_pct != expected_technology_current
                or unclassified.target_weight_pct != expected_unclassified_target
                or unclassified.current_weight_pct != expected_unclassified_current
            ):
                raise ValueError("aggregate constraint weights do not close target rows")
            referenced_constraint_ids = {
                constraint_id
                for target in self.targets
                for constraint_id in target.constraint_ids
            }
            represented_technology = any(
                _sector_key(target.sector)
                in {"technology", "information technology", "tech"}
                for target in self.targets
            )
            represented_unclassified = any(
                _sector_key(target.sector) == "UNCLASSIFIED" for target in self.targets
            )
            zero_only_aggregate_ids = {
                aggregate.constraint_id
                for represented, aggregate in (
                    (represented_technology, technology),
                    (represented_unclassified, unclassified),
                )
                if not represented
            }
            for aggregate_id in zero_only_aggregate_ids:
                aggregate = constraints_by_id[aggregate_id]
                if (
                    aggregate.current_weight_pct != Decimal("0.00")
                    or aggregate.target_weight_pct != Decimal("0.00")
                ):
                    raise ValueError("unrepresented aggregate constraint must be zero")
            if referenced_constraint_ids | zero_only_aggregate_ids != set(constraints_by_id):
                raise ValueError("optimization constraints must be fully referenced by targets")
            has_current_breach = any(
                item.current_weight_pct > item.allowed_max_weight_pct
                for item in self.constraints
            )
            expected_assessment_status = (
                BudgetAssessmentStatus.REVIEW_REQUIRED
                if has_current_breach
                else BudgetAssessmentStatus.PASS
            )
            if self.assessment_status != expected_assessment_status:
                raise ValueError("optimization assessment status does not match current constraints")
        else:
            if self.targets:
                raise ValueError("non-ready optimization must not expose targets")
            if self.constraints:
                raise ValueError("non-ready optimization must not expose constraints")
            if not self.issues:
                raise ValueError("non-ready optimization requires an issue")
        if _sensitive(self.model_dump_json()):
            raise ValueError("optimization response must not contain sensitive fields")
        return self


class PortfolioOptimizationTemplateResponse(ContractModel):
    schema_version: Literal["portfolio-optimization-template.v1"] = (
        "portfolio-optimization-template.v1"
    )
    manifest_id: NonEmptyStr
    owner_id: NonEmptyStr
    generated_at: datetime
    methodology_version: Literal["CAP_AND_REDISTRIBUTE_V1"] = METHODOLOGY_VERSION
    scope_description: NonEmptyStr
    questionnaire: RiskQuestionnaire
    portfolio: PortfolioImportBundle
    rules: tuple[OptimizationRuleResponse, ...] = Field(min_length=4)
    scenarios: tuple[OptimizationScenarioDefinition, ...] = Field(min_length=3)

    @model_validator(mode="after")
    def validate_template(self) -> Self:
        _aware(self.generated_at, "generated_at")
        if self.questionnaire.owner_id != self.owner_id:
            raise ValueError("optimization template questionnaire owner mismatch")
        if self.portfolio.owner_id != self.owner_id:
            raise ValueError("optimization template portfolio owner mismatch")
        scenario_ids = [item.scenario_id for item in self.scenarios]
        if scenario_ids != sorted(scenario_ids) or len(set(scenario_ids)) != len(scenario_ids):
            raise ValueError("optimization template scenarios must be unique and sorted")
        if set(scenario_ids) != set(OptimizationScenarioId):
            raise ValueError("optimization template must cover every scenario")
        dimensions = [item.dimension for item in self.rules]
        if len(set(dimensions)) != len(dimensions):
            raise ValueError("optimization template rules must be unique by dimension")
        if _sensitive(self.model_dump_json()):
            raise ValueError("optimization template must not contain sensitive fields")
        return self


__all__ = [
    "METHODOLOGY_VERSION",
    "OptimizationConstraint",
    "OptimizationDimension",
    "OptimizationDisposition",
    "OptimizationIssue",
    "OptimizationIssueCode",
    "OptimizationRuleResponse",
    "OptimizationScenarioDefinition",
    "OptimizationScenarioId",
    "OptimizationStatus",
    "OptimizationTarget",
    "OptimizationTrace",
    "PortfolioOptimizationRequest",
    "PortfolioOptimizationResponse",
    "PortfolioOptimizationTemplateResponse",
]
