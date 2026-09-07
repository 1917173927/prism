# Advisor Query API 与 Fixture 边界

Phase 14 增加了一个 fixture-first 的结构化查询入口：

```text
POST /api/v1/advisor/queries
X-Owner-ID: gate-owner-001
```

请求必须是 `advisor-query.v1`，包含有限字符集的 `query_id`、已登记的
`fixture_id`、带时区的 `generated_at`、`RiskQuestionnaire` 和
`PortfolioImportBundle`。问卷、持仓 bundle 和 `X-Owner-ID` 必须属于同一个
owner。请求没有自然语言建议、订单、目标价、收益承诺或凭据字段；额外字段、
敏感字段和无时区时间都会在 HTTP 边界被拒绝，错误响应不回显原文。

## 执行链

`FixtureAdvisorQueryService` 只编排已有确定性模块，顺序固定为：

```text
RiskQuestionnaire
  -> Profile
  -> Exposure / Concentration
  -> Risk Budget
  -> Allocation Envelope
  -> Fixture Provider Research Run
  -> Evidence -> Fact -> Finding
  -> Risk Gate + Compliance Gate
  -> HOLD / REDUCE Composer
  -> Decision Receipt
  -> owner-scoped DecisionEvent
```

`generated_at` 是重放锚点，Provider 的 `retrieved_at`、研究 run 时间、画像、
暴露和回执均使用该时间。固定输入的重复请求会得到相同 composition、receipt
content hash 和 DecisionEvent identity；SQLite store 返回 `created=false`，不会
覆盖已有内容。

## 离线 Fixture

默认 fixture manifest 位于
`app/fixtures/advisor/two_lineage_research.json`，Provider 输入位于
`app/fixtures/advisor/providers/`。两条来源使用不同 `source`、`record_id` 和
`lineage_id`，对同一合成收入 claim 提供相同的 `10.00 CNY` 值。manifest 在加载
时校验 owner 无关的静态 schema、source/lineage 唯一性、操作类型和敏感字段；
Provider 初始化时仍由既有四态契约验证 request/result。

这些文件仅用于本地测试和演示，不代表实时行情、同花顺问财 SkillHub 接入或
真实用户持仓。

## 结果语义

- BALANCED 问卷在合成完整证据下可产生带 Receipt 的 `HOLD`；
- CONSERVATIVE 问卷在相同持仓下可产生 breach-bound `REDUCE`；
- Provider `PARTIAL`、`EMPTY`、`FAILED` 或证据冲突只会产生
  `REVIEW_REQUIRED`/`BLOCKED`，不携带 Receipt、Recommendation 或 Evidence/Finding
  trace；
- 研究结果即使结构上可解析，也必须逐条匹配 manifest 的 source、record、lineage、
  field、unit、period 和 Decimal value，不能靠集合去重掩盖重复或额外证据。

## 与工作台的关系

查询成功保存为 Phase 13 的 `DecisionEvent`，因此现有根路径工作台可以通过
owner-scoped list/detail API 读取回执，并展开 `Recommendation -> Finding -> Fact ->
Evidence`。本阶段没有引入聊天、LLM、真实鉴权、生产数据库或交易副作用。
