# Decision Events API

Phase 13 exposes the Phase 12 result through a narrow, owner-scoped boundary.
It is a local MVP surface, not an authentication or production persistence claim.

## Run locally

The app factory defaults to an in-memory store. To retain events across process
restarts, inject a path-backed `SQLiteDecisionEventStore` whose parent directory
already exists. The migration under `app/store/migrations/001_decision_events.sql`
is applied idempotently at startup.

```powershell
python -m uvicorn app.api.main:app --reload
```

Install the optional web extra when `uvicorn` is not already available:

```powershell
python -m pip install -e ".[dev,web]"
```

## Endpoints

All decision-event endpoints require the `X-Owner-ID` header. The header is an
MVP isolation key only; it is not proof of identity.

| Method | Path | Meaning |
|---|---|---|
| `GET` | `/api/health` | Service and event-schema health only |
| `POST` | `/api/v1/decision-events` | Validate and idempotently store one `RecommendationCompositionResult` |
| `GET` | `/api/v1/decision-events` | List only the current owner's safe event summaries |
| `GET` | `/api/v1/decision-events/{event_id}` | Read one fully revalidated owner-scoped event |
| `GET` | `/` | Static explainable workbench |

The POST body is the Phase 12 `RecommendationCompositionResult`; the API does
not accept raw Provider records, credentials, or a free-form recommendation. A
`PASS` body must contain a valid Decision Receipt and closed trace. A
`REVIEW_REQUIRED` or `BLOCKED` body is retained as a safe refusal event with no
Receipt or Recommendation. The API never upgrades either status.

The response uses a stable `decision-event:{hash}` identity. Repeating the same
content returns `created=false`; reusing that identity with different content
returns a generic `409 CONFLICT` and never overwrites the existing row. Reads
query by both owner and event ID, so an event belonging to another owner is
reported as `404 NOT_FOUND` rather than revealing that it exists.

## Persistence integrity

SQLite stores a canonical JSON payload plus event content hash. The store
rebuilds `DecisionEvent`, `RecommendationCompositionResult`, `DecisionReceipt`
and `DecisionTrace` on every write and read, and compares all row identity,
status, timestamp and hash columns with that payload. The event content hash
covers the decision result and identity but deliberately excludes the storage
`recorded_at` metadata, allowing retries to remain idempotent. Receipt and trace
hashes remain covered by their Phase 12 contracts.

The adapter uses one transaction and a process lock for local concurrent writes.
It is a replaceable store port, not a PostgreSQL schema or a multi-process
availability guarantee. No private portfolio input or raw Provider payload is
sent to the store by this API; the persisted trace contains only the already
normalized Evidence/Facts/Findings and structured result.

## Workbench

The zero-build page follows the checked `tradeeye-copilot` visual grammar (warm
white, deep ink, clay accent, serif headings and monospaced numbers) while using
Prism's own information architecture. It reads the list/detail endpoints and
renders Overview, Advisor, Evidence and Risk Profile regions. Dynamic values are
inserted with `textContent`, and a restrictive same-origin CSP prevents inline
script execution. Empty, review and blocked results remain explicit states.

The offline acceptance fixture at
`tests/fixtures/decision-events/decision_event_cases.json` names the four
workbench states (balanced HOLD, conservative REDUCE, review and blocked) without
embedding private holdings or provider payloads.

## Deliberate next boundary

Phase 13 does not implement authentication, Profile/Portfolio CRUD, provider
execution, API-triggered orchestration, PostgreSQL/Redis, encrypted storage or a
production SLA. A later phase must keep this endpoint owner-scoped and revalidate
the same contracts before adding those capabilities.
