# Recommendation and Decision Receipt

Phase 12 is the first layer allowed to create the public `Recommendation`
contract. It consumes the accepted Phase 11 dual gate result and emits a
closed, deterministic decision:

```text
RiskProfile + PortfolioSnapshot
        + AllocationEnvelope
        + READY ResearchEvidencePipeline
        + PASS Risk/Compliance gates
        + AdvisoryCandidate
                     |
          deterministic Composer
                     |
 Recommendation -> Finding -> Fact -> Evidence
                     +
              DecisionReceipt
```

## Action boundary

The MVP Composer has two deliberately narrow modes:

- A balanced profile with no confirmed breach produces `HOLD` Recommendations
  for each ASSET band. The range is exactly the current weight.
- A profile with complete, deterministic breaches produces `REDUCE`
  Recommendations only for bands bound to every `remediation_breach_id`. The
  range is exactly the allocation band's bounded interval (`0` to its allowed
  maximum in the current policy).

The Composer never emits `ADD`, `EXIT`, a target price, quantity, expected
return, probability, or a reallocation of released cash. A deterministic
breach is therefore usable as a bounded risk-reduction proposal, while
incomplete or unresolved risk data remains review-required.

An aggregate sector, technology, or unclassified breach is not silently turned
into a security sell. Until a later phase supplies an explicit asset mapping,
the Composer blocks that case with a safe unmapped-breach reason.

The candidate's exact statement is used as the top-level summary and its exact
rationale is used on each Recommendation only after the current input set
recomputes to the same Phase 11 gate. No LLM or natural-language rewrite is
performed.

## Closure and stale-gate protection

`compose_recommendations` rebuilds every input through its Pydantic contract,
checks owner/profile/version and portfolio/report identities, and calls
`evaluate_decision_gates` again. A passed but stale gate, a different candidate,
or a `model_copy(update=...)` tampering attempt returns `REVIEW_REQUIRED` or
`BLOCKED` with an empty trace; it never reuses an old pass.

The final `DecisionTrace` is rebuilt from normalized Evidence, Fact, Finding and
new Recommendation objects. Existing closure validation then rejects unknown
Finding references, non-verified Facts/Evidence, duplicate IDs, or a
non-PASSED Recommendation chain.

Every Recommendation has a `RecommendationBinding` containing its allocation
band, dimension, target, current weight, allowed maximum, generated target
range, and breach IDs. The binding must match both the Recommendation range and
the selected remediation mode.

## Decision Receipt

`DecisionReceipt` contains replay metadata, not raw private holdings:

- owner/profile and position, exposure, concentration, risk, allocation and
  research identities;
- candidate and all three gate IDs;
- Evidence, Fact, Finding and Recommendation IDs;
- Recommendation-to-band/breach bindings;
- fixed rule versions for evidence, risk budget, allocation, compliance,
  composer and receipt; and `generation_mode=DETERMINISTIC` with no model
  versions;
- timezone-aware generation time, canonical trace hash and canonical receipt
  content hash.

Hashes use structured JSON with recursively sorted mapping keys and collection
items. This makes harmless input order changes stable while changing a material
value, rule, timestamp, binding or Recommendation content produces a different
hash. The Receipt validator recomputes `content_hash`; the composition result
recomputes `decision_trace_hash` and cross-checks all referenced IDs.

The receipt is an in-memory MVP artifact. It is not yet persisted, signed, or
presented through an API, and it is not a legal record.

## Product difference

Generic advisors usually return a sentence and lose the exact context that
produced it. Prism's Recommendation is one node in an immutable Receipt: the
user can see which profile version, portfolio snapshot, allocation constraint,
gate result, evidence and invalidation conditions were used. Changing the
profile from BALANCED to CONSERVATIVE changes the same holding from HOLD to
bounded REDUCE, making personalization an observable constraint effect rather
than a tone change.

## Next boundary

Phase 13 may expose the Composer and Receipt through owner-scoped persistence and
an API. It must preserve the receipt hashes, revalidate on read/write, and never
turn a review/blocked result into a Recommendation. Real SkillHub credentials,
regulatory policy coverage, browser UI and production SLA remain separate
acceptance items.
