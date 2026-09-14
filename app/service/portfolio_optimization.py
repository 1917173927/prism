"""Fixture-first deterministic portfolio target proposals."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from hashlib import sha256
from pathlib import Path

from app.optimization import (
    METHODOLOGY_VERSION,
    OptimizationConstraint,
    OptimizationDimension,
    OptimizationDisposition,
    OptimizationIssue,
    OptimizationIssueCode,
    OptimizationRuleResponse,
    OptimizationScenarioDefinition,
    OptimizationScenarioId,
    OptimizationStatus,
    OptimizationTarget,
    OptimizationTrace,
    PortfolioOptimizationRequest,
    PortfolioOptimizationResponse,
    PortfolioOptimizationTemplateResponse,
)
from app.portfolio import (
    AssetType,
    ExposureBasis,
    ExposureResult,
    ExposureStatus,
    PortfolioImportBundle,
    calculate_exposure,
)
from app.profile import (
    ExperienceLevel,
    InvestmentHorizon,
    LiquidityNeed,
    ReturnExpectation,
    RiskLevel,
    RiskProfile,
    RiskQuestionnaire,
)
from app.risk import (
    BudgetAssessmentStatus,
    ConcentrationResult,
    ConcentrationStatus,
    RiskBudgetAssessment,
    assess_risk_budget,
    calculate_concentration,
)
from app.service.profile_confirmation import confirm_questionnaire


_DEFAULT_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "optimization"
_DEFAULT_TEMPLATE = _DEFAULT_ROOT / "portfolio_optimization_template.json"
_CENT = Decimal("0.01")
_UNCLASSIFIED_SECTOR = "UNCLASSIFIED"
_TECHNOLOGY_SECTORS = {"technology", "information technology", "tech"}


class PortfolioOptimizationError(RuntimeError):
    """A safe refusal while loading or calculating an optimization fixture."""


def _stable_id(prefix: str, *parts: str) -> str:
    payload = "\x1f".join(parts).encode("utf-8")
    return f"{prefix}:" + sha256(payload).hexdigest()[:32]


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _cents(value: Decimal) -> int:
    return int(value.quantize(_CENT, rounding=ROUND_HALF_UP) * 100)


def _from_cents(value: int) -> Decimal:
    return (Decimal(value) / Decimal("100")).quantize(_CENT)


def _normal_key(value: str | None) -> str:
    if not value or not value.strip():
        return _UNCLASSIFIED_SECTOR
    normalized = value.strip().casefold()
    return _UNCLASSIFIED_SECTOR if normalized == "unclassified" else normalized


def _is_technology(sector: str | None) -> bool:
    return _normal_key(sector) in _TECHNOLOGY_SECTORS


def _largest_remainder_weights(
    values: dict[str, Decimal],
    total_value: Decimal,
) -> dict[str, int]:
    """Convert positive values to deterministic percentage cents totaling 10000."""
    if total_value <= 0 or not values:
        raise PortfolioOptimizationError("optimization weights have no positive total")
    raw: dict[str, Decimal] = {
        key: value / total_value * Decimal("10000")
        for key, value in values.items()
    }
    floors = {key: int(value.to_integral_value(rounding=ROUND_DOWN)) for key, value in raw.items()}
    remaining = 10000 - sum(floors.values())
    order = sorted(
        raw,
        key=lambda key: (-(raw[key] - Decimal(floors[key])), key),
    )
    for key in order[:remaining]:
        floors[key] += 1
    return floors


def _allocate_cents(
    target_cents: int,
    values: dict[str, Decimal],
    caps: dict[str, int],
) -> dict[str, int]:
    """Proportionally allocate a bucket with deterministic largest remainders."""
    if target_cents < 0 or not values:
        raise PortfolioOptimizationError("optimization bucket has no allocable assets")
    total_value = sum(values.values(), Decimal("0"))
    if total_value <= 0:
        raise PortfolioOptimizationError("optimization bucket has no positive value")
    if target_cents > sum(caps.values()):
        raise PortfolioOptimizationError("optimization bucket exceeds asset capacity")

    raw = {
        key: Decimal(target_cents) * value / total_value
        for key, value in values.items()
    }
    allocation = {
        key: min(caps[key], int(value.to_integral_value(rounding=ROUND_DOWN)))
        for key, value in raw.items()
    }
    # Capping an initially proportional allocation can leave more room than the
    # ordinary largest-remainder pass.  Repeated one-cent passes keep the
    # result exact while retaining a transparent deterministic rule.
    left = target_cents - sum(allocation.values())
    while left:
        candidates = [key for key in values if allocation[key] < caps[key]]
        if not candidates:
            raise PortfolioOptimizationError("optimization bucket cannot close to 100 percent")
        candidates.sort(
            key=lambda key: (
                -(raw[key] - Decimal(int(raw[key].to_integral_value(rounding=ROUND_DOWN)))),
                key,
            )
        )
        progressed = False
        for key in candidates:
            if left <= 0:
                break
            if allocation[key] >= caps[key]:
                continue
            allocation[key] += 1
            left -= 1
            progressed = True
        if not progressed:
            raise PortfolioOptimizationError("optimization bucket could not absorb rounding remainder")
    return allocation


def _scenario_definition(scenario_id: OptimizationScenarioId) -> OptimizationScenarioDefinition:
    definitions = {
        OptimizationScenarioId.BASELINE_READY: (
            "BASELINE_READY",
            "complete multi-asset snapshot",
        ),
        OptimizationScenarioId.SOURCE_PARTIAL: (
            "SOURCE_PARTIAL",
            "fund look-through coverage is below 100 percent",
        ),
        OptimizationScenarioId.INFEASIBLE: (
            "INFEASIBLE",
            "one-asset concentration cannot satisfy every configured cap",
        ),
    }
    label, description = definitions[scenario_id]
    return OptimizationScenarioDefinition(
        scenario_id=scenario_id,
        label=label,
        description=description,
    )


class FixturePortfolioOptimizationService:
    """Calculate one bounded, offline target proposal for an owner."""

    def __init__(self, *, template_path: str | Path = _DEFAULT_TEMPLATE) -> None:
        self._template_path = Path(template_path)
        try:
            payload = json.loads(self._template_path.read_text(encoding="utf-8"))
            self._template = PortfolioOptimizationTemplateResponse.model_validate(payload)
        except Exception as exc:
            raise PortfolioOptimizationError("portfolio optimization fixture could not be loaded") from exc
        self.manifest_id = self._template.manifest_id

    @staticmethod
    def _rebind_portfolio(portfolio: PortfolioImportBundle, owner_id: str) -> PortfolioImportBundle:
        snapshot = portfolio.position_snapshot
        positions = tuple(position.model_copy(update={"owner_id": owner_id}) for position in snapshot.positions)
        rebound_snapshot = snapshot.model_copy(update={"owner_id": owner_id, "positions": positions})
        funds = tuple(
            fund.model_copy(
                update={
                    "owner_id": owner_id,
                    "holdings": tuple(fund.holdings),
                }
            )
            for fund in portfolio.fund_holdings
        )
        return PortfolioImportBundle.model_validate(
            portfolio.model_copy(
                update={
                    "owner_id": owner_id,
                    "position_snapshot": rebound_snapshot,
                    "fund_holdings": funds,
                }
            ).model_dump(mode="python")
        )

    @classmethod
    def _scenario_portfolio(
        cls,
        portfolio: PortfolioImportBundle,
        scenario_id: OptimizationScenarioId,
    ) -> PortfolioImportBundle:
        if scenario_id == OptimizationScenarioId.BASELINE_READY:
            return portfolio
        if scenario_id == OptimizationScenarioId.SOURCE_PARTIAL:
            if not portfolio.fund_holdings:
                return portfolio
            funds = tuple(
                fund.model_copy(update={"coverage_pct": Decimal("80")})
                for fund in portfolio.fund_holdings
            )
            return PortfolioImportBundle.model_validate(
                portfolio.model_copy(update={"fund_holdings": funds}).model_dump(mode="python")
            )

        # The infeasible replay deliberately keeps the submitted bundle and
        # owner identities while reducing it to the first observed position.
        # It is a bounded fixture scenario, not a mutation of persisted data.
        first_position = portfolio.position_snapshot.positions[0]
        first_position_snapshot = portfolio.position_snapshot.model_copy(
            update={"positions": (first_position,)}
        )
        funds = tuple(
            fund
            for fund in portfolio.fund_holdings
            if fund.parent_asset_id == first_position.asset_id
        )
        if funds:
            first_fund = funds[0]
            first_holding = first_fund.holdings[0]
            first_fund = first_fund.model_copy(
                update={
                    "holdings": (
                        first_holding.model_copy(update={"weight_pct": Decimal("100")}),
                    ),
                    "coverage_pct": Decimal("100"),
                }
            )
            funds = (first_fund,)
        return PortfolioImportBundle.model_validate(
            portfolio.model_copy(
                update={
                    "position_snapshot": first_position_snapshot,
                    "fund_holdings": funds,
                }
            ).model_dump(mode="python")
        )

    def template(self, owner_id: str) -> PortfolioOptimizationTemplateResponse:
        try:
            questionnaire = self._template.questionnaire.model_copy(update={"owner_id": owner_id})
            portfolio = self._rebind_portfolio(self._template.portfolio, owner_id)
            return PortfolioOptimizationTemplateResponse.model_validate(
                self._template.model_copy(
                    update={
                        "owner_id": owner_id,
                        "questionnaire": questionnaire,
                        "portfolio": portfolio,
                    }
                ).model_dump(mode="python")
            )
        except Exception as exc:
            raise PortfolioOptimizationError("portfolio optimization template was refused") from exc

    @staticmethod
    def _failure_response(
        request: PortfolioOptimizationRequest,
        portfolio: PortfolioImportBundle,
        profile_id: str,
        profile_version: int,
        risk_level: RiskLevel,
        scenario: OptimizationScenarioDefinition,
        status: OptimizationStatus,
        summary: str,
        issues: tuple[OptimizationIssue, ...],
        *,
        exposure_report_id: str | None = None,
        concentration_report_id: str | None = None,
        assessment_id: str | None = None,
        assessment_status: BudgetAssessmentStatus | None = None,
        contribution_ids: tuple[str, ...] = (),
    ) -> PortfolioOptimizationResponse:
        invalidation = (
            "Risk Profile version or risk budget rule changes",
            "portfolio bundle or position snapshot changes",
            "fund look-through coverage or base currency changes",
            "CAP_AND_REDISTRIBUTE_V1 methodology changes",
        )
        trace = OptimizationTrace(
            owner_id=request.owner_id,
            profile_id=profile_id,
            portfolio_bundle_id=portfolio.bundle_id,
            position_snapshot_id=portfolio.position_snapshot.snapshot_id,
            exposure_report_id=exposure_report_id,
            concentration_report_id=concentration_report_id,
            assessment_id=assessment_id,
            source_contribution_ids=contribution_ids,
            calculation_steps=(
                "validate owner, profile and portfolio input",
                "calculate exposure, concentration and profile-conditioned risk budget",
                "preserve review or blocked state when inputs are incomplete or infeasible",
            ),
            invalidation_conditions=invalidation,
        )
        return PortfolioOptimizationResponse(
            request_id=request.request_id,
            owner_id=request.owner_id,
            generated_at=request.generated_at,
            scenario=scenario,
            profile_id=profile_id,
            profile_version=profile_version,
            risk_level=risk_level,
            portfolio_bundle_id=portfolio.bundle_id,
            position_snapshot_id=portfolio.position_snapshot.snapshot_id,
            exposure_report_id=exposure_report_id,
            concentration_report_id=concentration_report_id,
            assessment_id=assessment_id,
            assessment_status=assessment_status,
            status=status,
            summary=summary,
            issues=issues,
            invalidation_conditions=invalidation,
            trace=trace,
        )

    @staticmethod
    def _bucket_key(sector: str | None) -> str:
        return _normal_key(sector)

    def _calculate_targets(
        self,
        request: PortfolioOptimizationRequest,
        portfolio: PortfolioImportBundle,
        profile_id: str,
        profile_version: int,
        risk_level: RiskLevel,
        scenario: OptimizationScenarioDefinition,
        exposure: ExposureResult,
        concentration: ConcentrationResult,
        assessment: RiskBudgetAssessment,
        *,
        technology_cap_override: Decimal | None = None,
    ) -> PortfolioOptimizationResponse:
        invalidation = (
            "Risk Profile version or risk budget rule changes",
            "portfolio bundle or position snapshot changes",
            "fund look-through coverage or base currency changes",
            "CAP_AND_REDISTRIBUTE_V1 methodology changes",
        )
        report = exposure.report
        concentration_report = concentration.report
        assert report is not None and concentration_report is not None
        if exposure.status != ExposureStatus.COMPLETE or concentration.status != ConcentrationStatus.COMPLETE:
            issue_code = (
                OptimizationIssueCode.INPUT_PARTIAL
                if exposure.status == ExposureStatus.PARTIAL or concentration.status == ConcentrationStatus.PARTIAL
                else OptimizationIssueCode.INPUT_FAILED
            )
            return self._failure_response(
                request,
                portfolio,
                profile_id,
                profile_version,
                risk_level,
                scenario,
                OptimizationStatus.REVIEW_REQUIRED if issue_code == OptimizationIssueCode.INPUT_PARTIAL else OptimizationStatus.BLOCKED,
                "目标提案被数据质量状态阻断；请先补齐可穿透且同币种的持仓输入。",
                (OptimizationIssue(code=issue_code, safe_message="exposure or concentration input is not complete"),),
                exposure_report_id=report.report_id,
                concentration_report_id=concentration_report.report_id,
                assessment_id=assessment.assessment_id,
                assessment_status=assessment.status,
                contribution_ids=tuple(sorted(item.exposure_id for item in report.contributions)),
            )
        if (
            report.unclassified_market_value > Decimal("0")
            or concentration_report.unclassified_weight_pct > Decimal("0")
            or any(
                _normal_key(contribution.sector) == _UNCLASSIFIED_SECTOR
                for contribution in report.contributions
            )
        ):
            return self._failure_response(
                request,
                portfolio,
                profile_id,
                profile_version,
                risk_level,
                scenario,
                OptimizationStatus.REVIEW_REQUIRED,
                "存在未分类暴露；目标提案不会猜测其行业或风险归属。",
                (OptimizationIssue(code=OptimizationIssueCode.INPUT_UNCLASSIFIED, safe_message="unclassified exposure requires review"),),
                exposure_report_id=report.report_id,
                concentration_report_id=concentration_report.report_id,
                assessment_id=assessment.assessment_id,
                assessment_status=assessment.status,
                contribution_ids=tuple(sorted(item.exposure_id for item in report.contributions)),
            )

        # Aggregate observed contribution values; multiple look-through rows
        # for one asset are closed before any target arithmetic is attempted.
        asset_values: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        asset_labels: dict[str, str] = {}
        asset_sectors: dict[str, str | None] = {}
        asset_sector_sets: dict[str, set[str]] = defaultdict(set)
        for contribution in report.contributions:
            if contribution.basis == ExposureBasis.UNLOOKED_THROUGH:
                return self._failure_response(
                    request,
                    portfolio,
                    profile_id,
                    profile_version,
                    risk_level,
                    scenario,
                    OptimizationStatus.REVIEW_REQUIRED,
                    "存在未穿透的基金/ETF残余；目标权重需要人工复核。",
                    (OptimizationIssue(code=OptimizationIssueCode.INPUT_PARTIAL, safe_message="unlooked-through exposure requires review"),),
                    exposure_report_id=report.report_id,
                    concentration_report_id=concentration_report.report_id,
                    assessment_id=assessment.assessment_id,
                    assessment_status=assessment.status,
                    contribution_ids=tuple(sorted(item.exposure_id for item in report.contributions)),
                )
            asset_values[contribution.asset_id] += contribution.market_value
            asset_labels.setdefault(contribution.asset_id, contribution.asset_name)
            sector_key = _normal_key(contribution.sector)
            asset_sector_sets[contribution.asset_id].add(sector_key)
            asset_sectors.setdefault(contribution.asset_id, contribution.sector)
        if any(len(sectors) != 1 for sectors in asset_sector_sets.values()):
            return self._failure_response(
                request,
                portfolio,
                profile_id,
                profile_version,
                risk_level,
                scenario,
                OptimizationStatus.REVIEW_REQUIRED,
                "同一资产对应多个行业口径；目标提案不会擅自合并行业。",
                (OptimizationIssue(code=OptimizationIssueCode.INPUT_PARTIAL, safe_message="asset sector classification is ambiguous"),),
                exposure_report_id=report.report_id,
                concentration_report_id=concentration_report.report_id,
                assessment_id=assessment.assessment_id,
                assessment_status=assessment.status,
                contribution_ids=tuple(sorted(item.exposure_id for item in report.contributions)),
            )

        current_cents = _largest_remainder_weights(asset_values, report.total_market_value)
        sectors: dict[str, dict[str, Decimal]] = defaultdict(dict)
        for asset_id in sorted(asset_values):
            sector = _normal_key(asset_sectors[asset_id])
            sectors[sector][asset_id] = asset_values[asset_id]
        # Close sector current weights from the already rounded asset cents;
        # independently rounding both levels could otherwise create a one-cent
        # mismatch between the target rows and their sector constraint.
        sector_cents = {
            sector: sum((current_cents[asset_id] for asset_id in values), 0)
            for sector, values in sectors.items()
        }
        budget = assessment.budget
        technology_cap = (
            budget.max_technology_weight_pct
            if technology_cap_override is None
            else technology_cap_override
        )
        if technology_cap < Decimal("0") or technology_cap > Decimal("100"):
            raise PortfolioOptimizationError("technology cap override is outside the valid range")
        sector_caps: dict[str, int] = {}
        for sector, values in sectors.items():
            cap = budget.max_sector_weight_pct
            if sector in _TECHNOLOGY_SECTORS:
                cap = min(cap, technology_cap)
            if sector == _UNCLASSIFIED_SECTOR:
                cap = budget.max_unclassified_weight_pct
            cap_cents = min(_cents(cap), len(values) * _cents(budget.max_single_asset_weight_pct))
            sector_caps[sector] = cap_cents

        initial_sector = {sector: min(sector_cents[sector], sector_caps[sector]) for sector in sectors}
        cash_sectors = {_normal_key(c.sector) for c in report.contributions if c.asset_type == AssetType.CASH}
        cash_floor = _cents(request.minimum_cash_pct)
        if cash_floor:
            if len(cash_sectors) != 1 or sector_caps.get(next(iter(cash_sectors), ""), 0) < cash_floor:
                return self._failure_response(
                    request, portfolio, profile_id, profile_version, risk_level, scenario,
                    OptimizationStatus.BLOCKED, "缺少可用现金持仓或现金上限低于最低要求，无法闭合目标结构。",
                    (OptimizationIssue(code=OptimizationIssueCode.INFEASIBLE_CONSTRAINTS, safe_message="cash floor cannot be represented within current holdings and caps"),),
                )
            cash_sector = next(iter(cash_sectors))
            initial_sector[cash_sector] = max(initial_sector[cash_sector], cash_floor)
            excess = max(0, sum(initial_sector.values()) - 10000)
            for sector in sorted((s for s in sectors if s != cash_sector), key=lambda s: (-initial_sector[s], s)):
                reduction = min(excess, initial_sector[sector])
                initial_sector[sector] -= reduction
                excess -= reduction
                if not excess:
                    break
        technology_sectors = sorted(
            sector for sector in sectors if sector in _TECHNOLOGY_SECTORS
        )
        technology_cap_cents = _cents(technology_cap)
        technology_initial = sum(
            (initial_sector[sector] for sector in technology_sectors),
            0,
        )
        # Sector caps are local while the technology budget is global.  If
        # several sector labels map to Technology, reduce their initial
        # allocations first, then let the same deterministic redistribution
        # pass refill eligible buckets without crossing the aggregate cap.
        if technology_initial > technology_cap_cents:
            reduction_left = technology_initial - technology_cap_cents
            for sector in sorted(
                technology_sectors,
                key=lambda item: (-initial_sector[item], item),
            ):
                reduction = min(reduction_left, initial_sector[sector])
                initial_sector[sector] -= reduction
                reduction_left -= reduction
                if not reduction_left:
                    break
        released = 10000 - sum(initial_sector.values())
        while released:
            candidates = [
                sector for sector in sectors if initial_sector[sector] < sector_caps[sector]
            ]
            technology_headroom = technology_cap_cents - sum(
                (initial_sector[sector] for sector in technology_sectors),
                0,
            )
            if technology_headroom <= 0:
                candidates = [
                    sector for sector in candidates if sector not in technology_sectors
                ]
            if not candidates:
                return self._failure_response(
                    request,
                    portfolio,
                    profile_id,
                    profile_version,
                    risk_level,
                    scenario,
                    OptimizationStatus.BLOCKED,
                    "当前约束的可容纳总权重不足 100%；无法生成同时满足上限的目标。",
                    (OptimizationIssue(code=OptimizationIssueCode.INFEASIBLE_CONSTRAINTS, safe_message="configured asset and sector caps cannot close to 100 percent"),),
                    exposure_report_id=report.report_id,
                    concentration_report_id=concentration_report.report_id,
                    assessment_id=assessment.assessment_id,
                    assessment_status=assessment.status,
                    contribution_ids=tuple(sorted(item.exposure_id for item in report.contributions)),
                )
            candidates.sort(
                key=lambda sector: (-(sector_caps[sector] - initial_sector[sector]), sector)
            )
            for sector in candidates:
                if not released:
                    break
                headroom = sector_caps[sector] - initial_sector[sector]
                if sector in technology_sectors:
                    headroom = min(headroom, technology_headroom)
                add = min(released, headroom)
                initial_sector[sector] += add
                released -= add
                if sector in technology_sectors:
                    technology_headroom -= add

        target_cents: dict[str, int] = {}
        for sector in sorted(sectors):
            caps = {
                asset_id: _cents(budget.max_single_asset_weight_pct)
                for asset_id in sectors[sector]
            }
            allocated = _allocate_cents(initial_sector[sector], sectors[sector], caps)
            target_cents.update(allocated)
        if sum(target_cents.values()) != 10000:
            raise PortfolioOptimizationError("optimization target weights do not close to 100 percent")

        sector_target_cents: dict[str, int] = defaultdict(int)
        for asset_id, value in target_cents.items():
            sector_target_cents[_normal_key(asset_sectors[asset_id])] += value

        constraints: list[OptimizationConstraint] = []
        target_rows: list[OptimizationTarget] = []
        for asset_id in sorted(asset_values):
            sector = _normal_key(asset_sectors[asset_id])
            current = _from_cents(current_cents[asset_id])
            target = _from_cents(target_cents[asset_id])
            cap = budget.max_single_asset_weight_pct
            asset_constraint_id = _stable_id("optimization-constraint", "ASSET", asset_id)
            sector_constraint_id = _stable_id("optimization-constraint", "SECTOR", sector)
            aggregate_ids = [asset_constraint_id, sector_constraint_id]
            if sector in _TECHNOLOGY_SECTORS:
                aggregate_ids.append(_stable_id("optimization-constraint", "TECHNOLOGY"))
            if sector == _UNCLASSIFIED_SECTOR:
                aggregate_ids.append(_stable_id("optimization-constraint", "UNCLASSIFIED"))
            constraints.append(
                OptimizationConstraint(
                    constraint_id=asset_constraint_id,
                    owner_id=request.owner_id,
                    dimension=OptimizationDimension.ASSET,
                    target_id=asset_id,
                    label=asset_labels[asset_id],
                    current_weight_pct=current,
                    target_weight_pct=target,
                    allowed_max_weight_pct=cap,
                    delta_pct=_quantize(target - current),
                    disposition=(
                        OptimizationDisposition.REPAIRED
                        if current > cap
                        else OptimizationDisposition.WITHIN_LIMIT
                    ),
                    rationale=(
                        "single-asset cap applied; released weight is redistributed by stable headroom order"
                    ),
                )
            )
            target_rows.append(
                OptimizationTarget(
                    target_id=asset_id,
                    owner_id=request.owner_id,
                    asset_name=asset_labels[asset_id],
                    sector=(
                        asset_sectors[asset_id]
                        if _normal_key(asset_sectors[asset_id]) != _UNCLASSIFIED_SECTOR
                        else None
                    ),
                    current_weight_pct=current,
                    target_weight_pct=target,
                    delta_pct=_quantize(target - current),
                    allowed_max_weight_pct=cap,
                    constraint_ids=tuple(sorted(aggregate_ids)),
                    rationale=(
                        "target is deterministic and profile-conditioned; it is not a trade instruction"
                    ),
                )
            )

        for sector in sorted(sectors):
            current = _from_cents(sector_cents[sector])
            target = _from_cents(sector_target_cents[sector])
            cap = budget.max_sector_weight_pct
            if sector in _TECHNOLOGY_SECTORS:
                cap = min(cap, budget.max_technology_weight_pct)
            if sector == _UNCLASSIFIED_SECTOR:
                cap = budget.max_unclassified_weight_pct
            cid = _stable_id("optimization-constraint", "SECTOR", sector)
            constraints.append(
                OptimizationConstraint(
                    constraint_id=cid,
                    owner_id=request.owner_id,
                    dimension=OptimizationDimension.SECTOR,
                    target_id=sector,
                    label=sector,
                    current_weight_pct=current,
                    target_weight_pct=target,
                    allowed_max_weight_pct=cap,
                    delta_pct=_quantize(target - current),
                    disposition=(
                        OptimizationDisposition.REPAIRED
                        if current > cap
                        else OptimizationDisposition.WITHIN_LIMIT
                    ),
                    rationale="sector cap is applied before deterministic redistribution",
                )
            )

        technology_current = sum(
            (current_cents[asset_id] for asset_id in asset_values if _is_technology(asset_sectors[asset_id])),
            0,
        )
        technology_target = sum(
            (target_cents[asset_id] for asset_id in asset_values if _is_technology(asset_sectors[asset_id])),
            0,
        )
        unclassified_current = sum(
            (current_cents[asset_id] for asset_id in asset_values if _normal_key(asset_sectors[asset_id]) == _UNCLASSIFIED_SECTOR),
            0,
        )
        unclassified_target = sum(
            (target_cents[asset_id] for asset_id in asset_values if _normal_key(asset_sectors[asset_id]) == _UNCLASSIFIED_SECTOR),
            0,
        )
        for dimension, current_cents_value, target_cents_value, cap in (
            (OptimizationDimension.TECHNOLOGY, technology_current, technology_target, technology_cap),
            (OptimizationDimension.UNCLASSIFIED, unclassified_current, unclassified_target, budget.max_unclassified_weight_pct),
        ):
            cid = _stable_id("optimization-constraint", dimension.value)
            current = _from_cents(current_cents_value)
            target = _from_cents(target_cents_value)
            constraints.append(
                OptimizationConstraint(
                    constraint_id=cid,
                    owner_id=request.owner_id,
                    dimension=dimension,
                    label=dimension.value,
                    current_weight_pct=current,
                    target_weight_pct=target,
                    allowed_max_weight_pct=cap,
                    delta_pct=_quantize(target - current),
                    disposition=(
                        OptimizationDisposition.REPAIRED
                        if current > cap
                        else OptimizationDisposition.WITHIN_LIMIT
                    ),
                    rationale="aggregate budget dimension is checked independently of sector labels",
                )
            )

        target_rows = sorted(target_rows, key=lambda item: item.target_id)
        constraints = sorted(constraints, key=lambda item: item.constraint_id)
        source_ids = tuple(sorted(item.exposure_id for item in report.contributions))
        trace = OptimizationTrace(
            owner_id=request.owner_id,
            profile_id=profile_id,
            portfolio_bundle_id=portfolio.bundle_id,
            position_snapshot_id=portfolio.position_snapshot.snapshot_id,
            exposure_report_id=report.report_id,
            concentration_report_id=concentration_report.report_id,
            assessment_id=assessment.assessment_id,
            source_contribution_ids=source_ids,
            calculation_steps=(
                "aggregate exposure contributions into asset and sector buckets",
                "cap sector, technology and unclassified buckets using the confirmed risk budget",
                "redistribute released weight by largest headroom then stable ID",
                "allocate each bucket proportionally with a single-asset cap and cent-level closure",
            ),
            invalidation_conditions=invalidation,
        )
        return PortfolioOptimizationResponse(
            request_id=request.request_id,
            owner_id=request.owner_id,
            generated_at=request.generated_at,
            scenario=scenario,
            profile_id=profile_id,
            profile_version=profile_version,
            risk_level=risk_level,
            portfolio_bundle_id=portfolio.bundle_id,
            position_snapshot_id=portfolio.position_snapshot.snapshot_id,
            exposure_report_id=report.report_id,
            concentration_report_id=concentration_report.report_id,
            assessment_id=assessment.assessment_id,
            assessment_status=assessment.status,
            status=OptimizationStatus.READY,
            summary=f"已按确认画像和风险预算生成确定性目标结构，现金最低要求 {request.minimum_cash_pct}%；结果不是交易指令。",
            targets=tuple(target_rows),
            constraints=tuple(constraints),
            invalidation_conditions=invalidation,
            trace=trace,
        )

    def propose(
        self,
        portfolio: PortfolioImportBundle,
        profile: RiskProfile,
        exposure: ExposureResult,
        concentration: ConcentrationResult,
        assessment: RiskBudgetAssessment,
        *,
        request_id: str | None = None,
        generated_at: datetime | None = None,
        scenario_id: OptimizationScenarioId = OptimizationScenarioId.BASELINE_READY,
        technology_cap_override: Decimal | None = None,
    ) -> PortfolioOptimizationResponse:
        req_id = request_id or _stable_id("optimization-request", portfolio.bundle_id, profile.profile_id)
        gen_at = generated_at or (portfolio.created_at if portfolio.created_at.tzinfo else datetime.now(timezone.utc if hasattr(datetime, "UTC") else None))
        if gen_at is None or gen_at.tzinfo is None:
            from datetime import UTC
            gen_at = datetime.now(UTC)
        scenario = _scenario_definition(scenario_id)
        questionnaire = self._template.questionnaire.model_copy(
            update={
                "owner_id": portfolio.owner_id,
                "answered_at": gen_at,
            }
        )
        dummy_request = PortfolioOptimizationRequest(
            request_id=req_id,
            owner_id=portfolio.owner_id,
            generated_at=gen_at,
            questionnaire=questionnaire,
            portfolio=portfolio,
            scenario_id=scenario_id,
        )
        return self._calculate_targets(
            dummy_request,
            portfolio,
            profile.profile_id,
            profile.profile_version,
            profile.risk_level,
            scenario,
            exposure,
            concentration,
            assessment,
            technology_cap_override=technology_cap_override,
        )

    async def run(self, request: PortfolioOptimizationRequest) -> PortfolioOptimizationResponse:
        try:
            request = PortfolioOptimizationRequest.model_validate(
                request.model_dump(mode="python") if isinstance(request, PortfolioOptimizationRequest) else request
            )
            profile = request.confirmed_profile or confirm_questionnaire(request.questionnaire)
            portfolio = self._scenario_portfolio(request.portfolio, request.scenario_id)
            scenario = _scenario_definition(request.scenario_id)
            if request.scenario_id == OptimizationScenarioId.SOURCE_PARTIAL and not portfolio.fund_holdings:
                return self._failure_response(
                    request,
                    portfolio,
                    profile.profile_id,
                    profile.profile_version,
                    profile.risk_level,
                    scenario,
                    OptimizationStatus.REVIEW_REQUIRED,
                    "SOURCE_PARTIAL 回放需要基金/ETF 穿透快照；当前输入无法构造部分覆盖场景。",
                    (OptimizationIssue(code=OptimizationIssueCode.INPUT_PARTIAL, safe_message="partial replay requires a fund look-through snapshot"),),
                )
            exposure = calculate_exposure(
                portfolio,
                request_id=_stable_id("optimization-exposure-request", request.request_id),
                calculated_at=request.generated_at,
            )
            concentration = calculate_concentration(exposure)
            assessment = assess_risk_budget(profile, concentration)
            if exposure.status == ExposureStatus.FAILED or concentration.status == ConcentrationStatus.FAILED:
                return self._failure_response(
                    request,
                    portfolio,
                    profile.profile_id,
                    profile.profile_version,
                    profile.risk_level,
                    scenario,
                    OptimizationStatus.BLOCKED,
                    "组合暴露或集中度计算失败；目标权重已阻断。",
                    (OptimizationIssue(code=OptimizationIssueCode.INPUT_FAILED, safe_message="exposure or concentration calculation failed"),),
                    assessment_id=assessment.assessment_id,
                    assessment_status=assessment.status,
                )
            return self._calculate_targets(
                request,
                portfolio,
                profile.profile_id,
                profile.profile_version,
                profile.risk_level,
                scenario,
                exposure,
                concentration,
                assessment,
            )
        except PortfolioOptimizationError:
            raise
        except Exception as exc:
            raise PortfolioOptimizationError("portfolio optimization execution was refused") from exc


class DeterministicPortfolioOptimizationService:
    """Optimize an explicitly supplied portfolio without loading replay fixtures."""

    serving_mode = "LIVE"
    _failure_response = staticmethod(FixturePortfolioOptimizationService._failure_response)
    _calculate_targets = FixturePortfolioOptimizationService._calculate_targets

    async def run(self, request: PortfolioOptimizationRequest) -> PortfolioOptimizationResponse:
        try:
            request = PortfolioOptimizationRequest.model_validate(
                request.model_dump(mode="python")
                if isinstance(request, PortfolioOptimizationRequest)
                else request
            )
            if request.scenario_id != OptimizationScenarioId.BASELINE_READY:
                raise PortfolioOptimizationError(
                    "LIVE optimization only accepts the submitted baseline portfolio"
                )
            profile = request.confirmed_profile or confirm_questionnaire(request.questionnaire)
            portfolio = request.portfolio
            scenario = _scenario_definition(OptimizationScenarioId.BASELINE_READY)
            exposure = calculate_exposure(
                portfolio,
                request_id=_stable_id("optimization-exposure-request", request.request_id),
                calculated_at=request.generated_at,
            )
            concentration = calculate_concentration(exposure)
            assessment = assess_risk_budget(profile, concentration)
            if exposure.status == ExposureStatus.FAILED or concentration.status == ConcentrationStatus.FAILED:
                return self._failure_response(
                    request,
                    portfolio,
                    profile.profile_id,
                    profile.profile_version,
                    profile.risk_level,
                    scenario,
                    OptimizationStatus.BLOCKED,
                    "组合暴露或集中度计算失败；目标权重已阻断。",
                    (OptimizationIssue(
                        code=OptimizationIssueCode.INPUT_FAILED,
                        safe_message="exposure or concentration calculation failed",
                    ),),
                    assessment_id=assessment.assessment_id,
                    assessment_status=assessment.status,
                )
            return self._calculate_targets(
                request,
                portfolio,
                profile.profile_id,
                profile.profile_version,
                profile.risk_level,
                scenario,
                exposure,
                concentration,
                assessment,
            )
        except PortfolioOptimizationError:
            raise
        except Exception as exc:
            raise PortfolioOptimizationError("portfolio optimization execution was refused") from exc


__all__ = [
    "DeterministicPortfolioOptimizationService",
    "FixturePortfolioOptimizationService",
    "PortfolioOptimizationError",
]
