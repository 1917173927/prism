# 四类研究专员节点矩阵

Phase 16 把项目规范中的四类研究职责落成一个结构化、fixture-first 的执行边界：

| 产品轨道 | 运行时 node kind | 允许的 Provider operation | 合成 claim |
| --- | --- | --- | --- |
| Macro | `MACRO` | `MACRO_DATA` | 政策利率 |
| Industry | `INDUSTRY` | `INDUSTRY_DATA` | 科技行业增长 |
| Stock | `STOCK` | `COMPANY_DATA` / `MARKET_DATA` | 报告期收入 |
| ETF/Fund | `FUND` | `FUND_DATA` | ETF 科技暴露 |

`ResearchSpecialistNode` 是一个**来源节点**，不是自由聊天 Agent。一个轨道可以
有多个来源节点；打包演示矩阵每轨道有两个节点，分别使用不同的 source、record 和
lineage。`ResearchSpecialistMatrix` 要求至少覆盖四种 kind，并在同一 claim 的来源
之间保持 subject、metric、unit、period、expected value 和 Finding 元数据一致。

## 离线执行

```python
import asyncio
from app.research import ResearchSpecialistMatrixRequest
from app.service import FixtureResearchSpecialistMatrixService

service = FixtureResearchSpecialistMatrixService()
output = asyncio.run(service.run(ResearchSpecialistMatrixRequest(
    matrix_id=service.matrix_id,
    request_id="local-four-track-001",
    owner_id="demo-owner",
    generated_at="2026-09-02T01:00:00Z",
)))
```

服务只做以下编排：owner 重绑定 → 既有 `ResearchPlan`/bounded executor → 合成
`FixtureFinancialProvider` → normalized Evidence/Observation → 既有 Cross Validation
和 Evidence/Finding bridge。成功时四个 claim 都是 `SUPPORTED`，运行结果为 `READY`，
trace 有八条 Evidence、四个 Fact 和四个 Finding；输出永远没有 Recommendation、
Decision Receipt 或交易动作。

固定 `request_id`、`generated_at` 和同一矩阵会得到相同的 run/validation/bridge ID。
Evidence 不携带 owner，所以 owner 闭包由 Observation、矩阵和输出契约共同保证；
不同 owner 只能得到自己重绑定后的节点和观察。

## 降级与审计

- 任一 required 来源为 `PARTIAL`、`EMPTY`、`FAILED` 或超时，既有 run 状态机保留
  四态语义；pipeline 变为 `REVIEW_REQUIRED` 或 `BLOCKED`，不产生 Fact/Finding，
  也不把缺失转成 0。
- 两个来源对同一 claim 给出不同数值时，run 仍可完成，但 Cross Validation 为
  `UNRESOLVED`，结果只能待复核；这不是多数票，也不是模型置信度。
- Evidence/record/source/lineage 漂移、伪造 Provider 身份、跨 owner、额外字段、
  敏感输入和 Pydantic bypass 都在契约或服务边界拒绝，错误不带出 raw payload 或
  异常文本。
- `ResearchClaimSpec.observation_ids` 只用于多 claim 执行时划定 claim 自己的
  scope，并且必须包含该 subject/metric/unit/period 的全部已执行观察，不能借此
  隐藏同口径的冲突观察。

## 与产品路线的关系

这一步证明的是“四类结构化职责可以并行、可回放、可交叉验证”。合成 fixture 不代表
实时宏观、行业、个股或 ETF/Fund 数据已经接入；SkillHub 文档、授权和凭据确认后，
未来 Provider adapter 可以替换 fixture，而不改变 node、Evidence、lineage 或降级
语义。完整 Portfolio/Advisor/Risk Profile 视图和真实浏览器旗舰流由后续阶段消费
这个矩阵。
