# Advisor Query 结构化工作台

Phase 15 将 Phase 14 的 owner-scoped Advisor Query API 接成一个可复核的本地
工作台交互。它是合成 Fixture 驱动的演示，不是实时行情、自然语言投顾或交易入口。

## 交互边界

Advisor 面板提供显式字段：Query ID、损失容忍、投资期限、流动性需求、投资经验、
收益预期和最大回撤。页面首先读取 `GET /api/v1/advisor/query-template`，服务端按
`X-Owner-ID` 重绑定模板中的 owner；提交时只组装已存在的
`AdvisorQueryRequest`，再调用 `POST /api/v1/advisor/queries`。

服务端仍是唯一业务入口，依次复用 Profile、Portfolio、Exposure、Risk Budget、
Allocation、Research、Evidence/Finding、Risk/Compliance Gate、Recommendation
Composer 和 DecisionEvent Store。前端不计算金融指标、不拼接 Evidence、不生成建议，
也不接受自然语言或订单字段。

## 可复核演示路径

1. 使用任意非空 owner 打开工作台，模板元数据显示合成 fixture 的生成时间和持仓范围。
2. 以默认 BALANCED 问卷提交唯一 Query ID，页面显示 `PASS · 已保存` 和 `HOLD`。
3. 使用新的 Query ID 选择 CONSERVATIVE（低损失容忍、短期限、高流动性、低经验、低收益
   预期、10% 最大回撤），页面显示 `PASS · 已保存` 和 `REDUCE`，并能展开
   `Recommendation → Finding → Fact → Evidence`。
4. 再次提交同一 owner 与 Query ID，结果显示 `PASS · 已复用`，不会产生第二个事件。
5. 切换另一个 owner，列表为空，旧 owner 的事件、Query ID 和持仓不会泄露。

## 安全与边界

- 模板、请求和响应在 Pydantic 边界重新校验；owner、fixture、敏感字段和额外字段不能
  通过浏览器或 `model_construct` 绕过。
- 事件仍按 owner 隔离并以内容哈希幂等保存；研究退化继续保持
  `REVIEW_REQUIRED`/`BLOCKED`，不展示 Receipt、可执行 Recommendation 或闭合 Evidence。
- 静态页面只使用 CSP、`textContent` 和 DOM API；没有 inline script、`innerHTML`、
  外部网络引用、LLM 调用、凭据或交易副作用。
- `generated_at` 来自合成 manifest 并注入 Provider clock，保证同一输入可以重放；这不
  代表实时数据新鲜度或生产 SLA。

相关契约与验收记录见
[Phase 15 计划](plans/2026-09-02-mvp-phase-15-advisor-query-workbench.md) 和
[Advisor Query API](advisor-query-api.md)。
