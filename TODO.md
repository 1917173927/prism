# TODO

## 评审技术方案

- [x] 补充公式应用与演算、前后端框架图、三类上下文、多轮追问及工具路由；扩展四项创新的具体机制，更新评审版 Word 与 PDF。

- [x] 重点完善第五章和第六章的技术命名、数学模型、算法性质及十八组原生公式，更新评审版 Word。

- [x] 依据参考文档创新正文的写法与篇幅重写第六章，生成评审版 Word。

- [x] 将四项创新具体化为输入、处理步骤、判定条件、演算及工程证据，验证程序输出并更新 Word。

- [x] 按新增模板重组技术文档，引入近期论文与编号引用，生成可编辑 Word，并删除负责人、成员作用及成本章节。
- [x] 将完整技术文档导出为 34 页 PDF，检查分页与图表，并与本次文档及配图合并提交。
- [x] 应用 nature-figure 与 Python 重绘六幅技术图，采用前端灰白橙配色，输出 PNG、SVG、PDF，检查文字边界及文档引用。
- [x] 参考四份项目方案与指定共享对话调整最新技术方案，统一章节及图表格式，将工程索引集中于附录，补充真实组合报告案例并完成数值与文档结构校验。
- [x] 根据评审意见强化第三章截图说明，将第五章集中为四项核心技术，第八章通过比较与验证入口突出创新设计。
- [x] 根据已有实现提炼三项领域算法，补充输入、处理步骤与输出，核对评分、证据判定和再平衡规则并完成文档验证。
- [x] 标题及 README 入口改为技术文档，参考已有样图丰富六幅技术图，新增资产构成与创新关系图并完成八幅图的渲染检查。
- [x] 参考工程文档样图调整六幅流程图的阶段布局和连线，正文使用固定高清图片，完成节点穿线检查。
- [x] 应用视觉设计技能统一六幅技术图的标题层级、阶段底板、节点卡片及类别色条，完成渲染与文档验证。

> Updated: 2026-09-15

当前执行清单：[剩余缺口实施与验收](docs/plans/2026-09-08-gap-closure.md)。用户已授权推进其余缺口，明确排除正式 PPT、视频和提交版测试报告；外部授权与生产 SLA 需独立验证。
>
> Source of truth for product scope: [Prism.md](Prism.md)
>
> Overall execution plan: [docs/plans/2026-09-01-foundation.md](docs/plans/2026-09-01-foundation.md)
>
> Historical baseline: P2 Phase 34–39 implemented. Current work: local deployment and incremental P3 gap closure; status below is item-specific.
> External integrations and real model / SLA validation remain evidence-dependent.

## GitHub Pages 前端展示

- [x] 使用最新 `app/api/static/index.html` 与完整静态资源目录发布前端工作台，并通过 `.github/workflows/deploy-pages.yml` 自动更新。
- [x] 从本机当前服务捕获实际账户响应，生成 `app/api/static/pages-snapshot.json`，公开页面只读取静态快照。
- [x] 公开页面保留完整工作台导航与功能面板，未捕获的写入请求显示为只读快照不可用状态。
- [x] 在 GitHub Pages 证书就绪后打开 `Enforce HTTPS`，并复核 `https://prism.daoyezongzi.org` 的证书状态。

## 本地部署缺口执行

- [x] 整屏持仓 OCR 按表头定位列、按文字高度匹配双行，识别账户现金与总资产；三张用户原图上传接口及 17 项回归通过。

- [x] 模型配置移除回复模式与独立测试按钮，保存后自动测试；自然语言股票名称精确检索并复用下方研判卡片，发送旁常驻进度。
- [x] 扶摇补接 PE/PB 与已披露报告期 ROE、毛利率、资产负债率；宁德时代真实模型对话与卡片验证通过。
- [x] 正式报告按内容生成编号，修复同快照补充行业后的 409 冲突；问卷切页回到题目顶部，Q12/Q17 改为程度文字，评分保持不变。

- [x] AI 对话概念措辞误拦截、问财六类结构化数据工具连接、部分能力失败阻断全部聊天、锁定 LIVE 持仓体检与 `verified_skills` 配置兼容；真实模型及 HTTP/SSE 验证通过。
- [x] 核实问财 HTTP 401 原始正文：当日查询次数已用完，并非凭据失效。新增 QUOTA_EXHAUSTED 及准确处理提示；其余可用能力继续独立运行。
- [ ] 问财受限查询需等待额度重置，或由用户按需在 SkillHub 升级权益；额度恢复后复验财务数据。当前无需重新填写 Key。

- [x] 修复真实模型分片工具调用未执行、动态快捷标的丢失、用户模型配置未覆盖画像/记忆、AUTO 隐式模拟、LIVE 工具穿透 MOCK、未授权参数与未核验金融正文透传；真实浏览器和扶摇接口已验证个股行情与基金披露均为非合成数据。
- [x] Windows 本地模型密钥使用 DPAPI 持久化，工作树默认共享主仓库私有目录并保留账户作用域；状态刷新不覆盖输入，留空保存保留已有配置，显式 DELETE 才删除。实际页面保存、重启恢复与真实对话已验证。
- [x] 移植真实组合批量报价与行业解码修复；股票行业由东方财富公司资料自动查询并缓存，撤回人工行业确认入口；数据源确实缺失时返回部分体检。完整性不足的组合仍禁止优化与调仓。
- [x] 当前账户五只股票已自动识别行业；真实页面生成调仓测算通过，集中度风险仍按确定性检查保留。真实财务对话准确显示 QUOTA_EXHAUSTED。
- [x] LIVE 模式继续拒绝 Fixture 投顾、专家矩阵、股票/基金/转债完整研究、预设情景和固定工作流；组合优化已拆出不读取回放模板的真实持仓确定性服务，调仓链路已开放。
- [x] 组合刷新接入真实扶摇报价并保留问财适配：问财单项行情 Skill 失败不再阻断扶摇报价、组合体检、目标权重和调仓；问财动态中文股票列也已映射为标准字段。
- [x] 问财 SkillHub 已项目化接入九个官方 Skill；凭据以 DPAPI 保存一次、跨重启恢复。历史九项探测和公告工具链通过，但当前 `hithink-market-query` 返回 401，运行态按真实失败降级，不回退模拟数据。
- [ ] 【未实现】将 Fixture 投顾、研究矩阵、股票/基金/转债完整研究、预设情景和固定工作流替换为真实服务。现有双源证据契约不能用单一问财来源冒充闭合。
- [ ] 【部分实现】个股卡片已补接扶摇 PE/PB/ROE/毛利率/资产负债率，历史估值分位及完整个股适当性仍未实现；基金底层行业分类仍需完善。缺失项按实际服务响应保留。
- [x] Windows 启动入口收敛为单一 `start.bat`；自动选择 Python 3.12/3.11、创建 `.venv`、安装完整 Web 运行依赖并执行导入检查，已通过全新环境安装和 HTTP 健康检查。
- [x] 可选 HTTP Basic 绑定服务端 owner、管理员权限、跨来源写入拒绝和访问审计；已确认持仓继续服务端持久化，认证模式不缓存聊天或模型密钥。
- [x] SQLite 在线备份和新路径恢复；防覆盖并执行完整性校验。运行说明见 docs/local-deployment.md。
- [x] 真实 HTTP 观测工具，本地 100 并发持仓读取 P95 326ms、100/100 成功；外部和长期 SLA 未验收。
- [x] 自然语言偏好提取及原文证据、否定/冲突处理、显式提案确认；本机有限规则模式已浏览器验证，真实模型通用语言质量待验收。
- [x] 会话事实黑板锁定服务端画像、持仓和数据模式，旧版本/快照冲突拒绝，流式生成期间漂移立即停止；SSE 错误与截断不再显示完成。
- [x] 修复 session truth 未锁定时聊天发送前退出：普通概念问答降级为无画像、无持仓、无历史的一般会话，后端拒绝客户端伪造上下文；实时金融问题继续要求真实工具。
- [x] 历史记忆按 owner 检索最近 100 条显式保存记录，返回来源与摘要，模型不可用时明确降级；不自动应用历史持仓。
- [x] AntV X6 固定研究节点依赖编辑、版本保存及有界执行；已验证 MOCK 页面路径、环路拒绝、版本冲突及超时取消。
- [x] 可选 PostgreSQL 后端、原子迁移与失败回滚；真实 17.11 九项数据库回归通过，未切换用户 SQLite 主库。
- [ ] 正式上游配额/留存/展示授权、真实模型质量及外部长期 SLA 仍需独立验收；券商同步不在当前范围内。

## Product UX

- [x] 五项追加 UI 反馈：对话右栏字号/按钮、持仓右侧资产环图与风险预算、大盘四指数显式选择；后续按产品边界删除个人中心授权开关，将主题及 AI/工具数据入口收纳至右上角“更多”。
- [x] 恢复聊天四阶段真实事件进度，修复阶段卡片、核对提示和工具记录未挂载；问财回答使用真实标题/摘要并过滤无关工具模板；增加仅清除 owner 对话历史、不删除账户事实和凭据的“清空上下文”。

- [x] PRD 本轮页面修复：六项输入前缀、安全 Markdown、发送侧进度、导入/添加/删除持仓、分析视图并入持仓页、首次引导与隔离预览、个人 API Key 设置和开发者 AI 模拟切换。详见 docs/plans/2026-09-14-prd-ui-repair.md。
- [x] 指数专用身份及 A 股日 K 线接入；扶摇/iFinD 为配置后的主链路，腾讯公开指数日线用于无凭据降级；固定 12 项行业观察展示 1/5/20 个交易日涨跌幅。
- [ ] 独立 iFinD 登录账户及港美股权限核实；全市场板块轮动覆盖、真实模型质量与新券商截图识别准确率验收。

- [x] 顶部账户风险标签读取已确认有效画像，未确认时明确提示，修复默认 R3 与实际成长型画像不一致。

- [x] 问卷画像结果展示第一批：确定性八维雷达图、画像标签、关键档案、服务策略、资产配置参考和风险提示；交易记录不再作为结果展示前置条件，推荐智能体暂缓。
- [x] 持仓结果第二批：对齐四项 KPI、确定性正式快照报告、集中度/浮亏/底仓保护/配置参考、诊断抽屉与 HTML 导出链路；当前仍未提供历史报告列表，不接入个股研究智能体。

- [x] 修复调仓不足整手取整为零却返回 PASS、前端固定绿色和原因缺失；传递并检查体检现金下限。当前用户页面复测成功，全量 584 项通过。
- [x] 目标计算纳入现金下限，并传递已确认画像；交易数量与费用测算后重建假设持仓，复核完整体检和风险预算。风险未解除继续 REVIEW_REQUIRED，不宣称全局最优。

- [x] 修复刷新与服务重启丢失持仓和问卷；按账户及数据模式保存，防止过期恢复覆盖；修复跨页面持仓弹窗、重复截图快照冲突及识别文案。全量 582 项测试通过，真实浏览器完成刷新和重启恢复验证。

- [x] 为自然语言导入的瞬时取价失败增加一次有界重试，并显示失败证券及处理方式；相关 38 项测试通过。

- [x] 修复自然语言持仓千位逗号截断数量、成本和现金的问题；用户原文浏览器复测成功，相关 37 项测试通过。

- [x] 修复真实数据用户流程：首次使用前置检查、持仓现价、基金数据边界、缺失字段、聊天标的、HHI 渲染、调仓与压力测试失败恢复；全量 572 项测试通过。

- [x] Reorganize the default frontend around user tasks, with detailed research and audit modules available through explicit progressive disclosure.
- [x] Validate the task-first home, detailed-workbench toggle, analysis view, health-check flow, and responsive layout in a real browser.
- [x] Connect sector drill-down results below the chart and restore the evidence-lineage modal without changing sidebar or page partition behavior.
- [x] Make Agent conversation the standalone default home and move portfolio, research, decision history, and profile management to separate pages.
- [x] Require the formal 19-question investor suitability assessment on first entry and remove questionnaire completion indicators from the returning-user home.
- [x] Keep behavior-profile context visually secondary and allow bounded profile refinement inside the conversation without raising the formal risk level.

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

## P3 — Workflow Orchestration & Anti-Hallucination Blackboard（部分实现）

- [ ] Phase 40: Multi-Agent Graph & Pipeline Workflow Builder (Coze-aligned capabilities)
  - [x] 引入 AntV X6 3.1.8，提供节点拖动与依赖选择编辑；当前固定八节点 MOCK 目录。
  - [x] 支持画布与 `workflow-definition.v1` 双向转换、版本 CAS 和服务端环路校验。
  - [x] 提供高级画布与流水线卡片双视图，同一依赖模型；当前固定节点目录，按拓扑阶段显示依赖与执行状态。
  - [x] 将已保存依赖接入既有研究矩阵及 `executor.py`，总超时取消执行，返回节点状态。
- [ ] Phase 41: Session Truth Blackboard & Hallucination Suppression Panel
  - [x] 以 session-truth 接口锁定服务端已确认画像、持仓、模式与风险前提，追加修订并校验摘要。
  - [x] 实现 PREMISE_DRIFT、白名单结构化数值 HALLUCINATED_DATA 与明确买入禁投 ACTION_CONFLICT；未知约束保留 UNVERIFIED，不宣称通用语义判定。
  - [x] 增加事实黑板侧栏和本页分析中断记录，点击可滚动定位对话；中断不等于已证明存在幻觉。
  - [x] 增加显式前提确认预览，指纹变化拒绝提交；修订写入专用 session_truth 审计，后续会话受已锁定事实约束，不重复复制 ContextMemory。
  - [ ] 自动从通用自然语言提取可疑事实与动作仍需真实模型质量评测。

## External inputs / decisions

- [x] 接入扶摇服务端金融数据凭据；普通用户无需配置上游 API Key，LIVE 行情与基金披露持仓已完成真实请求验证。
- [x] 合并扶摇与问财核心能力：各 Provider 独立降级；问财未配置时不阻断独立的扶摇行情与基金披露，但组合刷新、优化和调仓必须同时取得真实报价与真实行业元数据，缺一即停止且不沿用旧持仓字段。
- [ ] 在公开部署或向第三方开放 Prism API 前，确认扶摇多用户展示、缓存、派生结果、调用限额、SLA 与再分发授权。
- [x] 已注入用户提供的问财 OpenAPI 服务端凭据并完成真实查询 smoke test；适配器使用 `IWENCAI_BASE_URL`/`IWENCAI_API_KEY`，保留 `WENCAI_SKILLHUB_*` 兼容别名和严格失败降级。
- [ ] Obtain competition-specific SkillHub development documentation and production credentials when officially issued by the committee.
- [ ] Confirm SkillHub quotas, caching, retention, attribution and output-display rights.
- [ ] Obtain the scoring appendix referenced by the competition brief.
- [ ] Confirm reuse/provenance terms for both upstream repositories; neither root currently exposes a LICENSE/NOTICE file.
- [ ] Choose the Prism repository license before any public publication.
- [ ] 取得并验证港股、美股四个指数及三项宏观因子的正式iFinD代码、展示权限、配额与再分发许可后，完成真实LIVE联调；验证前维持 `UNAVAILABLE`。

The remaining legal, quota and competition-document inputs block production redistribution and submission-readiness claims; they do not negate the verified local real-provider paths or block fixture-driven contract development for explicitly deferred features.

## Explicitly deferred

- broad persistent conversational memory beyond profile/decision audit state;
- autonomous trading or real order execution;
- microservices and Kubernetes;
- complex animation, persona-heavy Agent presentations and custom model training;
- 自研底层 Canvas/SVG 渲染引擎内核（统一通过引入成熟工业级开源图引擎支撑）。

## Next useful action

当前按 [剩余缺口执行清单](docs/plans/2026-09-08-gap-closure.md) 推进和验收。历史 472 项测试不再代表当前基线；2026-09-08 全量 638 项通过，含临时 PostgreSQL 17.11 的 9 项真实数据库测试。P3 已完成固定 DAG 编辑和结构化会话前提锁定，其余双视图与通用幻觉检查仍未勾选。

## 2026-09-15 对话与报告复验

- [x] 使用语义分流处理一般对话与金融数据请求，并验证未核验金融内容仍被阻止。
- [x] 排除 8000 旧子进程干扰，完成真实页面四轮对话、个人中心切换、正式报告重复生成验收。
- [x] 最终版本全量回归 827 passed / 9 skipped；当前证据替代此前版本不一致的测试声明。
