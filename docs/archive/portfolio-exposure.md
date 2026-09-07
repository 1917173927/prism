# Portfolio Exposure Contract

Phase 3 consumes the owner-closed Phase 2 `PortfolioImportBundle` and produces
an auditable deterministic look-through report. It is the numeric boundary for
future concentration and risk-budget modules; it is not a recommendation
engine.

## Calculation rules

All calculations use `Decimal`.

- Non-fund positions produce a `DIRECT` contribution using their imported
  market value.
- For an ETF or mutual fund with an as-of-valid `FundHoldingSnapshot`, each
  holding contributes `parent market value * weight_pct / 100` as
  `LOOK_THROUGH`.
- Any parent value not represented by reported holding weights produces an
  `UNLOOKED_THROUGH` residual. Reported weights are never normalised or
  extrapolated from `coverage_pct`.
- A missing or future look-through snapshot leaves the entire parent as a
  residual and returns a `PARTIAL` issue. The same applies when source coverage
  or reported weights leave value unclassified.
- Only positions in the snapshot's base currency enter the numeric total. A
  different currency is excluded with a `NON_BASE_CURRENCY` issue; no FX rate
  is guessed.
- A zero total base-currency value returns `FAILED` and no report, so a
  genuine inability to compute a percentage cannot look like a 0% exposure.

`ExposureReport` verifies that every contribution closes the total market
value, that attributed and unclassified values close the same total, and that
all portfolio percentages are rounded Decimal percentages. The report also
stores the source position/holding IDs and parent identity for every row.

## Classification and status

Technology is a deliberately small deterministic rule: a trimmed,
case-folded sector must be exactly `technology`, `information technology`, or
`tech`. Unknown sectors remain unknown; no natural-language or LLM classifier is
used.

`ExposureResult` has three states:

| Status | Report | Meaning |
| --- | --- | --- |
| `COMPLETE` | required | every base-currency value is attributed and no issue exists |
| `PARTIAL` | required | a usable report exists, but residuals or safe data issues remain |
| `FAILED` | absent | no positive base-currency value is available to calculate |

The result, report, contributions, and issues all preserve `owner_id` and
stable bundle/position/holding identities. Contribution IDs are deterministic
hashes of those identities and their basis, so repeated calculation of the
same bundle has identical JSON.

## Deliberate non-goals

This phase does not perform FX conversion, historical return/volatility or
correlation calculations, HHI/concentration analysis, liquidity or stress
testing, risk budgets, profile conditioning, optimisation, recommendations,
network access, persistence, API work, UI work, or Evidence Contract changes.
Those capabilities require later phase plans and independent review gates.

Synthetic offline coverage is in
`tests/fixtures/portfolio/portfolio_exposure_bundle.json`; the unit and
integration tests cover residual closure, future and non-base data, fixed
technology classification, zero-value failure, status invariants,
immutability, and deterministic serialization.
