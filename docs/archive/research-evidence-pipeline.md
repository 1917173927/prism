# Research-to-Evidence pipeline

Phase 10 is the consumer boundary after an asynchronous run:

```text
ResearchRunExecutionResult
          ↓
   validate_claim (Phase 6)
          ↓
 bridge_cross_validation (Phase 8)
          ↓ READY only
 DecisionTrace: Evidence → Fact → Finding
```

Callers provide a `ResearchClaimSpec` containing a typed `ValidationClaim` and
explicit Finding metadata. The pipeline aggregates the execution's normalized
Observations; it never re-queries a provider or parses prose into a financial
number.

## Status semantics

- `READY` requires a `COMPLETED` run and every claim to be a clean
  `SUPPORTED` validation with two independent lineages. All generated Facts and
  Findings are placed into one closed `DecisionTrace`.
- `REVIEW_REQUIRED` is used for `INSUFFICIENT`, `CONTRADICTED`, or `UNRESOLVED`
  claims, and for any `PARTIAL`/`FAILED`/`EMPTY` run. A supported claim in a
  degraded run is re-labelled unresolved with an explicit node-degradation
  issue; no Fact/Finding is exposed in the trace.
- `BLOCKED` means the claim set or evidence closure is invalid (duplicate or
  foreign claim, missing Evidence, forged supported metadata, or unsafe input).

The pipeline retains validation and bridge statuses for review, but non-ready
traces contain no Fact or Finding. It never creates a Recommendation.

## Product difference

Prism separates “a node returned data” from “the conclusion is ready to use.”
Even when two sources agree, an incomplete run stays visible as review-required.
This lets the workbench explain both the evidence behind a conclusion and the
reason a conclusion was withheld—an auditable distinction that generic
multi-Agent chat products usually hide.

## Boundary for the next phase

The next layer may consume the READY `DecisionTrace` for independent risk and
compliance gates. It must preserve the same owner, evidence, and invalidation
closures; no gate may convert review/blocked output into a recommendation.
