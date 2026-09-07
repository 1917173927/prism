# Research Tracks 工作台契约

Phase 17 将 Phase 16 的四轨道 `ResearchSpecialistMatrix` 接到现有 owner-scoped
工作台。它是研究可见性切片，不是新的投顾或交易入口。

## API

`GET /api/v1/advisor/research-matrix-template` 要求 `X-Owner-ID`，只返回：

- `matrix_id`、固定 `generated_at`、安全的 `scope_description`；
- `MACRO`、`INDUSTRY`、`STOCK`、`ETF_FUND` 四类 role；
- 节点数量。

它不会返回 Provider fixture 原文、请求参数、私有持仓、凭据或内部异常。

模板同时返回排序稳定的离线回放场景目录。场景 ID、标签和说明用于在工作台选择
基线一致、来源分歧或 PARTIAL/EMPTY/FAILED 数据退化；完整语义和验收边界见
[Research Tracks 场景回放契约](research-scenarios.md)。

`POST /api/v1/advisor/research-runs` 接收严格的
`research-specialist-matrix-request.v1`：`matrix_id`、`request_id`、`owner_id` 和
带时区的 `generated_at`，以及可选的 `scenario_id`（省略时为
`BASELINE_READY`）。body owner 必须等于 `X-Owner-ID`，多余字段、敏感字段、未知
场景/矩阵和服务异常都映射为安全错误。

响应 `research-matrix-response.v1` 从既有 run executor 和 Evidence/Finding
pipeline 映射而来，包含 run/pipeline 状态、八个节点的安全状态与 issue、四个
claim 的交叉验证和 `DecisionTrace`。它保证 owner、run、claim、trace 的闭合，
且永远不含 Recommendation、Receipt、订单或原始 Provider 结果。`READY` 才展示
`Finding -> Fact -> Evidence`；`REVIEW_REQUIRED`/`BLOCKED` 保留降级原因并隐藏
Fact/Finding。

## 工作台行为

“Research Tracks”区域通过 template 取得 replay anchor，先选择场景，再用固定 request
ID 运行矩阵。页面按四类 role 展示节点状态、独立 lineage 数和验证状态；READY 时
展开 Finding、Fact、Evidence，非 READY 时展示 support/contradict 证据和未升级为
Fact 的可见 Evidence。所有动态文字以 DOM
`textContent` 渲染，继续受同源 CSP 保护。

切换 owner 会清空研究模板、run、节点、证据和错误；异步旧请求返回后也不会写回
新 owner 的页面。研究 run 不写入 `DecisionEventStore`，不会改变 Advisor 的
Recommendation/Decision Receipt。

## 复用与边界

实现复用 Phase 13–16 的 FastAPI app factory、统一错误响应、静态工作台、
`ResearchSpecialistMatrixRequest`、bounded executor、lineage-aware Cross
Validation 和 Evidence/Finding bridge。它不接入 SkillHub/Tushare 网络、鉴权、
LLM、真实用户登录、生产持久化、研究历史、Portfolio CRUD 或订单。

这些明确边界使“研究已完成”不会被误读为“建议可执行”：Prism 展示哪一轨道、哪
个来源和哪条 lineage 让结论成立，并在数据退化时拒绝虚假确定性。
