# Bounded Research Orchestration Contract

Phase 7 fixes the state boundary around a future structured research DAG. It
does not run a DAG. `ResearchPlan` and `ResearchRunState` let an executor (in a
later phase) record exactly which node was eligible, started, completed,
degraded, cancelled or failed within one owner-scoped budget.

## Plan and topology

`ResearchNodeSpec` declares a node kind, whether it is required, its
dependencies and a positive node timeout. `build_research_plan` canonicalizes
node and dependency order, rejects unknown dependencies and cycles, and stores
a stable topological sequence. A node can only become runnable after every
dependency is `COMPLETE`; arrival order cannot change the plan order.

The synthetic flagship shape uses macro, industry, stock and fund nodes. The
fund node may be optional, while macro/industry/stock can be required. This is
only a fixture shape, not a claim that any real provider has been integrated.

## Run state machine

`create_research_run` fixes a positive total budget and its exact deadline
before work begins. Every transition returns a new frozen state:

| Run state | Meaning |
| --- | --- |
| `PENDING` | No node has started. |
| `RUNNING` | At least one eligible node is pending or running. |
| `COMPLETED` | Every node is `COMPLETE` and no issue exists. |
| `PARTIAL` | All nodes are terminal, required nodes are complete, and one or more optional nodes are incomplete. |
| `FAILED` | A required node is incomplete or the run deadline was exceeded. |
| `CANCELLED` | User/system cancellation ended a non-terminal run. |

`record_node_result` preserves Phase 6's node states. A required
`PARTIAL`/`EMPTY`/`FAILED` result fails the run; an optional incomplete result
can close it as `PARTIAL`. A result arriving at or after the deadline is not
accepted; active nodes receive safe deadline issues instead. Cancellation also
records a safe reason and never stores a raw exception or provider payload.

Terminal states cannot be overwritten, cancelled or supplied another node
result. Owner, request, plan, node kind and dependency identities are checked
at every boundary. The state is replayable because all timestamps, statuses,
issues and result references are explicit and immutable.

## Product difference

Prism exposes why a research answer is incomplete: a required stock node failed,
an optional fund node returned partial data, or the total budget expired. This
is materially different from an Agent chat that silently waits, substitutes a
zero, or reports a polished answer after a dependency failure. The same
state-machine record can later be rendered in the Advisor/Evidence workbench
and joined to the Evidence chain without changing its semantics.

## Deliberate non-goals

This phase does not start asynchronous work, providers, agents, threads or
network calls. It does not implement retries, caching, persistence, API, UI,
real concurrency/SLA, financial analysis, Evidence/Fact/Finding/
Recommendation conversion, compliance, allocation optimization or order
generation. Those concerns require separate plans and evidence.

Run the offline checks with:

```powershell
python -m pytest
python -m compileall -q app
python -c "from app.orchestration import ResearchRunState, start_research_run; print('phase7-import-ok')"
```
