# Profile / Portfolio Import Contracts

Phase 2 fixes the input boundary for the flagship “technology-fund concentrated
portfolio check-up” slice. It records a deterministic user profile and raw
portfolio observations so a later risk/portfolio engine can explain why two
owners receive different constraints from the same evidence.

This document describes the implemented contract boundary. It does not claim
that a live broker, SkillHub, Tushare, database, API, UI, or recommendation
engine exists.

## Profile boundary

`app.profile.RiskQuestionnaire` is the deterministic baseline. It contains
versioned, timezone-aware answers:

- loss tolerance: integer `1..5`;
- investment horizon: `SHORT`, `MEDIUM`, `LONG`;
- liquidity need: `LOW`, `MEDIUM`, `HIGH`;
- experience: `NOVICE`, `INTERMEDIATE`, `EXPERIENCED`;
- return expectation: `LOW`, `MODERATE`, `HIGH`;
- maximum drawdown tolerance: decimal percentage `0..100`;
- optional expected-return range with ordered `0..100` endpoints.

`score_questionnaire` maps the five discrete dimensions to a `0..100` Decimal
score. The fixed weights are loss tolerance `30%`, horizon `25%`, reversed
liquidity need `20%`, experience `10%`, and return expectation `15%`. The
levels are `0..33 CONSERVATIVE`, `34..66 BALANCED`, and `67..100 GROWTH`.
Maximum drawdown tolerance is retained as a separate constraint; it is not
inferred from the score.

`ProfileExtractionProposal` is not an LLM output sink. It accepts only typed
candidate values, preference/exclusion lists, a confidence value, and a
64-character input digest. Raw natural language, prompts, credentials, and
free-form diagnostics are not model fields.

`build_profile_draft` compares the proposal with the questionnaire. A
dimension mismatch creates a `ProfileConflict` and makes the draft
`REQUIRES_CONFIRMATION`. `finalize_profile` requires an explicit choice of
`USE_QUESTIONNAIRE` or `USE_EXTRACTION`, then preserves the resolved conflict
in the resulting immutable `RiskProfile`. No silent overwrite is allowed.

Every profile object carries an `owner_id`, forbids unknown fields, is frozen,
and requires timezone-aware timestamps. Duplicate preference, exclusion, or
conflict identities are rejected.

## Portfolio import boundary

`Position` is one raw owner position and carries the same `owner_id` as its
snapshot. Quantity is strictly positive; market value and all weights use
`Decimal`; currency is a three-letter code; source and observation time are
retained. `PositionSnapshot` is a non-empty, owner-scoped point-in-time
snapshot with unique `position_id` values.

`PositionImportResult` keeps four states separate:

| Status | Snapshot | Required explanation |
| --- | --- | --- |
| `COMPLETE` | present | no missing fields or issues |
| `PARTIAL` | usable partial snapshot | missing fields and/or safe issues |
| `EMPTY` | absent | explicit checked scope, with no error |
| `FAILED` | absent | at least one safe structured issue |

An empty import is never represented as a zero-value position. Failed imports
are never downgraded to empty. Issue objects contain only a safe message,
stable issue code, optional row reference, and retryability; they do not carry
raw provider responses or credentials.

`LookThroughHolding` and `FundHoldingSnapshot` retain source-reported
constituents, parent identity, observation time, `weight_pct`, and
`coverage_pct`. Holding weights are individually bounded to `0..100` and sum to
no more than `100`. Coverage is source metadata, not a calculated portfolio
exposure. Parent types are limited to ETF or mutual fund and each holding must
refer to its snapshot's parent.

`PortfolioImportBundle` closes the owner and parent identity graph: every
snapshot belongs to the same `owner_id`, every fund/ETF parent exists in the
position snapshot with the same asset type, and each parent has at most one
fund-holdings snapshot in the bundle. The bundle deliberately contains no
exposure, concentration, correlation, liquidity, risk-budget, or allocation
fields; those are Phase 3 responsibilities.

## Synthetic verification

`tests/fixtures/profile/profile_case.json` and
`tests/fixtures/portfolio/portfolio_bundle.json` are synthetic and credential
free. Integration tests load them through Pydantic model validation and prove
that a later module can consume a confirmed profile and an owner-closed raw
portfolio bundle without network access.

Run the complete contract suite with:

```powershell
python -m pytest
python -m compileall -q app
python -c "from app.profile import RiskProfile; from app.portfolio import PositionSnapshot; print('phase2-import-ok')"
```

The Phase 2 suite does not implement live data acquisition, persistence,
natural-language extraction, portfolio analytics, risk calculations, or
recommendations.
