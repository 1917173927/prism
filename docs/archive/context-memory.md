# Phase 29：结构化上下文记忆

Prism 的上下文记忆是可审计的结构化快照，不是聊天记录。一次记录只包含已经在
当前会话确认过的 `RiskQuestionnaire`、`RiskProfile`、`PortfolioImportBundle`，以及
可选的结构化 Intent/Plan 和研究、组合优化 ID 引用。原始自然语言、Prompt、模型输出、
Provider 响应和凭据永远不进入该边界。

## 身份与存储

- `memory_id` 为 `context-memory:<32 位十六进制>`，由 owner 与规范化内容 hash
  服务端派生；客户端不能提交或覆盖它。
- `content_hash` 是排除 `memory_id`、`saved_at`、`source` 和 schema 元数据后的
  canonical JSON SHA-256。相同 owner、相同结构化内容重复保存会幂等返回第一次记录；
  记录本身不可更新或删除。
- SQLite 迁移 `002_context_memory.sql` 与 DecisionEvent 共用 WAL、事务、owner 校验
  和损坏记录安全错误。读取按 UTC `saved_at`、`memory_id` 降序，单次最多 100 条。

## HTTP

所有请求需要本地 `X-Owner-ID` 隔离键（它不是身份认证）：

```text
POST /api/v1/advisor/context-memory
GET  /api/v1/advisor/context-memory?limit=20
```

POST 只接受 `context-memory-write-request.v1`，服务端会重新验证问卷、画像、持仓、
Intent/Plan 的 owner、问卷、bundle、snapshot 闭合。GET 返回当前 owner 的完整结构化
记录，便于用户检查 hash、画像版本、bundle/snapshot 和保存时间；不会返回任意 JSON 或
聊天文本。

## 工作台恢复

工作台刷新后只读取最近列表，不自动覆盖当前表单。用户点击“显式恢复到当前会话”后，
才载入保存的问卷、画像和 Portfolio，并清空旧 Advisor、Research、Optimization 派生
结果；这些流程必须用恢复后的上下文重新运行。切换 owner 或过期异步响应会清空旧列表和
选择，恢复失败不回显原始输入。

100 owner 的本地 ASGI/SQLite 并发基线由 `python -m tools.context_memory_load_test`
生成；该数字只用于回归和隔离检查，不代表真实网络 SLA、认证或云端持久化能力。
