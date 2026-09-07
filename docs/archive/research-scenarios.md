# Research Tracks 场景回放契约

Phase 24 在既有四轨道 Research Tracks 上增加一个明确的离线场景选择边界。场景是
合成 Provider fixture 的确定性 overlay，用来复核 Prism 如何处理来源一致、来源
冲突与数据退化；它不是实时行情、市场准确率或生产 Provider 质量证明。

## 场景目录

`GET /api/v1/advisor/research-matrix-template` 在原有矩阵元数据外返回排序稳定的
`scenarios`：

| ID | 含义 | 预期结果 |
| --- | --- | --- |
| `BASELINE_READY` | 两条独立来源与 claim 一致 | `COMPLETED` + `READY`，4 个 Fact/Finding |
| `SOURCE_DISAGREEMENT` | 宏观来源 B 改为不同的政策利率 | `COMPLETED` + `REVIEW_REQUIRED`，宏观 claim `UNRESOLVED` |
| `SOURCE_PARTIAL` | 基金来源 B 缺少 `technology_weight_pct` | `FAILED` + `REVIEW_REQUIRED`，基金节点 `PARTIAL` |
| `SOURCE_EMPTY` | 行业来源 B 在声明范围内无记录 | `FAILED` + `REVIEW_REQUIRED`，行业节点 `EMPTY` |
| `SOURCE_FAILED` | 个股来源 B 返回安全传输错误 | `FAILED` + `REVIEW_REQUIRED`，个股节点 `FAILED` |

场景选择不改变四轨道矩阵拓扑、claim、预算、owner 或请求 fingerprint。请求体使用
`research-specialist-matrix-request.v1` 的 `scenario_id` 字段；省略时兼容地采用
`BASELINE_READY`，未知枚举由 API 安全拒绝。

## 结果与 Evidence 边界

`POST /api/v1/advisor/research-runs` 的响应继续使用
`research-matrix-response.v1`，并在 `scenario` 中回显已校验的 ID、标签和说明。
所有场景都沿用 `FixtureFinancialProvider`、bounded executor 和
`build_research_evidence_pipeline`：

- 基线只有在两条独立 lineage 支持全部 claim 时才提升为 `READY`，并形成闭合
  `Finding → Fact → Evidence`；
- 分歧保留双方 Evidence，validation 显示支持/反对证据并为 `UNRESOLVED`，不产生
  Fact/Finding；
- PARTIAL、EMPTY、FAILED 分别保留节点四态和 run issue；缺失不会用零值填补，失败
  不会被转换为 EMPTY；
- 非 `READY` 响应可以包含仍可见的 Evidence，但 `trace.facts`、`trace.findings` 和
  `trace.recommendations` 必须为空；研究 run 永远不写 `DecisionEventStore`。

## 工作台回放

Research Tracks 的“回放场景”选择器从模板目录加载。运行后：

- `READY` 展开四条闭合 Evidence 链；
- 分歧显示 validation 状态、独立 lineage 数、support/contradict 计数和双方来源
  值，并标注“待复核”；
- PARTIAL/EMPTY/FAILED 显示对应节点状态、pipeline/run issue 和“未升级为 Fact”的
  可见 Evidence（若有），不显示虚假完整结论；
- owner 或场景切换会清空旧 run，异步旧响应不能写回新 owner/场景。

动态内容只通过 text-only DOM API 渲染，页面继续使用同源 CSP。场景 overlay 不调用
网络、SkillHub、Tushare、LLM/Gemini、认证或交易接口，也不改变 Advisor 的
HOLD/REDUCE 与 Receipt 链。

## 产品选择理由

聊天式产品通常只返回一个综合观点，无法区分来源冲突、数据缺失和真实无结果。Prism
把 scenario、lineage、validation、pipeline 状态和可见 Evidence 放在同一条可复核
路径上：用户能看到系统为什么接受、等待复核或安全阻断，而不是被一个确定语气的
答案掩盖不确定性。
