# Independent risk and compliance gates

Phase 11 adds two deterministic gates between the research Evidence pipeline
and future Recommendation composition:

```text
READY ResearchEvidencePipelineResult
                 +
RiskProfile -> RiskBudgetAssessment -> AllocationResult
                 +
          AdvisoryCandidate
                 |
        +--------+--------+
        |                 |
   Risk gate       Compliance gate
        |                 |
        +--------+--------+
                 |
       DecisionGateResult
                 |
        PASS only: eligible for
        Phase 12 composition
```

The gates do not create a `Recommendation`, choose an action, optimize a
portfolio, or execute an order. `AdvisoryCandidate` is a frozen preflight input
whose prose is checked in memory and deliberately omitted from every gate
result.

## Shared status semantics

- `PASS` means the gate's complete deterministic policy is satisfied.
- `REVIEW_REQUIRED` preserves incomplete research, unresolved/partial risk
  inputs, or missing required disclosures. It cannot be treated as eligibility
  for a Recommendation.
- `BLOCKED` means an input is invalid, foreign, tampered, evidence-incomplete,
  based on non-verified data, or contains prohibited language.

The combined status is `BLOCKED > REVIEW_REQUIRED > PASS`.
`eligible_for_recommendation` is true only when both independent child gates
are `PASS`.

## Risk gate closure

`evaluate_risk_gate` consumes existing artifacts; it does not recalculate
portfolio exposure or concentration. Before evaluating status it rebuilds all
inputs through their Pydantic contracts so unchecked `model_copy(update=...)`
changes cannot bypass invariants.

The gate verifies:

- one owner across profile, research pipeline, assessment, and allocation;
- one profile ID, version, risk level, and drawdown tolerance;
- a READY research trace containing only VERIFIED Facts and Evidence;
- budget, assessment, exposure report, concentration report, and allocation
  envelope identities and timestamps;
- every allocation band uses the limit selected by the active risk budget;
- required technology and unclassified bands exist, and allocation breach IDs
  close exactly over the assessment breaches;
- assessment and allocation statuses agree.

A complete deterministic budget breach is not the same as missing risk data.
When assessment breaches have no upstream issue and a review allocation
envelope closes every breach through concrete `OVER_LIMIT` bands, the risk gate
may PASS with `remediation_required=true` and the exact breach IDs. This only
authorizes Phase 12 to compose a risk-reducing proposal inside those bands. A
partial issue or any `UNRESOLVED` band remains `REVIEW_REQUIRED`; blocked input
remains blocked. The result contains only stable IDs, checked references,
status, remediation metadata, and static safe issues.

## Compliance policy v1

`evaluate_compliance_gate` verifies that a candidate belongs to the same owner
and references only Findings registered in the current READY trace. Every
referenced Finding must close through VERIFIED Facts to VERIFIED Evidence.

Four machine-readable disclosures are mandatory:

- `NO_GUARANTEE`
- `LOSS_RISK`
- `EVIDENCE_SCOPE`
- `INVALIDATION_CONDITIONS`

A missing disclosure produces `REVIEW_REQUIRED`. The candidate and every
referenced Finding are scanned by bounded deterministic policy for:

- guarantee/no-loss language such as guaranteed return, risk-free, sure win,
  保证收益、稳赚、保本、无风险或必涨;
- numeric target-return promises such as 目标/预期收益率达到 12%;
- credential-shaped or secret-shaped keys.

Any match is `BLOCKED`. Standard negative disclosures such as 不保证收益 or
not guaranteed are not misclassified as a promise. Rejected prose is never
copied into the result; only a static policy code and safe message are kept.

This is a bounded MVP policy and not a claim of complete regulatory coverage or
legal advice. Later policy versions may add jurisdiction, product-suitability,
marketing, and license rules without allowing the generator to self-approve.

## Audit and product difference

Gate IDs bind the full serialized inputs through local SHA-256 signatures, so
changing content under the same candidate or artifact ID changes the gate ID
without exposing the content. Results are frozen and have deterministic issue
and reference ordering.

Prism's differentiator is not a disclaimer appended after generated advice.
Risk and compliance are independent prerequisites: incomplete evidence,
profile/portfolio mismatch, budget breaches, and prohibited promises can all
withhold advice with an explicit auditable reason. “Why no recommendation is
available” is therefore a first-class product result.

## Phase 12 boundary

Phase 12 may compose a Recommendation only from a `DecisionGateResult` with
`status=PASS` and `eligible_for_recommendation=true`. It must reuse the checked
Finding IDs, allocation envelope, invalidation conditions, and child gate IDs.
It may not turn `REVIEW_REQUIRED` or `BLOCKED` into an actionable output, alter
the risk limits, or fabricate a missing Evidence link. When
`remediation_required=true`, Phase 12 must only emit risk-reducing actions bound
to `remediation_breach_ids`; it cannot use that PASS to justify adding risk.
