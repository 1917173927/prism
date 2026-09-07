# Portfolio / Risk Profile 上下文工作台

Phase 18 把现有 fixture-first Advisor 纵切已经使用的两个输入上下文展示在工作台：
Portfolio 持仓快照和 Risk Profile 问卷。它是一个可核对的只读视图，不是持仓管理、
风险计算或交易入口。

## 数据来源与显示边界

页面只调用 owner-scoped `GET /api/v1/advisor/query-template`，不读取 fixture 文件，
也不在浏览器重建或重算模型。服务端先按 `X-Owner-ID` 重绑定并验证
`AdvisorQueryTemplateResponse`，页面再用 DOM `textContent` 显示：

- Portfolio owner、bundle ID、position snapshot ID、as-of、基准币种；
- 每个 position 的资产 ID/名称/类型、position ID、数量和原始 market value；
- 每个基金/ETF 穿透快照的 parent、snapshot、coverage、as-of，以及 underlying
  holding 的 ID、名称、sector、weight 和 as-of；
- Risk Profile questionnaire ID、owner、回答时间、承受分数、期限、流动性、经验、
  收益预期、最大回撤容忍度和已存在的 expected-return range。

这些数值均是合成模板的原值。Portfolio 区域明确标注“只读 · 合成模板”；页面没有
上传、编辑、删除、再平衡、目标价或下单控件。Receipt 产生后，原有 Risk Profile
区域继续显示 profile、risk assessment、allocation、research 等回执绑定元数据，
不把模板上下文冒充为新的计算结果。

## Owner 与异步安全

`X-Owner-ID` 目前只是本地隔离键，不等同认证。每个模板响应的 questionnaire、
portfolio、position snapshot 和 nested owner 都必须与请求 owner 闭合。切换 owner，
或直接从 Advisor/Research 操作新 owner，会立即清空上一 owner 的模板、事件、回执、
证据和研究视图；模板或事件的异步响应只有在 owner 与递增 sequence 都仍匹配时才
允许写入 DOM。模板失败显示统一安全错误并保持空上下文，不回显异常、请求或敏感字段。

## 复用与产品差异

实现复用 Phase 2 的不可变 Profile/Portfolio contracts、Phase 14 的 template owner
rebind、Phase 15 的 Advisor/Evidence/Receipt 工作台和 Phase 17 的 Research Tracks
视觉语法。它没有复制 `tradeeye-copilot`/`TradeEye` 的运行时代码，也没有引入新的
金融公式、Provider、LLM 或数据库表。

聊天式产品通常只给出一句结论，用户无法确认结论使用了什么持仓和风险假设。Prism
把“我持有什么”“我允许承受什么”“研究证据如何成立”和“回执为何改变”放在同一
条可钻取链上；可核对的输入、明确的合成/只读边界和拒绝虚构事实，是本产品相对
更会聊天的产品的选择理由。

## 明确未做

- 真实账户认证、多用户会话、Portfolio/Risk Profile CRUD、CSV/券商导入和生产数据库；
- 暴露、集中度、风险预算、相关性、优化、目标价、收益承诺或其他新计算；
- 真实 SkillHub/Tushare/网络 Provider、LLM/Gemini、自然语言对话、后台任务、推送或
  订单/交易/再平衡；
- 真实持仓、真实风险等级、100 用户并发或 3 秒端到端 SLA 的结论。

因此，这个工作台解决的是 MVP 的“输入可见、结果可核对”问题，不能被误读为生产
投顾或真实账户管理系统。
