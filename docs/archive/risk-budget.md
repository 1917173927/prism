# Concentration and Risk-Budget Contract

Phase 4 consumes a Phase 3 `ExposureResult` and a confirmed Phase 2
`RiskProfile`. It produces deterministic concentration groups and a small,
versioned set of profile-conditioned limits. It does not turn a breach into a
trade instruction.

## Concentration

`calculate_concentration` aggregates every exposure contribution twice:

- by `asset_id` for single-asset concentration;
- by a trimmed, case-folded sector for sector concentration.

Missing sectors and unlooked-through residuals stay in the explicit
`UNCLASSIFIED` sector group. No contribution is discarded to make a result
look safer. Groups carry source contribution IDs and owner identity, and both
asset and sector values must close the total exposure value.

Group weights are Decimal percentages rounded to two places. HHI is
`sum((group value / total value)^2) * 10000`, computed before weight rounding
and rounded to two places. Top-1 ordering is descending market value followed
by the stable group ID, so ties cannot vary between runs.

Partial or failed upstream exposure is propagated as `PARTIAL` or `FAILED`
concentration. A failed upstream report cannot produce a concentration report.

## Fixed v1 budget

`build_risk_budget` maps the confirmed `RiskLevel` to these versioned limits:

| Risk level | Single asset | Known sector | Technology | Unclassified |
| --- | ---: | ---: | ---: | ---: |
| `CONSERVATIVE` | 20% | 30% | 25% | 10% |
| `BALANCED` | 35% | 45% | 40% | 20% |
| `GROWTH` | 50% | 60% | 60% | 35% |

The profile's maximum drawdown tolerance is copied into the budget as a
separate constraint. This phase has no historical return series, so it does
not invent an observed drawdown or volatility number.

`assess_risk_budget` emits explicit `RiskBudgetBreach` rows for single-asset,
known-sector, technology, or unclassified excesses. It returns:

- `PASS` only when concentration is complete and no breach exists;
- `REVIEW_REQUIRED` when any breach or partial-data issue exists;
- `BLOCKED` when no concentration report is available.

The output has no recommendation/action field. A later phase must decide how,
or whether, to respond to a breach.

## Product difference

The same exposure is intentionally evaluated against different limits for a
conservative and a growth profile. The resulting difference is explainable by
the profile ID/version, the fixed ruleset, and the exact concentration group,
not by an opaque model score.

## Non-goals and verification

This phase does not calculate correlation, volatility, Beta, VaR, liquidity,
stress loss, realized drawdown, FX, optimization, allocation ranges,
recommendations, network data, persistence, API, UI, or Evidence changes.

Synthetic offline tests cover group closure, HHI, stable tie-breaking, partial
and failed propagation, budget differences, explicit breaches, owner closure,
immutability and absence of recommendation fields. Run them with:

```powershell
python -m pytest
python -m compileall -q app
python -c "from app.risk import RiskBudget, ConcentrationReport; print('phase4-import-ok')"
```
