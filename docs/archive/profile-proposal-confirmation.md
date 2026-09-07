# Structured Profile Proposal and Confirmation

Phase 23 exposes the profile extraction boundary that was defined in Phase 2 but
was previously only used by domain tests. It accepts a typed candidate proposal,
shows real conflicts against the current questionnaire, and requires an
explicit choice before producing a `RiskProfile`.

## Contracts and API

`advisor-profile-proposal-request.v1` contains:

- the current `RiskQuestionnaire`;
- one `ProfileExtractionProposal` with typed optional dimensions,
  preferences/exclusions, confidence, timezone-aware `extracted_at`, and a
  64-character `input_digest`.

`POST /api/v1/advisor/profile-proposals` revalidates both owners and rebuilds a
`ProfileDraft` on the server. A mismatch returns a `REQUIRES_CONFIRMATION`
draft with one `ProfileConflict` per differing dimension. A matching proposal
is `READY`, but the UI still asks for explicit confirmation.

`advisor-profile-confirmation-request.v1` repeats the questionnaire and typed
proposal and adds a mapping of conflict IDs to `USE_QUESTIONNAIRE` or
`USE_EXTRACTION`. The server rebuilds the draft instead of trusting a client
draft, then calls the existing `finalize_profile`. Unknown IDs, omitted choices
for real conflicts, unresolved choices, and owner mismatches are refused.

`advisor-profile-confirmation-response.v1` returns the deterministic
`RiskProfile`, including the resolved conflict records, selected dimensions,
confidence, extraction ID, and stable profile ID. Neither endpoint writes the
decision-event store or creates a Recommendation/Receipt.

## Workbench behavior

The Risk Profile panel retains the existing questionnaire confirmation and adds
a separate typed proposal preview. The proposal input is JSON only; the UI
does not parse natural language or send the original text. Each conflict shows
the questionnaire value beside the extraction value and provides an explicit
choice. Confirmation remains disabled until all displayed conflicts are
resolved.

Owner changes, questionnaire edits, template failures, and stale async
responses clear the proposal, selections, JSON input, and confirmed result.
Dynamic values are rendered with `textContent` and requests are same-origin.

## Safety and product boundary

`ProfileExtractionProposal` rejects sensitive substrings in typed values and
requires a timezone-aware timestamp; API errors use a fixed safe message. The
digest is an audit identity for a separately handled input and is not proof of
account authenticity.

This makes Prism's differentiation visible: a user's constraints are not a
hidden model label. The user can see which extracted dimension conflicts with
the questionnaire and choose the value that should affect later work. Phase 23
does not implement natural-language/LLM/Gemini extraction, external SkillHub or
broker access, persistence, authentication, new scoring formulas, trade
execution, or automatic Recommendation binding.
