# Recommendation History：不可变历史建议追溯与审计对接书

Phase 34 提供了离线、确定性、owner-scoped 的 Recommendation History（历史建议追溯与审计）模块。它基于系统已持久化的不可变 `DecisionEvent`、`DecisionReceipt` 和 `DecisionTrace` 存储链，提供多维查询、版本生命周期索引与两两决策回执之间的确定性差分比对能力。

## 架构原则与安全边界

1. **Owner 严格隔离**：
   - 所有历史记录检索与对比必须提供合法且一致的 `owner_id`。
   - 跨 Owner 查询将被严格拦截（返回 403/422），防止多租户数据泄露。
2. **不可变审计与哈希验证**：
   - 历史建议条目包含 `content_hash` 与 `event_id`，保证历史回执不可篡改。
   - 历史回溯不重新执行 LLM 生成，直接读取确定性持久化证据快照。
3. **确定性对比模型（History Diff）**：
   - 支持对比两个同 Owner 的历史回执（`receipt_a` vs `receipt_b`）。
   - 逐项对比：画像得分变化、动作演变（如 `HOLD` -> `REDUCE`）、目标资产、配置区间、Finding 条目数、以及失效条件的差异。

## 契约定义

### 请求契约 `recommendation-history-query.v1`
- `owner_id`（必填）：所属用户 ID。
- `limit`（可选，默认 20，最大 100）：分页限制。
- `action_type`（可选）：过滤特定建议类型（如 `HOLD`、`REDUCE`）。
- `asset_id`（可选）：过滤特定标的。

### 响应契约 `recommendation-history-response.v1`
- `schema_version`: `recommendation-history-response.v1`
- `owner_id`: 当前所属用户 ID。
- `total_count`: 匹配的历史事件总数。
- `items`: 历史条目列表，每项包含：
  - `event_id`: 决策事件唯一标识
  - `receipt_id`: 决策回执唯一标识
  - `action_type`: 建议动作类型
  - `asset`: 投资标的代码与名称
  - `allocation_range`: 建议配置区间（min ~ max %）
  - `risk_score`: 决策时的风险偏好得分
  - `profile_version`: 决策时的画像版本
  - `generated_at`: 带时区的生成时间戳
  - `content_hash`: 回执内容哈希
  - `finding_count`: 关联的 Finding 数量
  - `compliance_passed`: 合规检查状态

### 对比契约 `recommendation-comparison.v1`
- `schema_version`: `recommendation-comparison.v1`
- `owner_id`: 所属用户 ID
- `receipt_a_id`: 基准回执 ID
- `receipt_b_id`: 对比回执 ID
- `action_changed`: 建议动作是否改变
- `action_transition`: 动作演变描述（如 `HOLD -> REDUCE`）
- `risk_score_delta`: 风险画像得分变动（Decimal）
- `allocation_min_delta`: 最小配置权重变动（Decimal）
- `allocation_max_delta`: 最大配置权重变动（Decimal）
- `new_findings_count`: 新增事实判断数
- `invalidation_conditions_diff`: 失效条件演变

## API 接口

- `GET /api/v1/advisor/recommendation-history`：获取当前用户的历史建议列表。
- `POST /api/v1/advisor/recommendation-history/compare`：提交两个回执 ID 进行差分对比。
