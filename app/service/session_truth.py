"""Server-derived session premises, revision checks and deterministic drift detection."""
from __future__ import annotations

from hashlib import sha256
import json
from decimal import Decimal, DecimalException
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.profile import RiskProfile, effective_risk_profile
from app.portfolio import PortfolioImportBundle
from app.store.sqlite import StoreOwnerError

class TruthInputRequired(ValueError):
    pass


class TruthConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    expected_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


def fingerprint(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def current_facts(store, owner, mode):
    snapshot = store.get_latest_questionnaire_snapshot(owner)
    portfolio = store.get_current_portfolio(owner, mode)
    if snapshot is None or portfolio is None:
        raise TruthInputRequired("请先确认风险问卷与当前数据模式下的持仓，再锁定分析前提")
    profile = snapshot.profile
    behavior = store.get_latest_behavior_profile(owner)
    if behavior and behavior.questionnaire_profile_id == profile.profile_id:
        profile = effective_risk_profile(profile, behavior)
    bundle = portfolio["portfolio"]
    if hasattr(bundle, "model_dump"):
        bundle = bundle.model_dump(mode="json")
    return {"data_mode":mode, "questionnaire_snapshot_id":snapshot.snapshot_id,
            "profile":profile.model_dump(mode="json"), "portfolio":bundle}


def truth_status(record, facts):
    current = {"current_fingerprint": fingerprint(facts), "current_facts": facts}
    if record is None:
        return {"status":"NOT_LOCKED", "revision":0, "changed_fields":[], "record":None, **current}
    changed = [key for key in ("data_mode", "questionnaire_snapshot_id", "profile", "portfolio")
               if fingerprint(record["facts"].get(key)) != fingerprint(facts.get(key))]
    return {"status":"DRIFT_DETECTED" if changed else "LOCKED", "revision":record["revision"],
            "changed_fields":changed, "record":record, **current}


class FactAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str = Field(min_length=1, max_length=100)
    value: str = Field(max_length=200)
    position_id: str | None = Field(default=None, min_length=1, max_length=200)


class StructuredAction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    action: Literal["BUY", "SELL", "HOLD"]
    asset_id: str = Field(min_length=1, max_length=200)


class SessionAssertionsRequest(BaseModel):
    """Structured claims only; numeric values are decimal strings, never floats."""
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_revision: int = Field(ge=1)
    assertions: list[FactAssertion] = Field(default_factory=list, max_length=30)
    actions: list[StructuredAction] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def require_items(self):
        if not self.assertions and not self.actions:
            raise ValueError("at least one assertion or action is required")
        return self


# Absolute units: market_value is currency units; profile numbers are percentage
# points. Quantities and identifiers require exact agreement with locked facts.
_PROFILE_FIELDS = {"risk_level", "investment_horizon", "liquidity_need", "risk_score",
                   "max_drawdown_tolerance_pct", "profile_id"}
_POSITION_FIELDS = {"asset_id", "asset_name", "asset_type", "sector", "currency", "quantity", "market_value"}
_TOLERANCES = {"risk_score": Decimal("0.01"), "max_drawdown_tolerance_pct": Decimal("0.01"),
               "market_value": Decimal("0.01"), "quantity": Decimal("0")}
_EXCLUSION_TYPES = {"股票": "STOCK", "基金": "FUND", "现金": "CASH", "债券": "BOND",
                    "stock": "STOCK", "etf": "ETF", "mutual_fund": "MUTUAL_FUND",
                    "bond": "BOND", "cash": "CASH", "other": "OTHER"}


def check_session_assertions(record, facts, request: SessionAssertionsRequest, *, owner_id: str):
    """Validate explicit claims against an authorized, unchanged session snapshot.

    This does not inspect prose or establish general recommendation suitability.
    """
    if not isinstance(owner_id, str) or not owner_id.strip():
        raise StoreOwnerError("owner required")
    for candidate in (facts, record["facts"] if record else None):
        if candidate and any(candidate.get(key, {}).get("owner_id") != owner_id for key in ("profile", "portfolio")):
            raise StoreOwnerError("session facts owner mismatch")
    state = truth_status(record, facts)
    if state["status"] != "LOCKED" or state["revision"] != request.expected_revision:
        return {"status": "UNVERIFIED", "reason": "CURRENT_LOCK_REQUIRED", "results": [],
                "revision": state["revision"], "truth_status": state["status"]}
    profile = RiskProfile.model_validate(record["facts"]["profile"])
    portfolio = PortfolioImportBundle.model_validate(record["facts"]["portfolio"])
    results = []
    for index, assertion in enumerate(request.assertions):
        parts = assertion.path.split(".")
        source, actual, field = None, None, parts[-1]
        if len(parts) == 2 and parts[0] == "profile" and field in _PROFILE_FIELDS and assertion.position_id is None:
            actual, source = getattr(profile, field), profile.profile_id
        elif len(parts) == 3 and parts[:2] == ["portfolio", "positions"] and field in _POSITION_FIELDS:
            position = next((p for p in portfolio.position_snapshot.positions if p.position_id == assertion.position_id), None)
            if position:
                actual, source = getattr(position, field), portfolio.position_snapshot.snapshot_id
        item = {"kind": "FACT", "index": index, "path": assertion.path,
                "position_id": assertion.position_id, "source_id": source,
                "expected": None if actual is None else str(actual), "claimed": assertion.value}
        if source is None:
            item.update(status="HALLUCINATED_DATA", reason="UNKNOWN_FACT_REFERENCE")
        elif actual is None:
            item.update(status="UNVERIFIED", reason="FACT_VALUE_UNAVAILABLE")
        elif field in _TOLERANCES:
            tolerance = _TOLERANCES[field]
            try:
                claimed = Decimal(assertion.value)
                matches = claimed.is_finite() and abs(claimed - actual) <= tolerance
            except (DecimalException, ValueError):
                matches = False
            item.update(status="PASS" if matches else "HALLUCINATED_DATA",
                        reason="DECIMAL_COMPARISON", absolute_tolerance=str(tolerance))
        else:
            item.update(status="PASS" if assertion.value == str(actual) else "HALLUCINATED_DATA", reason="EXACT_COMPARISON")
        results.append(item)
    for index, action in enumerate(request.actions):
        positions = [p for p in portfolio.position_snapshot.positions if p.asset_id == action.asset_id]
        item = {"kind": "ACTION", "index": index, "action": action.action,
                "asset_id": action.asset_id, "source_id": profile.profile_id,
                "constraint_path": "profile.exclusions"}
        if not positions:
            item.update(status="UNVERIFIED", reason="ASSET_NOT_IN_LOCKED_PORTFOLIO")
        elif action.action != "BUY":
            item.update(status="UNVERIFIED", reason="ONLY_NEW_BUY_EXCLUSION_CHECK_SUPPORTED")
        else:
            matched, unresolved = [], []
            for exclusion in profile.exclusions:
                normalized = exclusion.strip().casefold()
                asset_type = _EXCLUSION_TYPES.get(normalized)
                if any(normalized in {p.asset_id.casefold(), p.asset_name.casefold(), (p.sector or "").casefold()}
                       or (asset_type == "FUND" and p.asset_type in ("ETF", "MUTUAL_FUND"))
                       or asset_type == p.asset_type for p in positions):
                    matched.append(exclusion)
                elif asset_type is None:
                    unresolved.append(exclusion)
            item.update(status="ACTION_CONFLICT" if matched else "UNVERIFIED" if unresolved else "PASS",
                        reason="BUY_EXCLUSION_CHECK_ONLY", matched_exclusions=matched,
                        unverified_exclusions=unresolved)
        results.append(item)
    statuses = {item["status"] for item in results}
    return {"status": "VIOLATION" if statuses & {"HALLUCINATED_DATA", "ACTION_CONFLICT"} else "UNVERIFIED" if "UNVERIFIED" in statuses else "PASS",
            "revision": state["revision"], "facts_fingerprint": fingerprint(record["facts"]),
            "scope": "STRUCTURED_FACTS_AND_EXPLICIT_BUY_EXCLUSIONS_ONLY", "results": results}
