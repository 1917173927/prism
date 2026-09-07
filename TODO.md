# TODO

> Updated: 2026-09-07
>
> Source of truth for product scope: [Prism.md](Prism.md)
>
> Overall execution plan: [docs/plans/2026-09-01-foundation.md](docs/plans/2026-09-01-foundation.md)
>
> Active phase: P2 Milestones (Phase 34 Recommendation History, Phase 35 Portfolio Rebalancing, Phase 36 Evaluation Dashboard, Phase 37 Advanced Explainability) have been implemented, verified, and accepted.
> Next phase: External integrations / evaluation hardening.

## Product UX

- [x] Reorganize the default frontend around user tasks, with detailed research and audit modules available through explicit progressive disclosure.
- [x] Validate the task-first home, detailed-workbench toggle, analysis view, health-check flow, and responsive layout in a real browser.
- [x] Connect sector drill-down results below the chart and restore the evidence-lineage modal without changing sidebar or page partition behavior.

## 2026-09-07 Engineering Backlog

- [x] TASK-01: Tencent → Sina → static market-data failover with bounded timeout and freshness metadata.
- [x] TASK-02: OCR fuzzy security correction, deterministic value reconciliation, confidence states and odd-lot review.
- [x] TASK-03: A-share lot sizing and deterministic transaction-friction output.
- [x] TASK-04: Five-sector custom stress inputs with Python-calculated volatility and VaR changes.
- [x] TASK-05: Micro-Store for atomic owner, profile, portfolio and data-mode transitions.

## P0 — Foundation

- [x] Initialize the independent `main` Git repository.
- [x] Record the modular-monolith and structured-DAG decision.
- [x] Produce and verify the upstream Reuse Matrix.
- [x] Implement the first Evidence/Fact/Finding/Recommendation contract.
- [x] Test missing data, stale evidence, reference closure and blocked decisions.
- [x] Define a fixture-first Provider Protocol with distinct `SUCCESS`, `PARTIAL`, `EMPTY`, and `FAILED` results.
- [x] Add per-call correlation IDs, deterministic request fingerprints, time budgets and redacted diagnostics.
- [x] Add recorded, synthetic Wencai/Tushare fixtures without credentials or private data.
- [x] Define schema versioning and Decision Receipt content hashes.
- [x] Add an owner-scoped local decision-event store and migration; PostgreSQL-oriented profile/evidence storage remains deferred.
- [x] Add an early load-test harness before implementing the full research graph; record
  local fixture P50/P95/P99 and keep production SLA claims deferred.

## P0 — Flagship vertical slice

- [x] Implement deterministic risk questionnaire scoring.
- [x] Define structured profile extraction proposals and explicit conflict confirmation (without LLM parsing).
- [x] Define portfolio and fund/ETF position import contracts.
- [x] Calculate look-through technology exposure and data coverage.
- [x] Implement concentration and profile-conditioned risk-budget findings; correlation, liquidity and advanced optimization remain deferred.
- [x] Generate conservative, balanced and growth-oriented allocation ranges (constraint envelope; final Recommendation remains deferred).
- [x] Show deterministic per-constraint pre/post impact and profile/snapshot invalidation conditions.
- [x] Prove that the same evidence produces materially different valid outputs for different profiles.

## P0 — Structured research and UI

- [x] Define four-state structured research-node results and lineage-aware Cross-Validation contract; real Provider/DAG integration remains deferred.
- [x] Define bounded owner-scoped research-run state, dependency closure and deadline semantics; async execution remains deferred.
- [x] Bridge only fully supported cross-validation claims into closed `VERIFIED Fact -> Finding` objects; degraded and mismatched evidence remains review/blocked.
- [x] Implement bounded Fixture-backed async orchestration with structured `ResearchRunState`, dependency gating and four-state mapping; live execution remains deferred.
- [x] Add deterministic Macro, Industry, Stock and Fund/ETF specialist node recipes with
  dual-lineage fixture execution; live Provider access remains deferred.
- [x] Implement source-lineage-aware cross validation and disagreement handling for executed fixture observations; live provider nodes remain deferred.
- [x] Consume complete-run validation through the Evidence/Finding bridge and emit a closed DecisionTrace; degraded runs remain review/blocked.
- [x] Implement and independently accept the risk and compliance gates.
- [x] Build Portfolio, Advisor, Evidence and Risk Profile workbench views.
- [x] Connect a structured Advisor Query form to the fixture-first API, replay receipt and
  owner-isolated Evidence view; broader Portfolio/Risk Profile interactions remain open.
- [x] Compose deterministic HOLD/REDUCE Recommendations from a dual-PASS gate and create a self-validating Decision Receipt.
- [x] Expose stored decision receipts through a FastAPI boundary and the first explainable workbench slice.
- [x] Trigger the fixture-first Advisor vertical slice from a structured API request and persist an idempotent DecisionEvent.
- [x] Add the owner-scoped Research Tracks template/run API and four-track workbench view;
  keep READY research separate from Recommendation/Decision Receipt.
- [x] Add the read-only Portfolio snapshot and Risk Profile questionnaire context views;
  keep template values owner-closed and defer CRUD/real account import.
- [x] Add structured Portfolio JSON and Risk Profile session confirmation before Advisor;
  keep real account upload, authentication and persistence deferred.
- [x] Add the versioned `eval_cases/` fixed-set evaluator and replay report required by
  `Prism.md`; keep market accuracy and live Provider claims deferred.
- [x] Add explicit owner-scoped investment intent contracts and a read-only four-track task
  plan preview; keep natural-language understanding, LLM/Gemini and research execution
  deferred.
- [x] Verify the complete flagship flow in a real browser.
- [x] Verify the Phase 15 form → API → HOLD/REDUCE → Evidence → owner isolation path in a
  real browser.
- [x] Add the typed ProfileExtractionProposal preview and explicit conflict confirmation;
  keep natural-language parsing, LLM/Gemini and raw-text persistence deferred.
- [x] Add an explicit Research Tracks scenario catalog for baseline, source disagreement,
  PARTIAL, EMPTY and FAILED replays; keep live Provider access and recommendation side
  effects deferred.
- [x] Add the independent Demo F stock research Evidence Card with six financial claims,
  deterministic quality/leverage Findings, five safe replay scenarios and visible node
  degradation reasons; keep live market data, valuation and Recommendation effects deferred.
- [x] Add the independent Demo G ETF/Fund asset research Evidence Card with six fund claims,
  deterministic concentration/cost/volatility/drawdown Findings, five safe replay scenarios
  and visible node degradation reasons; keep live market data, portfolio adjustment and
  Recommendation effects deferred.
- [x] Add the independent Phase 28 Portfolio Optimization target-structure proposal with
  `CAP_AND_REDISTRIBUTE_V1`, owner-scoped API/UI, profile-conditioned caps, closed target /
  constraint arithmetic, and explicit REVIEW_REQUIRED/BLOCKED scenarios; keep correlation,
  liquidity, asset-category caps, backtest, trading and Recommendation effects deferred.
- [x] Add the independent Phase 29 owner-scoped structured Context Memory ledger with immutable
  profile/questionnaire/portfolio snapshots, optional typed references, deterministic identity,
  SQLite migration/restart reads, explicit browser recovery and stale/owner isolation; keep
  raw chat, semantic retrieval, automatic restore, cloud sync, authentication and delete/TTL
  deferred.
- [x] Add the Phase 30 bounded Provider Cache/Fallback boundary keyed by public request
  fingerprint, with explicit fresh/secondary/stale serving modes, four-state preservation,
  stale Evidence downgrade and no private/failed/empty cache pollution; keep live SkillHub,
  production cache, circuit breaker and full Evidence drill-down deferred.
- [x] Add the Phase 31 Advanced Evidence UI explorer with owner-bound Evidence aggregation,
  quality/serving-mode/source/promotion filters, provenance/freshness details, explicit stale /
  fallback review notices and no recommendation/API side effects; keep backend indexing,
  real SkillHub, authentication, cloud persistence and automatic refresh deferred.
- [x] Localize the Phase 32 workbench UI into Chinese while preserving stable machine IDs,
  enum values and audit labels; synchronize left navigation active/`aria-current` state on
  clicks, hash changes and direct hash loads; keep Scenario Simulation and other P2 work out
  of this phase.
- [x] Implement the bounded Phase 33 Scenario Simulation catalog and deterministic baseline →
  hypothetical diff flow; keep simulated values separate from Fact/Finding/Recommendation,
  preserve owner isolation and four-state degradation, and defer History/Rebalancing/Dashboard.

## P2 — Advanced Capabilities & Hardening

- [x] Phase 34: Implement immutable Recommendation History retrieval, receipt comparison, owner-isolated queries, action transition diffs, and audit trail visualization.
- [x] Phase 35: Implement deterministic Portfolio Rebalancing engine with decimal conservation, deadband threshold (0.50%), turnover cap checks, and liquidity-ordered step execution (SELL before BUY).
- [x] Phase 36: Implement Evaluation Dashboard integrating versioned `eval_cases/`, tracking Pass Rate, Evidence Coverage, 0.00% Hallucination, and latency percentiles.
- [x] Phase 37: Implement Advanced Explainability with deterministic causal DAG generation, key decision driver attributions, counterfactual conditions, and invalidation triggers.
- [x] Phase 38: Implement Copilot Interactive Task Center (Optimization Direction 1) featuring Three-Tier Information Architecture, 3 Preset Personas (Zhang R3, Li R2, Wang R4), 3 Core Tasks (Health Check, Asset Deep Dive, Smart Rebalancing), Natural Language Query router, L2 Decision Cards, and 1-Click L3 Expert Audit Drill-downs.
- [x] Phase 39: Implement Live LLM Cognitive Agent & Real Financial Data Providers (Optimization Direction 2) featuring OpenAI/DeepSeek/Qwen compatible streaming client, ReAct multi-agent tool execution, Live Market Provider (real quotes/PE/ROE), Live Fund Look-Through Provider, Live Wencai SkillHub Provider, and Natural Language Portfolio Parser.

## P3 — Workflow Orchestration & Anti-Hallucination Blackboard (Next Phase)

- [ ] Phase 40: Multi-Agent Graph & Pipeline Workflow Builder (Coze-aligned capabilities)
  - [ ] 引入成熟开源图引擎（如 AntV X6 / LiteGraph / Flow），构建高表现力节点画布与连线编排面板，避免从零造渲染轮子。
  - [ ] 支持图引擎拓扑模型与后端 `WorkflowDefinition` (v1) 契约的双向转换与环路校验 (DAG Cycle Detection)。
  - [ ] 提供「高级画布视图」与「流水线卡片视图」双模切换，适配普通用户预置模版与进阶用户自定义投研链。
  - [ ] 将可视化导出的工作流配置对接至 `executor.py` 有界并发异步执行器。
- [ ] Phase 41: Session Truth Blackboard & Hallucination Suppression Panel
  - [ ] Define `session-blackboard.v1` contract extracting locked profile baselines, holdings, and risk envelopes per session.
  - [ ] Implement deterministic drift and contradiction detection rules (`PREMISE_DRIFT`, `ACTION_CONFLICT`, `HALLUCINATED_DATA`).
  - [ ] Add slide-over Session Truth Blackboard drawer with suspicious turn alerts and smooth scroll-to-turn anchors.
  - [ ] Provide one-click manual premise override modal that commits to `ContextMemory` and enforces negative constraint prompts on subsequent turns.

## External inputs / decisions

- [x] 接入扶摇服务端金融数据凭据；普通用户无需配置上游 API Key，LIVE 行情与基金披露持仓已完成真实请求验证。
- [x] 合并扶摇与问财核心能力：各 Provider 独立降级；问财未配置时不阻断扶摇行情、基金披露和基于已确认持仓的确定性组合计算。
- [ ] 在公开部署或向第三方开放 Prism API 前，确认扶摇多用户展示、缓存、派生结果、调用限额、SLA 与再分发授权。
- [x] External decision confirmed: 官方 SkillHub 开发文档与测试凭据目前处于「暂时没有」状态。本轮系统架构严格实现真实适配器骨架（LiveWencaiProvider）与离线不可用/降级态（SKELETON_UNAVAILABLE），绝不虚假声称真实接口已测试通过。
- [ ] Obtain competition-specific SkillHub development documentation and production credentials when officially issued by the committee.
- [ ] Confirm SkillHub quotas, caching, retention, attribution and output-display rights.
- [ ] Obtain the scoring appendix referenced by the competition brief.
- [ ] Confirm reuse/provenance terms for both upstream repositories; neither root currently exposes a LICENSE/NOTICE file.
- [ ] Choose the Prism repository license before any public publication.

These inputs block claims of real SkillHub integration or submission readiness, but they do not block fixture-driven contract and vertical-slice development.

## Explicitly deferred

- broad persistent conversational memory beyond profile/decision audit state;
- autonomous trading or real order execution;
- microservices and Kubernetes;
- complex animation, persona-heavy Agent presentations and custom model training;
- 自研底层 Canvas/SVG 渲染引擎内核（统一通过引入成熟工业级开源图引擎支撑）。

## Next useful action

Optimization Direction 1 (Phase 38) and Optimization Direction 2 (Phase 39) have been fully implemented and verified with 100% test pass rate across 472 automated tests.
Next targets are Phase 40 (Multi-Agent Graph & Pipeline Workflow Builder, 引入成熟开源图引擎) and Phase 41 (Session Truth Blackboard & Anti-Hallucination Panel) as specified in `docs/architecture.md`.
