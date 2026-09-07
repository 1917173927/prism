# Phase 20：结构化上下文确认

Phase 20 把固定合成模板扩展为一个可核对的、本地会话级输入边界。它只接受已经脱敏的
结构化 JSON，不宣称真实账户同步，也不把粘贴动作当作认证或持久化。

## API contracts

- `POST /api/v1/advisor/context/portfolio`
  - Header：`X-Owner-ID`；必须与 `portfolio.owner_id` 完全一致。
  - Body：`portfolio-context-request.v1`，只包含已验证的
    `PortfolioImportBundle`。
  - Response：`portfolio-context-response.v1`，返回重新验证的 bundle 和
    `position_count`、`fund_snapshot_count`、`holding_count` 结构计数。
- `POST /api/v1/advisor/context/profile`
  - Header：`X-Owner-ID`；必须与 `questionnaire.owner_id` 完全一致。
  - Body：`profile-context-request.v1`，只包含 `RiskQuestionnaire`。
  - Response：`profile-context-response.v1`，返回问卷和既有确定性 scorer 产生的
    `RiskProfile`。

两个接口都 `extra=forbid`、拒绝敏感字段/字符串、要求 timezone-aware 时间并且不写入
`DecisionEventStore`。验证失败只返回统一安全错误，不回显粘贴原文。Profile ID 在
owner 与 questionnaire ID 相同的情况下稳定不变，确认不会产生 Recommendation 或
Receipt。

## Workbench behavior

Portfolio panel 支持粘贴一个 `portfolio-import-bundle.v1` 对象，浏览器在同源 API
验证后展示原值。Risk Profile panel 从现有表单构造问卷并请求确定性确认。Advisor
查询优先使用当前会话确认的 Portfolio，未确认时使用 owner-rebound 合成模板；风险
表单仍由 Advisor 服务端重新计算 Profile。只有 Advisor 查询成功才写入
`DecisionEvent`，Receipt 会绑定实际使用的 bundle 与 snapshot ID。

切换 owner、模板失败、异步响应过期或确认失败都会清空已确认会话上下文。所有动态
内容通过 text-only DOM 渲染，页面保持同源 CSP；本阶段不提供文件上传、账户同步、
认证、Profile/Portfolio CRUD、真实 Provider、LLM、交易或生产 SLA。
