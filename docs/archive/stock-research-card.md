# Demo F：个股研究 Evidence Card

Phase 25 将 Prism 的个股研究职责落成一个 fixture-first、可审计的本地纵切。
它用于证明“数字从哪里来、什么时候不能下结论”，不是实时行情服务，也不是交易
建议引擎。

## 用户看到什么

工作台从 `GET /api/v1/advisor/stock-research-template` 读取固定的合成标的、期间、
指标标签、风险阈值和五个安全场景，再由
`POST /api/v1/advisor/stock-research-runs` 运行一个 owner-scoped 回放。结果卡按
以下顺序展开：

```text
source node -> Provider 四态 -> lineage-aware Cross-Validation
            -> VERIFIED Fact -> deterministic Finding -> risk summary
```

基线场景展示六个原始财务事实：营业收入、净利润、经营现金流、应收账款、毛利率和
资产负债率。现金流质量、应收账款占收入、杠杆三条规则使用服务端 `Decimal` 计算，
每个 Finding 都引用本次运行产生的 Fact；前端只负责展示，不重算金融指标。

## 五个可回放场景

| 场景 | 预期状态 | 语义 |
| --- | --- | --- |
| `BASELINE_READY` | `COMPLETED/READY` | 两条独立来源一致，六个 Fact 可验证，基线风险为 `HIGH_RISK`。 |
| `SOURCE_DISAGREEMENT` | `COMPLETED/REVIEW_REQUIRED` | 来源 B 的债务率与来源 A 不一致；双方 Evidence 可见，但不生成 Fact/Finding。 |
| `SOURCE_PARTIAL` | `COMPLETED/REVIEW_REQUIRED` | 来源 B 缺少债务率；节点显示 `PARTIAL` 与 `MISSING_FIELDS`。 |
| `SOURCE_EMPTY` | `COMPLETED/REVIEW_REQUIRED` | 来源 B 在声明范围内没有记录；节点显示 `EMPTY` 和范围说明，不填零值。 |
| `SOURCE_FAILED` | `COMPLETED/REVIEW_REQUIRED` | 来源 B 安全失败；节点显示 `FAILED/SOURCE_UNAVAILABLE`，不转换为 `EMPTY`。 |

所有非 `READY` 结果保留可审计 Evidence 和节点降级原因，但 `facts`、`findings` 为空，
风险为 `NOT_ASSESSED`。响应还包含完整 `DecisionTrace`，且永远不含
Recommendation 或 DecisionEvent 写入。

## 契约与隔离

- 请求只接受 owner、request ID、固定 subject/period、timezone-aware `generated_at`
  和枚举场景；extra、未知场景、敏感字段、跨 scope 和 naive 时间会在 API 边界拒绝。
- 模板只公开稳定标签和阈值，不公开 Provider 名称、请求参数、fixture 原文或凭据。
- `StockResearchNodeResponse` 暴露每个节点的状态、缺失字段、范围说明和安全 issue，
  使“Evidence 可见但未升级”可解释。
- 结果、验证、Fact、Finding、Evidence 均绑定 owner/subject/period；owner 切换会清空
  浏览器旧卡，异步序列不会把旧响应写回。
- 动态 DOM 使用节点 API/`textContent`，请求只走同源路径；这条 Demo 不接入外网、
  LLM/Gemini、在线鉴权或生产存储。

## 复用边界与产品差异

服务只编排新的 stock manifest、fixture overlay、风险派生和卡片投影，复用既有
`FixtureFinancialProvider`、bounded research run、四态 Provider 契约、
Cross-Validation、Evidence/Finding bridge 与 `DecisionTrace`。上游
`tradeeye-copilot` 仅作为字段语义、质量规则思路和 Evidence 引用白名单的只读参考，
没有运行时导入。

普通个股聊天产品可以直接给出“看多/看空”或一个分数，但用户无法核对数字的来源，
也无法知道缺一个字段时结论是否还成立。Prism 先展示来源和 lineage，再在证据闭合
后生成确定性风险；冲突或退化时明确阻断升级。这种可复核的失效边界是本阶段的产品
差异化，而不是把离线合成数据包装成实时能力。

## 明确不做

真实同花顺问财/SkillHub 或 Tushare 网络 Provider、在线鉴权、重试/缓存/断路器、
真实公司覆盖、估值和价格预测、新闻情绪、趋势因子、ETF/可转债分析、自然语言理解、
LLM/Gemini、多 Agent、交易/配置/Recommendation、Portfolio/Risk Profile CRUD、
研究历史和生产 SLA 均留在后续阶段或外部输入。

