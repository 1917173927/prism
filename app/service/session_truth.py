"""Server-derived session premises, revision checks and deterministic drift detection."""
from __future__ import annotations

from hashlib import sha256
import json

from pydantic import BaseModel, ConfigDict, Field

from app.profile import effective_risk_profile

class TruthInputRequired(ValueError):
    pass


class TruthConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)


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
    if record is None:
        return {"status":"NOT_LOCKED", "revision":0, "changed_fields":[], "record":None}
    changed = [key for key in ("data_mode", "questionnaire_snapshot_id", "profile", "portfolio")
               if fingerprint(record["facts"].get(key)) != fingerprint(facts.get(key))]
    return {"status":"DRIFT_DETECTED" if changed else "LOCKED", "revision":record["revision"],
            "changed_fields":changed, "record":record}
