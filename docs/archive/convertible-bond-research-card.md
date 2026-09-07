# Demo H：可转债资产研究 Evidence Card

Phase 27 把 `Prism.md` 第 15 节要求的最低可转债能力落成一张
fixture-first、owner-scoped 的资产事实卡。它用来回答“转股参数、债底、信用和
流动性这些数字能否被核对”，不是实时行情、完整估值模型或交易建议。

## 用户看到什么

工作台从 `GET /api/v1/advisor/convertible-bond-research-template` 读取固定合成
标的、报告期、指标标签、面值、信用/流动性等级标签、风险阈值和五个离线场景，
再由 `POST /api/v1/advisor/convertible-bond-research-runs` 运行 owner-scoped 回放：

```text
两条独立 lineage
    -> CONVERTIBLE_BOND_DATA Provider 四态与 bounded run
    -> lineage-aware Cross-Validation
    -> raw VERIFIED Facts
    -> Decimal conversion_value / conversion_premium_pct 公式 Facts
    -> deterministic risk Findings
    -> 风险摘要与 Finding -> Fact -> Evidence
```

基线最低指标为：

- 正股价格 `underlying_stock_price`；
- 转股价 `conversion_price`；
- 转债价格 `bond_price`；
- 转股价值 `conversion_value`（`underlying_stock_price / conversion_price * 100`）；
- 转股溢价率 `conversion_premium_pct`
  （`(bond_price / conversion_value - 1) * 100`）；
- 债底 `bond_floor`；
- 到期收益率 `yield_to_maturity_pct`；
- 信用评级序数 `credit_rating_rank`（安全 label 映射为 AAA/AA+/AA/AA- 等）；
- 流动性等级序数 `liquidity_score`（安全 label 映射为高/中/低）。

面值固定为 100 CNY；服务端使用有限 Decimal、两位小数和 `ROUND_HALF_UP` 计算
派生值。Provider 不请求也不能伪造两个派生字段；响应契约还会再次复算并拒绝
不一致的注入结果。

## 五个可回放场景

| 场景 | 预期状态 | 语义 |
| --- | --- | --- |
| `BASELINE_READY` | `COMPLETED/READY` | 双源一致，九个最低 Fact 与公式/风险 Finding 可用。 |
| `SOURCE_DISAGREEMENT` | `COMPLETED/REVIEW_REQUIRED` | 来源 B 的转股价冲突；双方 Evidence 保留，不升级任何 Fact/Finding。 |
| `SOURCE_PARTIAL` | `FAILED/REVIEW_REQUIRED` | 来源 B 缺少债底，节点为 `PARTIAL/MISSING_FIELDS`。 |
| `SOURCE_EMPTY` | `FAILED/REVIEW_REQUIRED` | 来源 B 在声明期间无记录，显示范围说明，不填零值。 |
| `SOURCE_FAILED` | `FAILED/REVIEW_REQUIRED` | 来源 B 安全失败，显示 `FAILED/SOURCE_UNAVAILABLE`，不伪装成 EMPTY。 |

所有非 `READY` 响应仍返回 Cross-Validation、节点原因和可审计 Evidence，但
`facts`、`findings` 为空，风险为 `NOT_ASSESSED`；响应和 trace 永远不含
Recommendation，也不写 DecisionEvent。

## 确定性风险规则

版本化方法为 `convertible-bond-risk.v1`：

| 条件 | Finding | 严重度 |
| --- | --- | --- |
| 溢价率 `> 30%` | `CONVERTIBLE_PREMIUM_WARNING` | WARNING |
| 债底 `< 80` | `CONVERTIBLE_BOND_FLOOR_WARNING` | WARNING |
| 到期收益率 `< 0%` | `CONVERTIBLE_NEGATIVE_YIELD` | WARNING |
| 信用评级序数 `>= 4` | `CONVERTIBLE_CREDIT_RISK` | CRITICAL |
| 流动性序数 `>= 3` | `CONVERTIBLE_LIQUIDITY_RISK` | WARNING |

风险摘要只允许 `NOT_ASSESSED`、`CLEAR`、`WATCH`、`HIGH_RISK`，并必须引用所有
非 INFO Finding；这些状态不表示 BUY/SELL、HOLD/REDUCE、仓位或收益承诺。

## 契约与隔离

- 请求只接受 owner、request ID、固定 subject/period、timezone-aware
  `generated_at` 和枚举场景；extra、敏感字段、naive 时间、未知场景和跨 owner/
  scope 输入在 API 边界拒绝。
- 模板不公开 Provider 名称、fixture 原文、请求参数或凭据，只公开安全标签、公式
  和风险规则。
- 两个节点、所有 raw validation、Fact、Finding、Evidence 和 formula lineage
  闭合到本次 owner/subject/period；API 注入边界会重新构造并校验完整响应，再检查
  request/scope/scenario closure。
- 工作台使用同源 `fetch` 与 `textContent`/节点 API；owner 或场景变化清空旧卡，
  异步 sequence 不允许旧响应写回；页面无外部请求。

## 复用边界与产品差异

本卡复用 `FixtureFinancialProvider`、Provider 四态协议、bounded research run、
normalization、Cross-Validation、Evidence/Finding bridge 和 `DecisionTrace`，并
沿用 Phase 26 Fund 卡的 manifest、双 lineage overlay、API 二次校验与 Evidence 展开
结构。新增代码只负责可转债字段契约、公式和风险规则；`tradeeye-copilot` 与
`TradeEye` 仍是只读参考，Prism 不做运行时导入。

普通产品可以把可转债压成“攻守兼备”的一句话或一个分数，用户看不到转股价值的
输入，也不知道信用/流动性缺失时结论是否仍成立。Prism 把债券和股票两条风险来源
拆开，先展示期间与 lineage，再用可复算公式和可见失效边界升级结论。来源冲突时
宁可停在待复核，也不让漂亮的评级掩盖不可核验的数字。

## 明确不做

真实同花顺问财/SkillHub/Tushare Provider、在线鉴权、实时全市场行情、赎回/回售/
强赎条款、纯债估值、隐含波动率、久期/凸性、历史回测、排名、组合优化、真实持仓
写入、自然语言/LLM/Gemini、交易/Recommendation、DecisionEvent 持久化和生产级
缓存/重试/断路器/外部 SLA 均留在后续阶段。
