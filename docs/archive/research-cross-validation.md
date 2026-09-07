# Structured Research and Cross-Validation Contract

Phase 6 defines the smallest research boundary that can be consumed by a
future structured DAG. It does not fetch data. A node records typed scalar
observations and an explicit four-state result; the validator then compares one
claim with observations that are aligned by subject, metric, unit and period.

## Research node states

`ResearchNodeResult` uses the following states:

| State | Meaning |
| --- | --- |
| `COMPLETE` | At least one usable observation and no missing field or issue. |
| `PARTIAL` | Usable observations exist, but fields or source coverage are incomplete. |
| `EMPTY` | The declared scope was searched and no observation matched; no issue is hidden. |
| `FAILED` | The source/node was unavailable or invalid; no observation is emitted. |

Observations are scalar `Decimal` values carrying owner, evidence ID,
provider/source, quality status, period and optional explicit lineage. Non-
`VERIFIED` observations remain review metadata and never become support votes.
The node contract rejects duplicate observation/evidence IDs and illegal state
combinations.

## Lineage-aware validation

`ValidationClaim` fixes the expected value and its subject/metric/unit/period.
`validate_claim` first excludes scope-mismatched observations and non-`VERIFIED`
observations. Explicit `lineage_id` is the only proof of independence:

- repeated rows under one lineage are listed as duplicates and count once;
- different lineages may support or contradict a claim;
- observations without lineage are visible but cannot prove independent support;
- a lineage containing different values is itself unresolved.

The result states are:

- `SUPPORTED`: at least two independent lineages support the value and no
  unresolved input or independent contradiction exists;
- `CONTRADICTED`: at least two independent lineages disagree and none supports;
- `UNRESOLVED`: independent support and contradiction coexist, or a mismatch,
  non-verified observation, lineage conflict or partial node prevents a clean
  conclusion;
- `INSUFFICIENT`: fewer than two independent usable lineages are available,
  including empty/failed nodes and unlinked-only observations.

`confidence` is a fixed Decimal agreement/coverage indicator: `1.00` for a
fully supported claim, `0.00` for a clean contradiction or no independent
coverage, and the supporting-lineage ratio for unresolved conflicts. It is not
a return probability, win rate or model confidence. The `methodology` field
states that this is equality/lineage logic rather than a majority vote.

## Product difference and audit closure

Prism does not treat “three Agents repeated the same article” as evidence. A
reviewer can inspect the exact evidence IDs, provider/source, lineage, period,
quality and reason for exclusion. This makes disagreement and missing data
visible, and lets the same market fact remain stable while profile-conditioned
allocation (Phase 5) or later compliance decisions change.

The result contains only claim and evidence references plus safe issues. It does
not create `Fact`, `Finding`, `Recommendation` or `DecisionTrace` objects; a
later phase must perform those transformations under the Evidence Contract.

## Deliberate non-goals

This phase does not implement Wencai/SkillHub/Tushare adapters, network or
credentials, LLM prompts, macro/industry/stock/fund financial formulas,
orchestration/DAG scheduling, retries, caching, persistence, APIs, UI,
correlation, volatility, returns, risk scoring, compliance prose, optimization,
orders or portfolio recommendations.

Run the offline checks with:

```powershell
python -m pytest
python -m compileall -q app
python -c "from app.research import ResearchNodeResult, validate_claim; print('phase6-import-ok')"
```
