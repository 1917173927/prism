# Advanced Evidence UI contract

Phase 31 adds a read-only evidence explorer to the local Prism workbench. It is a
projection of results already loaded in the current browser session; it is not a second
evidence store or a search service.

## Input boundary

The explorer aggregates only owner-matching objects held in the current session:

| source | input | run identity |
|---|---|---|
| Advisor receipt | selected decision event `result.trace` | event id / receipt research run |
| Research Matrix | `state.researchRun.trace` | `run_id` |
| Stock Research | `state.stockResearchRun.trace` | `request_id` |
| ETF / Fund Research | `state.fundResearchRun.trace` | `request_id` |
| Convertible Bond Research | `state.convertibleBondResearchRun.trace` | `request_id` |

An object is ignored when its `owner_id` does not equal the current owner. The browser does
not fetch an evidence row, infer a source URL, or persist a raw provider payload. Changing
owner, changing a replay scenario, restoring context, or starting a new run clears the old
selection and its derived explorer index through the existing owner/sequence reset boundary.

## Row and detail semantics

Each row is keyed by source track plus `evidence_id`, sorted by source key and evidence ID.
Search covers only bounded normalized fields: evidence ID, provider, source, field, period,
lineage, source track and the displayed status labels. Filters are local and deterministic:

- quality: `VERIFIED`, `STALE`, `PARTIAL`, `CONFLICTING`, `INVALID`;
- serving mode: `DIRECT`, `CACHE_FRESH`, `FALLBACK_PROVIDER`,
  `CACHE_STALE_FALLBACK`, or `UNAVAILABLE` when a receipt has no node provenance;
- source track: Advisor, Matrix, Stock, Fund, Convertible Bond;
- promotion: `FINDING` (closed), `FACT` (fact only), or `AVAILABLE` (not promoted).

The detail pane retains the normalized `provider`, `source`, `field`, scalar value/unit,
period, observed/retrieved timestamps, lineage, run/owner, pipeline status and cache age.
Structured values are displayed as a bounded placeholder rather than dumping raw payloads.
The path section lists the actual linked Fact, Finding and Cross-Validation objects. When no
link exists it says that the Evidence remains auditable but does not constitute a conclusion.
Validation and pipeline issues use their existing safe code/message fields only.

## Freshness and degradation

`provider_serving_mode` comes from Phase 30's API node projection and is never guessed when a
node is available. A `STALE` row is conservatively displayed as
`CACHE_STALE_FALLBACK` when the stale node metadata is present (or inferred only from the
Evidence quality when it is not). Cache age is rendered in a human-readable form while the
raw millisecond value remains in the metadata label. `retrieved_at` is always the provider
timestamp from the response; a cache hit is not presented as a new retrieval.

Stale rows show a blocking review notice and cannot be represented as a verified fact by this
UI. Fallback rows preserve the fallback provider/source/lineage and show a review notice.
Partial, conflicting and invalid quality statuses retain review/blocked styling plus their
quality note. The explorer never upgrades a status or creates a recommendation.

## Product distinction and deliberate limits

Generic investment chat often presents a source link without showing whether the data was
fresh, cached, substituted or actually promoted through validation. Prism makes those choices
visible and clickable while preserving the same Evidence → Fact → Finding contract used by
the deterministic pipeline. This improves reviewability without pretending that a fixture is
live market data.

The phase does not add real SkillHub access, online authentication, backend indexing, semantic
search, automatic refresh, cloud persistence, sharing/export, LLM/Gemini output or trading
actions. Those boundaries remain deferred in `Prism.md` and the phase plan.
