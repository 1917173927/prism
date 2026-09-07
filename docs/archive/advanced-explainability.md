# Advanced Explainability：全链路高级可解释性对接书

Phase 37 提供了全链路决策高级可解释性（Advanced Explainability）模块。它将复杂的投研分析、画像约束、风险预算与合规检查转化为透明、可交互、可溯源的因果归因链（Causal Attribution Chain），并提供反事实边界分析（Counterfactual Boundary Analysis）与确定性失效清单。

## 架构原则与安全边界

1. **结构化因果追溯而非自由幻觉（Deterministic Causal DAG）**：
   - 决策解释直接锚定确凿的 `Finding -> Fact -> Evidence` 链条与用户画像量化约束。
   - 禁止由 LLM 脱离事实生成主观臆断的“投资故事”。
2. **多层级归因分析（Multi-level Attribution）**：
   - **画像约束归因**：解释为什么特定风险偏好得分和投资期限限制了最大配置上限。
   - **风险指标归因**：量化科技行业暴露或资产集中度对调仓动作（`REDUCE`/`HOLD`）的贡献权重。
   - **合规拦截归因**：若发生阻断，明确指明哪一条合规底线被触发。
3. **反事实分析（Counterfactual Conditions）**：
   - 清晰回答“如果在何种条件下，建议动作会发生改变”（例如：“如果科技暴露从 45% 降至 25% 以下，建议将从 REDUCE 转为 HOLD”）。
4. **确定性失效条件（Invalidation Conditions）**：
   - 列出明确可观测的失效触发事件（如财报发布、市场剧烈波动、数据超过有效时限）。

## 契约定义

### 请求契约 `advanced-explainability-request.v1`
- `request_id`: 请求标识
- `owner_id`: 所属用户 ID
- `generated_at`: 请求时间
- `recommendation_id`: 目标建议 ID
- `profile_score`: 画像得分（0~100）
- `risk_level`: 画像等级
- `findings`: 事实判断列表
- `action_type`: 建议动作类型
- `allocation_range`: 配置区间

### 响应契约 `advanced-explainability-response.v1`
- `schema_version`: `advanced-explainability-response.v1`
- `request_id`: 请求标识
- `owner_id`: 所属用户 ID
- `decision_summary`: 核心决策结论摘要
- `causal_nodes`: 因果链条节点列表（`node_id`, `node_type`, `label`, `value`, `status`, `influence_weight_pct`）
- `causal_edges`: 因果关系边（`from_node_id`, `to_node_id`, `relationship_type`）
- `key_drivers`: 核心驱动因素排序列表（`driver_name`, `contribution_pct`, `evidence_reference`, `explanation`）
- `counterfactuals`: 反事实边界分析列表（`scenario_name`, `condition_change`, `expected_action_change`, `rationale`）
- `invalidation_triggers`: 显式失效条件清单（`trigger_id`, `trigger_type`, `description`, `threshold_or_event`）

## API 接口

- `GET /api/v1/advisor/explainability-template`：获取可解释性默认模板与示例分析。
- `POST /api/v1/advisor/explainability-runs`：提交决策要素，生成完整因果解释与反事实分析报告。
