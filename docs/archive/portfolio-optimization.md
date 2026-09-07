# Portfolio Optimization：确定性目标结构提案

Phase 28 提供一个离线、fixture-first 的 Portfolio Engine 最小纵切。它在已确认的
Risk Profile 与 owner-scoped `PortfolioImportBundle` 上，生成可复算的目标权重结构，
用于回答“当前约束能否闭合、每个暴露资产的目标占比是多少”。输出是结构化提案，
不是 Recommendation、交易指令或收益预测。

## 输入与边界

服务只接受结构化 `RiskQuestionnaire`、`PortfolioImportBundle` 和固定场景 ID。服务端
会重新确认问卷，并重新计算 Exposure、Concentration 与 v1 Risk Budget；客户端不能
提交或覆盖这些派生结果。输入必须绑定同一 `owner_id`，Portfolio 的 snapshot、基金
穿透快照和基准币种仍遵循既有 Phase 2/3 契约。

本阶段只使用四个已版本化的预算维度：单资产、行业、Technology 聚合和
`UNCLASSIFIED` 聚合。现有 Risk Budget 没有可复用的资产类别上限，因此本阶段不会
凭空添加一套 category 规则。相关性、流动性、汇率、税费、交易成本、最小交易单位、
历史回测、真实 Provider、LLM/Gemini、生产持久化和订单执行均不在范围内。

## `CAP_AND_REDISTRIBUTE_V1`

算法使用 `Decimal`，把权重转换为百分比的整数百分点（1 个单位 = 0.01%），并以稳定
ID 排序解决所有舍入余数：

1. 从完整且无未分类残余的 Exposure contributions 按资产和行业聚合当前价值；同一
   资产若出现多个行业口径则停在 `REVIEW_REQUIRED`。
2. 对每个行业应用行业上限、Technology/未分类特殊上限和可容纳的单资产总容量；
   超过上限的当前权重被释放。Technology 是跨标签的全局上限，不能因出现多个
   Technology 标签而重复占用预算。
3. 将释放量按剩余 headroom 和稳定行业键确定性地分配，再在行业内按当前价值比例
   分配并逐步应用单资产上限。无法把总和闭合到 100.00% 时返回 `BLOCKED`，不输出
   虚假的目标。
4. 每个目标都绑定资产约束、行业约束，以及适用的 Technology/`UNCLASSIFIED`
   聚合约束。响应契约校验目标总和、current/target/delta 算术、约束引用闭包和
   聚合约束闭合；无代表资产的聚合约束只能为零。

这是一种透明的约束修复启发式，不是均值-方差或风险平价意义上的全局最优。相同的
请求、画像版本、持仓快照和方法版本必须得到相同的 ID、排序和数值。

## 状态语义

| 状态 | 含义 | 是否返回目标权重 |
| --- | --- | --- |
| `READY` | Exposure/Concentration 完整、行业已分类且约束可闭合 | 是 |
| `REVIEW_REQUIRED` | 穿透覆盖不足、非基准币种、未分类/歧义行业或其他输入质量问题 | 否 |
| `BLOCKED` | 上游失败或预算容量不足以同时满足约束 | 否 |

`READY` 仍可能带有 `assessment_status=REVIEW_REQUIRED`：这表示当前组合曾超过预算，
但确定性目标提案把它修复到上限内；它不等于已经执行或已经通过适当性审查。

## API 与工作台

- `GET /api/v1/advisor/portfolio-optimization-template` 返回合成五资产模板、四条
  规则和 `BASELINE_READY`、`SOURCE_PARTIAL`、`INFEASIBLE` 场景目录。
- `POST /api/v1/advisor/portfolio-optimization-runs` 接受严格 request，使用
  `X-Owner-ID` 做隔离，并在 API 注入边界再次验证响应身份和契约。

静态工作台显示方法版本、画像/Portfolio/报告身份、当前→目标权重、cap、delta、
约束算术和失效条件。切换 owner、持仓、问卷或场景会清空旧提案；动态内容只进入
DOM 节点的 `textContent`。请求不写 `DecisionEventStore`，结果也不会进入既有
Recommendation/Receipt 链。

## 为什么用户会选择 Prism

普通“组合优化”产品通常直接给一个模型权重或买卖列表。Prism 的可复核差异在于：

- 画像、快照、暴露、风险预算和方法版本都显式绑定；
- 每一项目标都能沿资产/行业/聚合约束回到当前值、上限和释放算术；
- 数据不完整时保持 `REVIEW_REQUIRED`/`BLOCKED`，不以零值或默认权重掩盖不确定性；
- 结果明确不是交易指令，并列出画像、持仓、穿透覆盖率或方法变化时的失效条件。

这使 MVP 的价值从“多一个黑箱权重模型”转为“能解释、能重放、知道何时不能算”。

