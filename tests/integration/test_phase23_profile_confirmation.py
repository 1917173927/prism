"""Phase 23 structured profile proposal and explicit conflict confirmation."""

from __future__ import annotations

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api import create_app
from app.api.contracts import AdvisorProfileConfirmationRequest
from app.profile import ProfileExtractionProposal
from app.store import SQLiteDecisionEventStore


OWNER = "phase23-profile-owner"


def _client() -> tuple[TestClient, SQLiteDecisionEventStore]:
    store = SQLiteDecisionEventStore(":memory:")
    return TestClient(create_app(store)), store


def _template(client: TestClient, owner: str = OWNER) -> dict:
    response = client.get(
        "/api/v1/advisor/query-template",
        headers={"X-Owner-ID": owner},
    )
    assert response.status_code == 200
    return response.json()


def _extraction(owner: str = OWNER, **overrides: object) -> dict:
    values: dict[str, object] = {
        "schema_version": "profile-extraction.v1",
        "extraction_id": "phase23-extraction-001",
        "owner_id": owner,
        "input_digest": "a" * 64,
        "extracted_at": "2026-09-02T00:00:00Z",
        "confidence": "0.80",
        "investment_horizon": "SHORT",
        "liquidity_need": "HIGH",
        "experience_level": "NOVICE",
        "return_expectation": "LOW",
        "max_drawdown_tolerance_pct": "10",
        "asset_preferences": ["ETF_TECH"],
        "sector_preferences": ["Technology"],
        "exclusions": ["LEVERAGED"],
    }
    values.update(overrides)
    return values


def _proposal_payload(template: dict, extraction: dict | None = None) -> dict:
    return {
        "schema_version": "advisor-profile-proposal-request.v1",
        "questionnaire": template["questionnaire"],
        "extraction": extraction or _extraction(),
    }


def test_proposal_preview_is_deterministic_and_exposes_real_conflicts() -> None:
    client, store = _client()
    template = _template(client)
    payload = _proposal_payload(template)
    first = client.post(
        "/api/v1/advisor/profile-proposals",
        headers={"X-Owner-ID": OWNER},
        json=payload,
    )
    replay = client.post(
        "/api/v1/advisor/profile-proposals",
        headers={"X-Owner-ID": OWNER},
        json=payload,
    )
    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    body = first.json()
    assert body["schema_version"] == "advisor-profile-proposal-response.v1"
    assert body["draft"]["status"] == "REQUIRES_CONFIRMATION"
    assert body["draft"]["owner_id"] == OWNER
    assert {item["dimension"] for item in body["draft"]["conflicts"]} == {
        "investment_horizon",
        "liquidity_need",
        "experience_level",
        "return_expectation",
        "max_drawdown_tolerance_pct",
    }
    assert body["draft"]["extraction"]["input_digest"] == "a" * 64
    assert "raw_natural_language" not in first.text.casefold()
    assert store.list(OWNER) == ()
    store.close()


def test_explicit_resolution_changes_profile_and_retains_conflict_audit() -> None:
    client, store = _client()
    template = _template(client)
    extraction = _extraction()
    preview = client.post(
        "/api/v1/advisor/profile-proposals",
        headers={"X-Owner-ID": OWNER},
        json=_proposal_payload(template, extraction),
    )
    assert preview.status_code == 200
    conflicts = preview.json()["draft"]["conflicts"]
    questionnaire_resolution = {
        item["conflict_id"]: "USE_QUESTIONNAIRE" for item in conflicts
    }
    extraction_resolution = {
        item["conflict_id"]: "USE_EXTRACTION" for item in conflicts
    }

    first = client.post(
        "/api/v1/advisor/profile-proposals/confirm",
        headers={"X-Owner-ID": OWNER},
        json={
            "schema_version": "advisor-profile-confirmation-request.v1",
            "questionnaire": template["questionnaire"],
            "extraction": extraction,
            "resolutions": questionnaire_resolution,
        },
    )
    second = client.post(
        "/api/v1/advisor/profile-proposals/confirm",
        headers={"X-Owner-ID": OWNER},
        json={
            "schema_version": "advisor-profile-confirmation-request.v1",
            "questionnaire": template["questionnaire"],
            "extraction": extraction,
            "resolutions": extraction_resolution,
        },
    )
    assert first.status_code == second.status_code == 200
    first_profile = first.json()["profile"]
    second_profile = second.json()["profile"]
    assert first.json()["schema_version"] == "advisor-profile-confirmation-response.v1"
    assert first_profile["profile_id"] != second_profile["profile_id"]
    assert first_profile["risk_level"] == "BALANCED"
    assert second_profile["risk_level"] == "CONSERVATIVE"
    assert all(item["resolution"] != "UNRESOLVED" for item in first_profile["conflicts"])
    assert all(item["resolution"] != "UNRESOLVED" for item in second_profile["conflicts"])
    assert store.list(OWNER) == ()
    store.close()


def test_no_conflict_proposal_still_requires_explicit_confirmation() -> None:
    client, store = _client()
    template = _template(client)
    questionnaire = deepcopy(template["questionnaire"])
    extraction = _extraction(
        investment_horizon=questionnaire["investment_horizon"],
        liquidity_need=questionnaire["liquidity_need"],
        experience_level=questionnaire["experience_level"],
        return_expectation=questionnaire["return_expectation"],
        max_drawdown_tolerance_pct=questionnaire["max_drawdown_tolerance_pct"],
        asset_preferences=[],
        sector_preferences=[],
        exclusions=[],
    )
    preview = client.post(
        "/api/v1/advisor/profile-proposals",
        headers={"X-Owner-ID": OWNER},
        json=_proposal_payload(template, extraction),
    )
    assert preview.status_code == 200
    assert preview.json()["draft"]["status"] == "READY"
    assert preview.json()["draft"]["conflicts"] == []
    confirmed = client.post(
        "/api/v1/advisor/profile-proposals/confirm",
        headers={"X-Owner-ID": OWNER},
        json={
            "schema_version": "advisor-profile-confirmation-request.v1",
            "questionnaire": template["questionnaire"],
            "extraction": extraction,
            "resolutions": {},
        },
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["profile"]["risk_level"] == "BALANCED"
    confirmation_model = AdvisorProfileConfirmationRequest.model_validate(
        {
            "schema_version": "advisor-profile-confirmation-request.v1",
            "questionnaire": template["questionnaire"],
            "extraction": extraction,
            "resolutions": {},
        }
    )
    with pytest.raises(TypeError):
        confirmation_model.resolutions["new-conflict"] = "USE_EXTRACTION"
    assert store.list(OWNER) == ()
    store.close()


def test_proposal_confirmation_rejects_unresolved_unknown_forged_and_owner_inputs() -> None:
    client, store = _client()
    template = _template(client)
    extraction = _extraction()
    payload = _proposal_payload(template, extraction)

    missing = client.post("/api/v1/advisor/profile-proposals", json=payload)
    assert missing.status_code == 403
    assert missing.json()["error_code"] == "OWNER_SCOPE"

    wrong_owner = client.post(
        "/api/v1/advisor/profile-proposals",
        headers={"X-Owner-ID": "phase23-other-owner"},
        json=payload,
    )
    assert wrong_owner.status_code == 403
    assert wrong_owner.json()["error_code"] == "OWNER_SCOPE"
    assert "phase23-other-owner" not in wrong_owner.text

    preview = client.post(
        "/api/v1/advisor/profile-proposals",
        headers={"X-Owner-ID": OWNER},
        json=payload,
    )
    conflicts = preview.json()["draft"]["conflicts"]
    unresolved = client.post(
        "/api/v1/advisor/profile-proposals/confirm",
        headers={"X-Owner-ID": OWNER},
        json={
            "schema_version": "advisor-profile-confirmation-request.v1",
            "questionnaire": template["questionnaire"],
            "extraction": extraction,
            "resolutions": {},
        },
    )
    assert unresolved.status_code == 400
    assert unresolved.json()["error_code"] == "PROFILE_PROPOSAL_ERROR"

    unknown = {
        conflicts[0]["conflict_id"]: "USE_QUESTIONNAIRE",
        "unknown-conflict": "USE_EXTRACTION",
    }
    unknown_response = client.post(
        "/api/v1/advisor/profile-proposals/confirm",
        headers={"X-Owner-ID": OWNER},
        json={
            "schema_version": "advisor-profile-confirmation-request.v1",
            "questionnaire": template["questionnaire"],
            "extraction": extraction,
            "resolutions": unknown,
        },
    )
    assert unknown_response.status_code == 400
    assert unknown_response.json()["error_code"] == "PROFILE_PROPOSAL_ERROR"
    assert "unknown-conflict" not in unknown_response.text

    forged = {**payload, "draft": {"status": "READY"}}
    forged_response = client.post(
        "/api/v1/advisor/profile-proposals",
        headers={"X-Owner-ID": OWNER},
        json=forged,
    )
    assert forged_response.status_code == 422
    assert forged_response.json()["error_code"] == "INVALID_INPUT"

    mismatched_extraction = _extraction("phase23-other-owner")
    mismatch_response = client.post(
        "/api/v1/advisor/profile-proposals",
        headers={"X-Owner-ID": OWNER},
        json=_proposal_payload(template, mismatched_extraction),
    )
    assert mismatch_response.status_code == 422
    assert mismatch_response.json()["error_code"] == "INVALID_INPUT"
    assert store.list(OWNER) == ()
    store.close()


def test_proposal_boundary_rejects_sensitive_and_naive_inputs_without_echo() -> None:
    client, store = _client()
    template = _template(client)
    sensitive = _extraction(sector_preferences=["secret account"])
    sensitive_response = client.post(
        "/api/v1/advisor/profile-proposals",
        headers={"X-Owner-ID": OWNER},
        json=_proposal_payload(template, sensitive),
    )
    assert sensitive_response.status_code == 422
    assert sensitive_response.json()["error_code"] == "INVALID_INPUT"
    assert "secret account" not in sensitive_response.text

    naive = _extraction(extracted_at="2026-09-02T00:00:00")
    naive_response = client.post(
        "/api/v1/advisor/profile-proposals",
        headers={"X-Owner-ID": OWNER},
        json=_proposal_payload(template, naive),
    )
    assert naive_response.status_code == 422
    assert naive_response.json()["error_code"] == "INVALID_INPUT"

    with pytest.raises(ValidationError):
        ProfileExtractionProposal.model_validate(sensitive)
    assert store.list(OWNER) == ()
    store.close()


def test_profile_proposal_boundary_has_no_external_or_html_injection_surface() -> None:
    client, store = _client()
    page = client.get("/")
    js = client.get("/static/app.js")
    css = client.get("/static/styles.css")
    assert page.status_code == js.status_code == css.status_code == 200
    assert 'id="profile-proposal-json"' not in page.text
    assert 'id="preview-profile-proposal"' not in page.text
    assert 'id="confirm-profile-proposal"' not in page.text
    assert "/api/v1/advisor/profile-proposals" in js.text
    assert "profile-extraction.v1" not in page.text
    assert "innerHTML" not in js.text
    assert "https://" not in page.text
    assert "fetch(\"http" not in js.text
    assert "gemini" not in js.text.casefold()
    assert ".profile-conflict" in css.text
    store.close()
