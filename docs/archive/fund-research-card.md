# Demo G：ETF / Fund 资产研究 Evidence Card

Phase 26 将旗舰场景中的“科技基金集中持仓体检”拆出一张独立的、fixture-first
资产卡。它不是实时行情、基金推荐或组合调仓器，而是验证基金数字何时可以被信任、
何时必须停在待复核。

## 用户看到什么

工作台先读取固定的合成基金、报告期、指标标签、风险阈值和五个离线场景，再运行
owner-scoped 回放：

```text
两条独立来源
    -> Provider 四态与 bounded research run
    -> lineage-aware Cross-Validation
    -> VERIFIED Fact
    -> deterministic asset-risk Finding
    -> 风险摘要
```

基线 `BASELINE_READY` 有六个资产指标：

- `technology_weight_pct`：科技行业权重；
- `top10_weight_pct`：前十大持仓权重；
- `expense_ratio_pct`：费率；
- `annualized_volatility_pct`：年化波动率；
- `max_drawdown_pct`：最大回撤；
- `tracking_error_pct`：跟踪误差。

两条 `FUND_DATA` lineage 必须在同一 subject、period、unit 和 expected value 下闭合。
每个 Fact 的 Evidence 都可展开查看 source、record identity、lineage、value、unit
和 period。前端只展示这些对象，不重算风险数字。

## 五个可回放场景

| 场景 | 预期状态 | 语义 |
| --- | --- | --- |
| `BASELINE_READY` | `COMPLETED/READY` | 双源一致，六个 VERIFIED Fact 和资产风险 Finding 可用。 |
| `SOURCE_DISAGREEMENT` | `COMPLETED/REVIEW_REQUIRED` | 来源 B 的科技权重改为不同值；双方 Evidence 保留，但不升级任何 Fact/Finding。 |
| `SOURCE_PARTIAL` | `FAILED/REVIEW_REQUIRED` | 来源 B 缺少最大回撤，节点显示 `PARTIAL/MISSING_FIELDS`。 |
| `SOURCE_EMPTY` | `FAILED/REVIEW_REQUIRED` | 来源 B 在声明范围内没有记录；显示范围说明，不补零值。 |
| `SOURCE_FAILED` | `FAILED/REVIEW_REQUIRED` | 来源 B 安全失败，显示 `FAILED/SOURCE_UNAVAILABLE`，不伪装成 EMPTY。 |

所有非 `READY` 结果仍返回可审计 Evidence、Cross-Validation、节点 reason 和安全
issue，但 `facts`、`findings` 为空，风险为 `NOT_ASSESSED`。

## 确定性资产风险

服务端以 `Decimal` 和版本化 `fund-risk.v1` 方法计算，不由 LLM 或浏览器生成：

| 指标 | 条件 | Finding | 严重度 |
| --- | --- | --- | --- |
| 科技行业权重 | `> 50%` | `FUND_TECHNOLOGY_CONCENTRATION` | WARNING |
| 前十大权重 | `> 60%` | `FUND_TOP10_CONCENTRATION` | WARNING |
| 年化波动率 | `> 25%` | `FUND_VOLATILITY_RISK` | WARNING |
| 最大回撤 | `> 30%` | `FUND_DRAWDOWN_RISK` | CRITICAL |
| 费率 | `> 1.00%` | `FUND_COST_WARNING` | WARNING |

跟踪误差仅作为已验证资产事实展示，不在本阶段发明质量评分。每条派生 Finding
都引用当前运行的 Fact，`DecisionTrace` 会拒绝未知 Fact/Evidence 或不一致的值。
风险摘要只表达 `NOT_ASSESSED`、`CLEAR`、`WATCH`、`HIGH_RISK`，不表达买卖、仓位或
收益承诺。

## API 与隔离

- `GET /api/v1/advisor/fund-research-template` 返回安全模板和场景目录，不返回 raw
  fixture、请求参数、Provider 名称或凭据；
- `POST /api/v1/advisor/fund-research-runs` 只接受 owner、request ID、固定 subject/period、
  timezone-aware `generated_at` 和枚举场景；extra、敏感、naive 或跨 owner/scope 输入
 统一安全拒绝；
- 服务输出在 API 注入边界再次按 `FundResearchResponse` 校验，并闭合 owner、request、
  subject、period 和 scenario；漂移只映射为 `FUND_RESEARCH_ERROR`；
- 结果不写 `DecisionEventStore`，不生成 Recommendation，不进入 HOLD/REDUCE；
- 静态工作台使用同源 `fetch` 与 `textContent`/节点 API。owner 或场景变化会清空旧卡，
  异步 sequence 不允许旧响应写回。

## 复用边界与产品差异

Demo G 复用 Prism 的 `FixtureFinancialProvider`、Provider 四态校验、bounded research
run、normalization、Cross-Validation、Evidence/Finding bridge 和 `DecisionTrace`；新
代码只编排 fund manifest、双 lineage fixture overlay、资产风险规则和卡片投影。
`tradeeye-copilot` 仅作为 ETF 字段、费用/波动/集中度检查思路的只读参考，不进入运行时。

许多基金产品把“科技仓位高”“回撤大”压成一个无法核验的分数，即使来源冲突也继续给
结论。Prism 先显示两条 lineage 的原始数字和期间，再用固定规则生成 Finding；一旦
来源冲突或数据退化，Evidence 仍可审阅，但 Fact/Finding/风险评估被阻断。用户因而能
回答“哪条数据、哪个期间、何时失效”，而不是只能相信一段泛化推荐。

## 明确不做

真实同花顺问财/SkillHub/Tushare Provider、在线鉴权、凭据、实时行情、重试/缓存/断路器、
真实基金覆盖、成分股逐行导入、组合优化/相关性/流动性压力、调仓或 Recommendation、
自然语言/LLM/Gemini、多 Agent 对话、生产持久化和真实外部 SLA 均不在本阶段。
