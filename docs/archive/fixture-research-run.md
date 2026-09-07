# Fixture-backed asynchronous research run

Phase 9 connects the existing contracts into an offline executable slice:

```text
ResearchPlan + node ProviderRequest
              ↓
      execute_research_run
              ↓
bounded Provider calls (parallel ready nodes)
              ↓
ResearchNodeResult + Evidence + ResearchObservation
              ↓
      replayable ResearchRunState
```

`execute_research_run` accepts a `FinancialProvider` implementation instead of
choosing a data source. In tests this is `FixtureFinancialProvider`; a future
SkillHub adapter can be injected only after its contract and authorization are
confirmed.

## Execution semantics

- The runner calls Phase 7's `start_research_run`, `record_node_result`, and
  `finish_research_run`; it never edits run state directly.
- All currently ready nodes are awaited with `asyncio.gather`. Dependents are
  scheduled only in the next round after their parents are `COMPLETE`.
- Request timeouts are bounded by both the node timeout and remaining run
  budget, then passed through `execute_with_budget`.
- Provider `SUCCESS`, `PARTIAL`, `EMPTY`, and `FAILED` map to typed research
  results. Missing/failed/empty data stays explicit; no numeric zero is
  synthesized.
- Normalized Evidence retains textual fields such as a fund name. Only finite
  scalar fields with a unit and period become `ResearchObservation` values.
  Missing lineage remains visible but cannot later prove independent support.
- Observation IDs are stable hashes of owner, node, and Evidence ID. Output
  Evidence and Observation IDs are unique and closure-checked.

Provider exceptions, timeout responses, unsafe metadata, and identity mismatches
become safe failed node results. Raw exception text, credentials, and provider
payloads are not stored in the run state or execution result.

## Product difference

Prism's parallelism is bounded and explainable rather than an unreviewable group
chat between Agents. A user can see which node completed, which returned an
empty scope, and which optional result degraded the run. Later phases can pass
the normalized output to cross-validation and the Evidence/Finding bridge, so
speed does not loosen the audit chain.

## Deliberate boundary

This phase does not implement live SkillHub/Tushare access, retry/cache/limit
infrastructure, LLM reasoning, CrossValidation invocation, Fact/Finding
creation, risk/compliance, Recommendation, persistence, API, UI, browser
acceptance, or production SLA claims.
