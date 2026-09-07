# Evidence-grounded Fact/Finding Bridge

Phase 8 adds a deterministic registration boundary between the structured
research validation result and Prism's existing evidence graph:

```text
CrossValidationResult + ResearchObservation + Evidence
                  ↓
     EvidenceFindingBridgeResult
                  ↓ READY only
        VERIFIED Fact → Finding
```

The bridge is deliberately not a provider, agent, recommendation composer, or
compliance engine. It verifies that the already-normalized objects still agree
before making a fact available to later phases.

## Ready conditions

`bridge_cross_validation(...)` returns `READY` only when all of these are true:

- the validation status is `SUPPORTED` with at least two independent lineages;
- there are no validation issues, contradictions, unresolved IDs, duplicate
  lineage IDs, or unlinked support IDs;
- every supporting ID exists in the `Evidence` registry and has exactly one
  owner/lineage binding in `ResearchObservation`;
- owner, subject, metric, unit, period, value, provider, source, lineage and
  retrieval/observation timestamps match between the validation, observation,
  and Evidence row;
- every selected Evidence and observation is `VERIFIED`;
- the finding metadata is explicit and safe.

The resulting `Fact` uses a stable hash ID (`fact:<sha256-prefix>`) derived from
owner, claim, scope, value, and supporting evidence IDs. The `Finding` likewise
uses a stable hash ID and references exactly that Fact. Therefore a
`DecisionTrace` can close the chain without trusting a free-form source URL.

## Degraded states

- `REVIEW_REQUIRED`: the validation is `CONTRADICTED`, `UNRESOLVED`, or
  `INSUFFICIENT`; no Fact or Finding is emitted.
- `BLOCKED`: a `SUPPORTED` label cannot be reconciled with the registered
  Evidence/observation data, or the input contains an unknown ID, scope/owner
  mismatch, non-verified row, duplicate, sensitive text, or forged metadata.

Issues contain only stable codes, bounded safe identifiers, and static safe
messages. Raw provider payloads, exceptions, credentials, and validation issue
text are not copied into the bridge output.

## Why this matters to the product

Many multi-agent products show a fluent conclusion and a source link. Prism's
distinguishing behavior is stricter: a research conclusion is not a usable fact
until it closes through independent lineage and exact value/period/unit checks.
When the chain cannot be closed, the UI can show *待复核* or *已阻断* and explain
which invariant failed. This makes the smallest trustworthy adjustment and its
invalidation conditions reviewable instead of hiding uncertainty behind prose.

## Deliberate boundary

This phase does not create `Recommendation`, allocation actions, risk/compliance
decisions, network calls, persistence, LLM output, or UI state. A future phase
may consume the verified Finding, but must preserve the same
`Recommendation → Finding → Fact → Evidence` closure.
