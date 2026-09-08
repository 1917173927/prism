from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.service import FixtureAdvisorQueryService, confirm_questionnaire
from app.service.session_truth import SessionAssertionsRequest, TruthConfirmation, check_session_assertions, fingerprint, truth_status
from app.store.sqlite import StoreOwnerError


def facts(exclusions=()):
    template = FixtureAdvisorQueryService().query_template("alice")
    profile = confirm_questionnaire(template.questionnaire).model_dump(mode="json")
    profile["exclusions"] = list(exclusions)
    return {"data_mode": "MOCK", "questionnaire_snapshot_id": "questionnaire-1",
            "profile": profile, "portfolio": template.portfolio.model_dump(mode="json")}


def check(assertions=(), actions=(), exclusions=()):
    current = facts(exclusions)
    request = SessionAssertionsRequest.model_validate({"expected_revision": 1, "assertions": list(assertions), "actions": list(actions)})
    return check_session_assertions({"facts": current, "revision": 1}, current, request, owner_id="alice")


def claim(path, value, position_id=None):
    return {"path": path, "value": value, "position_id": position_id}


POSITION = "ui-template-position-etf-001"
ASSET = "ui-template-etf-001"


@pytest.mark.parametrize("value,status", [("1000.01", "PASS"), ("1000.011", "HALLUCINATED_DATA"),
    ("NaN", "HALLUCINATED_DATA"), ("Infinity", "HALLUCINATED_DATA"), ("1e999999999", "HALLUCINATED_DATA")])
def test_decimal_currency_tolerance_is_absolute_and_bounded(value, status):
    result = check([claim("portfolio.positions.market_value", value, POSITION)])
    assert result["results"][0]["status"] == status
    assert result["results"][0]["absolute_tolerance"] == "0.01"
    assert result["results"][0]["source_id"] == "ui-template-position-snapshot-001"


def test_quantity_has_zero_tolerance_and_profile_has_exact_enum_evidence():
    result = check([claim("portfolio.positions.quantity", "1.001", POSITION), claim("profile.risk_level", "BALANCED")])
    assert result["status"] == "VIOLATION"
    assert result["results"][0]["absolute_tolerance"] == "0"
    assert result["results"][1]["status"] == "PASS"
    assert result["facts_fingerprint"]


@pytest.mark.parametrize("path,position", [("portfolio.total_profit", None), ("portfolio.positions.quantity", "missing"),
                                         ("profile.risk_level", POSITION)])
def test_unknown_or_ambiguous_fact_reference_is_not_trusted(path, position):
    result = check([claim(path, "1", position)])
    assert result["results"][0]["reason"] == "UNKNOWN_FACT_REFERENCE"
    assert result["results"][0]["status"] == "HALLUCINATED_DATA"


def test_null_fact_is_unverified_not_fabricated():
    assert check([claim("portfolio.positions.sector", "科技", POSITION)])["results"][0]["status"] == "UNVERIFIED"


@pytest.mark.parametrize("exclusion", ["ETF", "基金", ASSET, "Synthetic Balanced ETF"])
def test_buy_conflicts_with_exact_confirmed_exclusion(exclusion):
    result = check(actions=[{"action": "BUY", "asset_id": ASSET}], exclusions=[exclusion])
    assert result["results"][0]["status"] == "ACTION_CONFLICT"
    assert result["results"][0]["matched_exclusions"] == [exclusion]


def test_free_text_exclusion_and_unknown_assets_are_not_claimed_verified():
    result = check(actions=[{"action": "BUY", "asset_id": ASSET}, {"action": "BUY", "asset_id": "new-stock"}],
                   exclusions=["不要投资高风险行业"])
    assert all(row["status"] == "UNVERIFIED" for row in result["results"])
    assert result["results"][0]["unverified_exclusions"] == ["不要投资高风险行业"]


def test_selling_excluded_asset_is_not_falsely_classified_as_conflict():
    assert check(actions=[{"action": "SELL", "asset_id": ASSET}], exclusions=["ETF"])["results"][0]["status"] == "UNVERIFIED"


def test_current_lock_and_revision_are_required():
    current = facts()
    request = SessionAssertionsRequest(expected_revision=1, assertions=[claim("profile.risk_level", "BALANCED")])
    assert check_session_assertions(None, current, request, owner_id="alice")["reason"] == "CURRENT_LOCK_REQUIRED"
    record = {"facts": deepcopy(current), "revision": 2}
    assert check_session_assertions(record, current, request, owner_id="alice")["status"] == "UNVERIFIED"
    record["revision"] = 1
    current["data_mode"] = "LIVE"
    assert check_session_assertions(record, current, request, owner_id="alice")["truth_status"] == "DRIFT_DETECTED"


def test_owner_validation_before_any_assertion_output():
    current = facts()
    request = SessionAssertionsRequest(expected_revision=1, assertions=[claim("profile.risk_level", "BALANCED")])
    with pytest.raises(StoreOwnerError):
        check_session_assertions({"facts": current, "revision": 1}, current, request, owner_id="bob")


def test_confirmation_preview_exposes_current_fingerprint_without_mutation():
    current = facts()
    original = deepcopy(current)
    preview = truth_status(None, current)
    assert preview["current_fingerprint"] == fingerprint(current)
    assert preview["current_facts"] == current
    confirmed = TruthConfirmation(expected_revision=0, expected_fingerprint=preview["current_fingerprint"])
    assert confirmed.expected_fingerprint == fingerprint(current)
    with pytest.raises(ValidationError):
        TruthConfirmation(expected_revision=0, expected_fingerprint="not-a-fingerprint")
    assert current == original


@pytest.mark.parametrize("payload", [
    {"expected_revision": True, "assertions": [claim("profile.risk_score", "1")]},
    {"expected_revision": 1},
    {"expected_revision": 1, "assertions": [claim("profile.risk_score", 1.0)]},
    {"expected_revision": 1, "assertions": [claim("profile.risk_score", "1")] * 31},
    {"expected_revision": 1, "actions": [{"action": "BUY", "asset_id": ASSET, "asset_type": "CASH"}]},
])
def test_strict_bounded_request_contract(payload):
    with pytest.raises(ValidationError):
        SessionAssertionsRequest.model_validate(payload)
