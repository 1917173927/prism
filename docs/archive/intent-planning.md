# Structured Investment Intent and Plan Preview

Phase 22 adds a small, explicit boundary between a user's selected research
question and the existing four-track research matrix. It is a deterministic
preview boundary, not a natural-language agent or a research result.

## Contract

`advisor-intent-request.v1` contains only a replayable identity summary:

```json
{
  "schema_version": "advisor-intent-request.v1",
  "intent_id": "ui-profile-confirmation-questionnaire-plan",
  "owner_id": "demo-owner",
  "intent_type": "TECHNOLOGY_EXPOSURE_REVIEW",
  "generated_at": "2026-09-02T06:00:00+00:00",
  "portfolio_bundle_id": "portfolio-demo-owner",
  "position_snapshot_id": "positions-demo-owner",
  "questionnaire_id": "ui-profile-confirmation-questionnaire"
}
```

The supported `intent_type` values are deliberately finite:

- `TECHNOLOGY_EXPOSURE_REVIEW`
- `PORTFOLIO_RISK_REVIEW`

The request is strict (`extra=forbid`), owner-scoped by `X-Owner-ID`, requires a
timezone-aware timestamp and rejects sensitive substrings. The IDs identify the
session context; they are not a claim that a client-supplied summary proves a
real brokerage account.

`advisor-plan-response.v1` returns the stable plan identity, the selected intent,
the same owner/context IDs, an explainable scope, the four specialist roles and
the matrix node count. It intentionally contains no Provider response,
Evidence, Fact, Finding, Recommendation, order, or Receipt.

## API

```text
POST /api/v1/advisor/plans
X-Owner-ID: <owner>
Content-Type: application/json
```

The endpoint calls only `FixtureResearchSpecialistMatrixService.matrix_template`
and the deterministic intent mapper. It does not execute a research run, call a
Provider, or write `DecisionEventStore`. Repeating the same request returns the
same `plan_id` and response.

## Workbench behavior

The Advisor form offers the two intent types and a **预览任务计划** action. The
preview shows the plan/context identities and the Macro, Industry, Stock and
ETF/Fund tracks. Running Advisor remains a separate explicit action and still
uses the existing Profile → Portfolio → Research → Gate → Recommendation →
Receipt chain.

The browser clears a plan when its owner, confirmed Portfolio, confirmed Risk
Profile, questionnaire fields, selected intent, template, or request sequence
changes. Dynamic values use `textContent` and all requests are same-origin.

## Boundary and product choice

Prism makes the task decomposition inspectable before it produces a decision.
This is the product difference from a generic “ask a model to review my
portfolio” flow: users can see the scope and specialist responsibilities, then
trace the eventual decision through the existing Evidence → Receipt chain. The
phase does **not** add natural-language parsing, LLM/Gemini calls, online
SkillHub access, authentication, persistence, new financial calculations, or
trade execution.
