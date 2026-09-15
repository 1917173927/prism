"""Deterministic current-portfolio report snapshots.

The report is a presentation contract over one confirmed portfolio bundle. It
does not query a language model, invent a quote, or turn a holding row into a
stock-research run.  Every displayed number is derived from the persisted
portfolio rows and the existing deterministic risk calculation.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import json
from hashlib import sha256
from typing import Literal, Self

from pydantic import Field, model_validator

from app.contracts.evidence import ContractModel, NonEmptyStr
from app.portfolio.contracts import AssetType, PortfolioImportBundle
from app.portfolio.health import PortfolioHealthResponse
from app.portfolio.summary import portfolio_summary
from app.profile import ProfilePresentation, RiskProfile
from app.risk import build_risk_budget


REPORT_RULESET_VERSION = "portfolio-report-rules.v1"
REPORT_DATA_MODES = ("LIVE", "MOCK")
ASSET_GROUP_KEYS = (
    "stock",
    "etf",
    "convertible",
    "bond",
    "cash",
    "other",
)
ASSET_GROUP_LABELS = {
    "stock": "股票",
    "etf": "ETF / 基金",
    "convertible": "可转债",
    "bond": "债券",
    "cash": "现金",
    "other": "其他",
}


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _decimal(value: object) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("report values must be finite")
    return result


def _percentage(value: Decimal, total: Decimal) -> Decimal:
    if total <= 0:
        return Decimal("0.00")
    return _q(value / total * Decimal("100"))


def _asset_group(asset_type: AssetType, asset_id: str, asset_name: str, asset_class: object) -> str:
    normalized_class = str(asset_class or "").strip().upper()
    normalized_name = asset_name.casefold()
    if asset_type == AssetType.CASH or asset_id == "CASH-CNY":
        return "cash"
    if normalized_class in {"CONVERTIBLE", "CONVERTIBLE_BOND", "CB", "BOND_CONVERTIBLE"}:
        return "convertible"
    if "转债" in normalized_name or "convertible" in normalized_name:
        return "convertible"
    if asset_type in {AssetType.ETF, AssetType.MUTUAL_FUND} or normalized_class in {
        "ETF",
        "FUND",
        "FUND_ETF",
        "MUTUAL_FUND",
    }:
        return "etf"
    if asset_type == AssetType.BOND:
        return "bond"
    if asset_type == AssetType.OTHER:
        return "other"
    return "stock"


class PortfolioReportPosition(ContractModel):
    """One holding row in the formal report and diagnosis drawer."""

    position_id: NonEmptyStr
    asset_id: NonEmptyStr
    asset_name: NonEmptyStr
    asset_type: AssetType
    asset_group: Literal["stock", "etf", "convertible", "bond", "cash", "other"]
    sector: NonEmptyStr | None = None
    quantity: Decimal = Field(gt=Decimal("0"))
    cost_price_cny: Decimal | None = Field(default=None, gt=Decimal("0"))
    current_price_cny: Decimal = Field(gt=Decimal("0"))
    market_value_cny: Decimal = Field(ge=Decimal("0"))
    pnl_cny: Decimal | None = None
    pnl_pct: Decimal | None = None
    weight_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    diagnosis_status: Literal["PASS", "REVIEW_REQUIRED"]
    diagnosis: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=4)


class PortfolioReportAssetGroup(ContractModel):
    """Closed asset-class allocation in the report."""

    group_key: Literal["stock", "etf", "convertible", "bond", "cash", "other"]
    label: NonEmptyStr
    market_value_cny: Decimal = Field(ge=Decimal("0"))
    weight_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    position_count: int = Field(ge=0)


class PortfolioReportProfile(ContractModel):
    """The small profile slice needed for portfolio suitability comparison."""

    profile_id: NonEmptyStr
    profile_version: int = Field(ge=1)
    suitability_level: Literal["C1", "C2", "C3", "C4", "C5"]
    archetype: NonEmptyStr
    risk_score: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    max_single_asset_weight_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    equity_weight_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    equity_minimum_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    equity_maximum_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    equity_verdict: Literal["PASS", "OVERBOUND", "UNDERBOUND"]

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.equity_minimum_pct > self.equity_maximum_pct:
            raise ValueError("profile equity minimum must not exceed maximum")
        return self


class PortfolioReportSector(ContractModel):
    """Safe sector comparison rows copied from the deterministic health run."""

    sector_key: NonEmptyStr
    name: NonEmptyStr
    weight_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    limit_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    limit_operator: Literal["MAX", "MIN"]
    verdict: Literal["PASS", "OVERBOUND"]
    top_holdings: tuple[NonEmptyStr, ...] = ()


class PortfolioReportRisk(ContractModel):
    """Portfolio risk conclusion used by the report card."""

    status: Literal["PASS", "REVIEW_REQUIRED", "BLOCKED", "UNAVAILABLE"]
    sector_hhi: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("10000"))
    hhi_limit: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("10000"))
    hhi_verdict: Literal["PASS", "OVERBOUND", "UNAVAILABLE"]
    top_sector_name: NonEmptyStr | None = None
    top_sector_weight_pct: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("100"))
    cash_weight_pct: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("100"))
    cash_minimum_pct: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("100"))
    sectors: tuple[PortfolioReportSector, ...] = ()
    issues: tuple[NonEmptyStr, ...] = ()


class PortfolioReportConcentration(ContractModel):
    """Explicit asset-concentration facts for the overall report."""

    status: Literal["CALCULATED", "REVIEW_REQUIRED", "UNAVAILABLE"]
    top_asset_name: NonEmptyStr | None = None
    top_asset_weight_pct: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("100"))
    asset_hhi: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("10000"))
    single_asset_limit_pct: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("100"))
    single_asset_verdict: Literal["PASS", "OVERBOUND", "UNAVAILABLE"]
    issues: tuple[NonEmptyStr, ...] = ()


class PortfolioReportPnlSummary(ContractModel):
    """Loss facts which remain separate from the headline P&L KPI."""

    status: Literal["CALCULATED", "PARTIAL"]
    loss_position_count: int = Field(ge=0)
    loss_market_value_cny: Decimal = Field(ge=Decimal("0"))
    loss_weight_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    note: NonEmptyStr


class PortfolioReportProtection(ContractModel):
    """Observed defensive assets and optional profile reference."""

    status: Literal["CALCULATED", "REVIEW_REQUIRED"]
    defensive_market_value_cny: Decimal = Field(ge=Decimal("0"))
    defensive_weight_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    components: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=4)
    profile_reference_pct: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("100"))
    reference_verdict: Literal["PASS", "BELOW_REFERENCE", "UNAVAILABLE"]
    note: NonEmptyStr


class PortfolioReport(ContractModel):
    """Immutable, owner-scoped report snapshot for one current portfolio."""

    schema_version: Literal["portfolio-report.v1"] = "portfolio-report.v1"
    ruleset_version: Literal["portfolio-report-rules.v1"] = REPORT_RULESET_VERSION
    report_id: NonEmptyStr
    owner_id: NonEmptyStr
    data_mode: Literal["LIVE", "MOCK"]
    generated_at: datetime
    source_bundle_id: NonEmptyStr
    source_snapshot_id: NonEmptyStr
    source_as_of: datetime
    base_currency: NonEmptyStr
    holdings_value_cny: Decimal = Field(ge=Decimal("0"))
    cash_cny: Decimal = Field(ge=Decimal("0"))
    total_value_cny: Decimal = Field(gt=Decimal("0"))
    daily_pnl_cny: Decimal | None = None
    cumulative_pnl_cny: Decimal | None = None
    cumulative_pnl_pct: Decimal | None = None
    position_count: int = Field(ge=0)
    positions: tuple[PortfolioReportPosition, ...] = ()
    asset_structure: tuple[PortfolioReportAssetGroup, ...] = Field(min_length=1)
    profile: PortfolioReportProfile | None = None
    concentration: PortfolioReportConcentration
    pnl_summary: PortfolioReportPnlSummary
    base_protection: PortfolioReportProtection
    configuration_reference: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=3)
    risk: PortfolioReportRisk
    headline: NonEmptyStr
    observations: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=8)
    disclosures: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        if self.source_as_of.tzinfo is None or self.source_as_of.utcoffset() is None:
            raise ValueError("source_as_of must be timezone-aware")
        if self.position_count != len(self.positions):
            raise ValueError("position_count must match report positions")
        group_keys = [group.group_key for group in self.asset_structure]
        if len(set(group_keys)) != len(group_keys):
            raise ValueError("asset_structure must not contain duplicate groups")
        group_total = sum((group.market_value_cny for group in self.asset_structure), Decimal("0"))
        if group_total != self.total_value_cny:
            raise ValueError("asset structure must close total value")
        weight_total = sum((group.weight_pct for group in self.asset_structure), Decimal("0"))
        if weight_total != Decimal("100.00"):
            raise ValueError("asset structure weights must close to 100 percent")
        position_total = sum((position.market_value_cny for position in self.positions), Decimal("0"))
        if position_total != self.holdings_value_cny:
            raise ValueError("report positions must close holdings value")
        if position_total + self.cash_cny != self.total_value_cny:
            raise ValueError("report positions and cash must close total value")
        if self.concentration.top_asset_weight_pct is not None and self.concentration.top_asset_weight_pct > Decimal("100"):
            raise ValueError("top asset weight must not exceed 100 percent")
        if self.pnl_summary.loss_market_value_cny > self.holdings_value_cny:
            raise ValueError("loss market value must not exceed holdings value")
        if self.base_protection.defensive_market_value_cny > self.total_value_cny:
            raise ValueError("defensive market value must not exceed total value")
        return self


def _report_identity(
    bundle: PortfolioImportBundle,
    data_mode: str,
    profile: RiskProfile | None,
) -> str:
    payload = json.dumps(
        {
            "bundle_id": bundle.bundle_id,
            "snapshot_id": bundle.position_snapshot.snapshot_id,
            "data_mode": data_mode,
            "profile_id": profile.profile_id if profile is not None else None,
            "profile_version": profile.profile_version if profile is not None else None,
            "ruleset_version": REPORT_RULESET_VERSION,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "portfolio-report-" + sha256(payload.encode("utf-8")).hexdigest()[:32]


def _profile_projection(
    profile: RiskProfile | None,
    presentation: ProfilePresentation | None,
    equity_weight_pct: Decimal,
) -> PortfolioReportProfile | None:
    if profile is None or presentation is None:
        return None
    budget = build_risk_budget(profile)
    minimum = presentation.equity_range.minimum_pct
    maximum = presentation.equity_range.maximum_pct
    verdict = (
        "UNDERBOUND"
        if equity_weight_pct < minimum
        else "OVERBOUND"
        if equity_weight_pct > maximum
        else "PASS"
    )
    return PortfolioReportProfile(
        profile_id=profile.profile_id,
        profile_version=profile.profile_version,
        suitability_level=presentation.suitability_level.value,
        archetype=presentation.archetype,
        risk_score=profile.risk_score,
        max_single_asset_weight_pct=budget.max_single_asset_weight_pct,
        equity_weight_pct=equity_weight_pct,
        equity_minimum_pct=minimum,
        equity_maximum_pct=maximum,
        equity_verdict=verdict,
    )


def _position_diagnosis(
    *,
    weight_pct: Decimal,
    risk_weight_pct: Decimal | None = None,
    cost_price: Decimal | None,
    pnl_cny: Decimal | None,
    sector: str | None,
    max_single_asset_weight_pct: Decimal | None,
) -> tuple[Literal["PASS", "REVIEW_REQUIRED"], tuple[str, ...]]:
    reasons: list[str] = []
    risk_weight = risk_weight_pct if risk_weight_pct is not None else weight_pct
    if cost_price is None or pnl_cny is None:
        reasons.append("成本价未提供，累计盈亏暂不可核验。")
    elif pnl_cny > 0:
        reasons.append("当前价格高于成本价，累计盈亏为正。")
    elif pnl_cny < 0:
        reasons.append("当前价格低于成本价，累计盈亏为负。")
    else:
        reasons.append("当前价格与成本价一致，累计盈亏为零。")
    if max_single_asset_weight_pct is None:
        reasons.append("未绑定风险画像，暂不执行单一资产上限对照。")
    elif risk_weight > max_single_asset_weight_pct:
        reasons.append(
            f"证券持仓占比 {weight_pct}%，按组合总资产口径为 {risk_weight}%，超过画像单一资产上限 {max_single_asset_weight_pct}%。"
        )
    else:
        reasons.append(
            f"证券持仓占比 {weight_pct}%，按组合总资产口径为 {risk_weight}%，未超过画像单一资产上限 {max_single_asset_weight_pct}%。"
        )
    if not sector:
        reasons.append("行业信息未分类，组合穿透结论需复核。")
    needs_review = (
        cost_price is None
        or pnl_cny is None
        or (max_single_asset_weight_pct is not None and risk_weight > max_single_asset_weight_pct)
        or not sector
    )
    return ("REVIEW_REQUIRED" if needs_review else "PASS"), tuple(reasons[:4])


def _risk_projection(health: PortfolioHealthResponse | None) -> PortfolioReportRisk:
    if health is None:
        return PortfolioReportRisk(
            status="UNAVAILABLE",
            hhi_verdict="UNAVAILABLE",
            issues=("未绑定风险画像，未执行组合风险预算对照。",),
        )
    return PortfolioReportRisk(
        status=health.status,
        sector_hhi=health.sector_hhi,
        hhi_limit=health.hhi_limit,
        hhi_verdict=health.hhi_verdict,
        top_sector_name=health.top_sector_name,
        top_sector_weight_pct=health.top_sector_weight_pct,
        cash_weight_pct=health.cash_weight_pct,
        cash_minimum_pct=health.cash_minimum_pct,
        sectors=tuple(
            PortfolioReportSector(
                sector_key=sector.sector_key,
                name=sector.name,
                weight_pct=sector.weight_pct,
                limit_pct=sector.limit_pct,
                limit_operator=sector.limit_operator,
                verdict=sector.verdict,
                top_holdings=sector.top_holdings,
            )
            for sector in health.sectors
        ),
        issues=health.issues,
    )


def build_portfolio_report(
    data: dict,
    *,
    owner_id: str,
    data_mode: str,
    profile: RiskProfile | None = None,
    presentation: ProfilePresentation | None = None,
    health: PortfolioHealthResponse | None = None,
) -> PortfolioReport:
    """Build one stable report from a persisted current-portfolio payload."""

    if data_mode not in REPORT_DATA_MODES:
        raise ValueError("invalid report data mode")
    if not isinstance(data, dict) or not data.get("portfolio"):
        raise ValueError("portfolio report requires a confirmed portfolio")
    bundle = PortfolioImportBundle.model_validate(data["portfolio"])
    if bundle.owner_id != owner_id:
        raise ValueError("portfolio report owner does not match portfolio bundle")
    if profile is not None and profile.owner_id != owner_id:
        raise ValueError("portfolio report owner does not match profile")
    if presentation is not None and profile is None:
        raise ValueError("profile presentation requires a profile")
    if health is not None and health.owner_id != owner_id:
        raise ValueError("portfolio report owner does not match health result")

    summary = portfolio_summary(data)
    rows = summary["positions"]
    contract_positions = [
        position
        for position in bundle.position_snapshot.positions
        if position.asset_type != AssetType.CASH
    ]
    if len(rows) != len(contract_positions):
        raise ValueError("portfolio report rows do not match portfolio snapshot")

    cash = _decimal(summary["cash_cny"])
    holdings_value = _decimal(summary["holdings_value_cny"])
    total_value = _decimal(summary["total_value_cny"])
    groups = {key: Decimal("0") for key in ASSET_GROUP_KEYS}
    group_counts = {key: 0 for key in ASSET_GROUP_KEYS}
    raw_positions: list[tuple[dict, object, str]] = []
    for raw, contract in zip(rows, contract_positions, strict=True):
        group = _asset_group(
            contract.asset_type,
            contract.asset_id,
            contract.asset_name,
            raw.get("asset_class"),
        )
        market_value = _decimal(raw["market_value_cny"])
        groups[group] += market_value
        group_counts[group] += 1
        raw_positions.append((raw, contract, group))
    groups["cash"] += cash

    group_values = {key: _q(value) for key, value in groups.items()}
    group_delta = total_value - sum(group_values.values(), Decimal("0"))
    if group_delta:
        largest_group = max(ASSET_GROUP_KEYS, key=lambda key: group_values[key])
        group_values[largest_group] += group_delta
    asset_structure = tuple(
        PortfolioReportAssetGroup(
            group_key=key,
            label=ASSET_GROUP_LABELS[key],
            market_value_cny=group_values[key],
            weight_pct=_percentage(group_values[key], total_value),
            position_count=group_counts[key],
        )
        for key in ASSET_GROUP_KEYS
    )
    structure_weights = [group.weight_pct for group in asset_structure]
    weight_delta = Decimal("100.00") - sum(structure_weights, Decimal("0"))
    if weight_delta:
        largest_index = max(range(len(asset_structure)), key=lambda index: asset_structure[index].market_value_cny)
        adjusted = list(asset_structure)
        adjusted[largest_index] = adjusted[largest_index].model_copy(
            update={"weight_pct": adjusted[largest_index].weight_pct + weight_delta}
        )
        asset_structure = tuple(adjusted)

    max_single = None
    if profile is not None:
        max_single = build_risk_budget(profile).max_single_asset_weight_pct
    report_positions: list[PortfolioReportPosition] = []
    risk_weights: dict[str, Decimal] = {}
    for raw, contract, group in raw_positions:
        cost_price = raw.get("cost_price")
        cost = _decimal(cost_price) if cost_price is not None else None
        current = _decimal(raw["price"])
        market_value = _q(_decimal(raw["market_value_cny"]))
        pnl = raw.get("pnl_cny")
        pnl_value = _decimal(pnl) if pnl is not None else None
        pnl_pct = _q((current / cost - Decimal("1")) * Decimal("100")) if cost else None
        # The PRD defines the detail-table weight against securities holdings
        # value.  Risk-budget checks retain the total-asset denominator because
        # the existing health contract includes cash in its exposure report.
        weight = _percentage(market_value, holdings_value)
        risk_weights[contract.asset_id] = _percentage(market_value, total_value)
        diagnosis_status, diagnosis = _position_diagnosis(
            weight_pct=weight,
            risk_weight_pct=risk_weights[contract.asset_id],
            cost_price=cost,
            pnl_cny=pnl_value,
            sector=contract.sector,
            max_single_asset_weight_pct=max_single,
        )
        report_positions.append(
            PortfolioReportPosition(
                position_id=contract.position_id,
                asset_id=contract.asset_id,
                asset_name=contract.asset_name,
                asset_type=contract.asset_type,
                asset_group=group,
                sector=contract.sector,
                quantity=contract.quantity,
                cost_price_cny=cost,
                current_price_cny=current,
                market_value_cny=market_value,
                pnl_cny=pnl_value,
                pnl_pct=pnl_pct,
                weight_pct=weight,
                diagnosis_status=diagnosis_status,
                diagnosis=diagnosis,
            )
        )

    ordered_positions = sorted(
        report_positions,
        key=lambda position: (-position.weight_pct, position.asset_id),
    )
    if ordered_positions:
        top_position = ordered_positions[0]
        top_risk_weight = risk_weights[top_position.asset_id]
        asset_hhi = _q(
            sum(
                (position.weight_pct * position.weight_pct for position in ordered_positions),
                Decimal("0"),
            )
        )
        single_verdict = (
            "UNAVAILABLE"
            if max_single is None
            else "OVERBOUND"
            if top_risk_weight > max_single
            else "PASS"
        )
        concentration_status = "REVIEW_REQUIRED" if single_verdict == "OVERBOUND" else "CALCULATED"
        concentration_issues = (
            (f"{top_position.asset_name} 证券持仓占比 {top_position.weight_pct}%，按组合总资产口径为 {top_risk_weight}%，超过画像单一资产上限 {max_single}%。",)
            if single_verdict == "OVERBOUND"
            else ()
        )
        concentration = PortfolioReportConcentration(
            status=concentration_status,
            top_asset_name=top_position.asset_name,
            top_asset_weight_pct=top_position.weight_pct,
            asset_hhi=asset_hhi,
            single_asset_limit_pct=max_single,
            single_asset_verdict=single_verdict,
            issues=concentration_issues,
        )
    else:
        concentration = PortfolioReportConcentration(
            status="UNAVAILABLE",
            single_asset_verdict="UNAVAILABLE",
            issues=("当前快照没有可用于个股集中度计算的证券持仓。",),
        )

    loss_positions = [
        position for position in report_positions
        if position.pnl_cny is not None and position.pnl_cny < 0
    ]
    loss_market_value = _q(
        sum((position.market_value_cny for position in loss_positions), Decimal("0"))
    )
    loss_weight = _percentage(loss_market_value, total_value)
    pnl_summary = PortfolioReportPnlSummary(
        status="CALCULATED" if summary["pnl_cny"] is not None else "PARTIAL",
        loss_position_count=len(loss_positions),
        loss_market_value_cny=loss_market_value,
        loss_weight_pct=loss_weight,
        note=(
            "累计盈亏完整可核验，当前快照没有已核验浮亏持仓。"
            if summary["pnl_cny"] is not None and not loss_positions
            else f"当前有 {len(loss_positions)} 个标的浮亏，浮亏市值约 {loss_market_value} 元。"
            if summary["pnl_cny"] is not None
            else "至少一项持仓缺少成本价，浮亏统计不完整。"
        ),
    )

    equity_value = groups["stock"] + groups["etf"]
    equity_weight = _percentage(equity_value, total_value)
    profile_projection = _profile_projection(profile, presentation, equity_weight)
    risk_projection = _risk_projection(health)

    defensive_keys = ("cash", "bond", "convertible")
    defensive_value = _q(sum((groups[key] for key in defensive_keys), Decimal("0")))
    defensive_components = tuple(
        ASSET_GROUP_LABELS[key] for key in defensive_keys if groups[key] > 0
    ) or ("未发现现金、债券或可转债资产",)
    profile_reference = None
    reference_verdict = "UNAVAILABLE"
    if presentation is not None:
        profile_reference = _q(
            sum(
                item.target_pct
                for item in presentation.asset_allocation
                if item.key in {"cash", "bonds"}
            )
        )
    defensive_weight = _percentage(defensive_value, total_value)
    if presentation is not None:
        reference_verdict = "PASS" if defensive_weight >= profile_reference else "BELOW_REFERENCE"
    base_protection = PortfolioReportProtection(
        status="CALCULATED" if defensive_value > 0 else "REVIEW_REQUIRED",
        defensive_market_value_cny=defensive_value,
        defensive_weight_pct=defensive_weight,
        components=defensive_components,
        profile_reference_pct=profile_reference,
        reference_verdict=reference_verdict,
        note=(
            f"现金、债券和可转债合计占比 {defensive_weight}%，作为防御性资产观察项。"
            if presentation is None
            else f"现金、债券和可转债合计占比 {defensive_weight}%；画像防御性配置参考为 {profile_reference}%。"
        ),
    )

    if profile_projection is None:
        configuration_reference = ("未绑定已确认风险画像，暂不生成权益增配参考。",)
    elif profile_projection.equity_verdict == "UNDERBOUND":
        configuration_reference = (
            "权益类仓位低于画像参考区间；后续可评估是否向参考区间补足，不自动生成交易指令。",
        )
    elif profile_projection.equity_verdict == "OVERBOUND":
        configuration_reference = (
            "权益类仓位高于画像参考区间；后续可评估降低风险暴露，不自动生成交易指令。",
        )
    else:
        configuration_reference = ("权益类仓位位于画像参考区间内，当前不提示额外配置调整。",)

    observations: list[str] = []
    observations.append(
        f"本次报告覆盖 {len(report_positions)} 个证券持仓，组合总市值为 {total_value} 元。"
    )
    observations.append(pnl_summary.note)
    if summary["daily_pnl_cny"] is None:
        observations.append("当日盈亏未完整计算：至少一项持仓缺少可核验昨收价。")
    else:
        observations.append(f"当日盈亏为 {summary['daily_pnl_cny']} 元，基于当前价格与昨收价计算。")
    if concentration.top_asset_name is not None:
        observations.append(
            f"集中度观察：{concentration.top_asset_name} 占证券持仓市值 {concentration.top_asset_weight_pct}%；"
            + (
                f"超过画像单一资产上限 {concentration.single_asset_limit_pct}%，需要复核。"
                if concentration.single_asset_verdict == "OVERBOUND"
                else "当前仅作事实展示，未生成交易指令。"
            )
        )
    else:
        observations.append("集中度暂不可计算：当前没有可用证券持仓。")
    largest_key = max(ASSET_GROUP_KEYS, key=lambda key: group_values[key])
    observations.append(
        f"资产结构中{ASSET_GROUP_LABELS[largest_key]}占比最高，为 {asset_structure[ASSET_GROUP_KEYS.index(largest_key)].weight_pct}%。"
    )
    if profile_projection is None:
        observations.append("当前报告未绑定已确认风险画像，未执行画像区间和单项上限对照。")
    elif profile_projection.equity_verdict == "PASS":
        observations.append(
            f"权益类占比 {equity_weight}% 在画像参考区间 {profile_projection.equity_minimum_pct}%–{profile_projection.equity_maximum_pct}% 内。"
        )
    elif profile_projection.equity_verdict == "UNDERBOUND":
        observations.append(
            f"权益类占比 {equity_weight}% 低于画像参考下限 {profile_projection.equity_minimum_pct}%，需结合资金用途复核。"
        )
    else:
        observations.append(
            f"权益类占比 {equity_weight}% 高于画像参考上限 {profile_projection.equity_maximum_pct}%，需结合风险承受能力复核。"
        )
    observations.append(base_protection.note)
    if risk_projection.status == "PASS":
        observations.append("组合行业集中度与已确认风险预算均未发现超限项。")
    elif risk_projection.status == "UNAVAILABLE":
        observations.append("组合风险预算尚未执行，当前只展示持仓事实和收益计算。")
    else:
        observations.append("组合风险结果需要关注；请展开行业与集中度明细复核。")

    headline = (
        "当前组合在已确认规则下未发现明显超限"
        if risk_projection.status == "PASS"
        else "当前组合存在需要关注的风险边界"
        if risk_projection.status in {"REVIEW_REQUIRED", "BLOCKED"}
        else "持仓事实已生成，风险画像对照待完成"
    )
    source_as_of = bundle.position_snapshot.as_of
    return PortfolioReport(
        report_id=_report_identity(bundle, data_mode, profile),
        owner_id=owner_id,
        data_mode=data_mode,
        generated_at=source_as_of,
        source_bundle_id=bundle.bundle_id,
        source_snapshot_id=bundle.position_snapshot.snapshot_id,
        source_as_of=source_as_of,
        base_currency=bundle.position_snapshot.base_currency,
        holdings_value_cny=holdings_value,
        cash_cny=cash,
        total_value_cny=total_value,
        daily_pnl_cny=_decimal(summary["daily_pnl_cny"]) if summary["daily_pnl_cny"] is not None else None,
        cumulative_pnl_cny=_decimal(summary["pnl_cny"]) if summary["pnl_cny"] is not None else None,
        cumulative_pnl_pct=_decimal(summary["pnl_pct"]) if summary["pnl_pct"] is not None else None,
        position_count=len(report_positions),
        positions=tuple(report_positions),
        asset_structure=asset_structure,
        profile=profile_projection,
        concentration=concentration,
        pnl_summary=pnl_summary,
        base_protection=base_protection,
        configuration_reference=configuration_reference,
        risk=risk_projection,
        headline=headline,
        observations=tuple(observations[:8]),
        disclosures=(
            f"{data_mode} · 报告基于持仓快照 {source_as_of.isoformat()} 计算。",
            "报告中的收益和比例只对当前快照负责，不代表未来表现。",
            "缺少成本价、昨收价或行业穿透时，相关结论保留为待复核。",
            "本报告仅供投资研究与风险复核参考，不构成投资建议或交易指令。",
        ),
    )


__all__ = [
    "ASSET_GROUP_KEYS",
    "REPORT_RULESET_VERSION",
    "PortfolioReport",
    "PortfolioReportAssetGroup",
    "PortfolioReportConcentration",
    "PortfolioReportPnlSummary",
    "PortfolioReportProtection",
    "PortfolioReportPosition",
    "PortfolioReportProfile",
    "PortfolioReportRisk",
    "PortfolioReportSector",
    "build_portfolio_report",
]
