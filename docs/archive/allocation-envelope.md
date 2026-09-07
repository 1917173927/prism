# Allocation Envelope Contract

Phase 5 consumes the confirmed `RiskProfile`, the Phase 3 `ExposureResult`,
the Phase 4 `ConcentrationResult`, and the Phase 4 `RiskBudgetAssessment`. It
returns a deterministic constraint envelope: what the current snapshot weighs,
which profile-conditioned cap applies, and the smallest percentage-point
reduction needed to reach that cap.

## What a band means

`AllocationBand` is one auditable row for an asset, a known sector, the
technology aggregate, or the unclassified aggregate. It contains:

- the owner/profile/budget context and a stable target ID;
- current weight and the applicable fixed v1 budget maximum;
- a target interval and `minimum_reduction_pct`;
- `WITHIN_LIMIT`, `OVER_LIMIT`, or `UNRESOLVED` disposition;
- the exact Phase 4 breach IDs when the observed row is over its limit.

The disposition is a constraint state, not a trade action. `OVER_LIMIT` means
that a reduction would be required to satisfy that one cap; it does not choose
an asset to sell, a price, a quantity, or a destination for released cash.

Within-limit rows have a degenerate hold interval equal to their current
weight. Over-limit rows expose `[0, allowed_max]` and the exact excess as the
minimum reduction. When any upstream input is partial, every row is
`UNRESOLVED`: the numeric observation remains visible for review but cannot be
treated as a passed result.

## Before/after impact semantics

`ConstraintImpact` compares one row's current weight with its own budget cap.
It is a constraint-only scenario. Impacts are intentionally not summed across
asset, sector, technology, and unclassified dimensions because those rows can
overlap. No reallocation, return estimate, risk probability, or portfolio
backtest is implied.

`AllocationResult` has three states:

| State | Meaning |
| --- | --- |
| `READY` | Complete upstream data and no observed budget breach. |
| `REVIEW_REQUIRED` | A valid report has a breach or partial coverage; human review is required. |
| `BLOCKED` | Exposure/concentration/budget is unavailable; no envelope is emitted. |

The envelope always records profile version, budget ID, assessment ID,
concentration report ID, and exposure report ID. It also carries these
invalidation conditions:

1. risk-profile version changes;
2. the position or fund-holdings snapshot changes;
3. look-through coverage or base currency changes.

## Product difference

The same exposure is evaluated against different fixed limits for conservative,
balanced, and growth profiles. The difference is explainable by those profile
and budget identifiers plus the exact concentration row, rather than by an
opaque model score. This is the smallest deterministic bridge from “what is in
the portfolio” to “which constraints matter for this person.”

## Deliberate non-goals

This phase does not create `Recommendation`, `Finding`, `Fact`, `Evidence`, or
`DecisionTrace` objects. It does not perform correlation, volatility, VaR,
drawdown measurement, liquidity, tax/fee/slippage, FX, optimization, risk
parity, mean-variance allocation, order generation, network acquisition,
persistence, API, orchestration, LLM interpretation, or UI rendering.

Use the offline verification commands:

```powershell
python -m pytest
python -m compileall -q app
python -c "from app.allocation import AllocationEnvelope; print('phase5-import-ok')"
```
