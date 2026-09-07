# Portfolio Rebalancing：组合再平衡行动规划对接书

Phase 35 提供了离线、确定性、owner-scoped 的 Portfolio Rebalancing（组合再平衡行动规划）模块。它基于当前持仓组合（`PortfolioImportBundle`）与目标资产配置（来自画像规则或组合优化结果），通过确定性 Decimal 算术计算出最小调仓差异，并生成带流动性执行优先级的调仓动作序列。

## 架构原则与安全边界

1. **确定性算术与现金守恒**：
   - 所有的市值计算、权重差额（`delta_weight_pct`）与变动金额（`cash_delta_cny`）均使用 `Decimal`，两位小数四舍五入。
   - 组合总价值在再平衡前后严格守恒，买入总额与卖出总额保持自洽。
2. **死区阈值（Deadband）与抑噪**：
   - 支持设置再平衡死区阈值（默认 `0.50%`）。若某项资产的权重变动绝对值小于死区阈值，则不生成买卖操作，保持 `HOLD`，避免微小调仓带来的摩擦成本。
3. **流动性优先执行步长（Ordered Execution Steps）**：
   - 调仓步骤严格按照“先卖后买（Sell-before-Buy）”原则排序，释放现金流动性后再执行买入。
4. **状态降级与非自主交易免责**：
   - 若持仓中存在未穿透资产或数据缺失，状态安全降级为 `REVIEW_REQUIRED`。
   - 所有输出明确标注为 `ADVISORY_ONLY`，严禁自主直接触发交易所交易下单。

## 契约定义

### 请求契约 `portfolio-rebalancing-request.v1`
- `request_id`: 请求唯一标识
- `owner_id`: 所属用户 ID
- `generated_at`: 带时区的请求生成时间戳
- `portfolio_bundle`: 完整持仓导入包
- `target_weights`: 各资产目标权重字典（键为 `asset_id`，值为 Decimal 目标百分比，总和必须为 100.00%）
- `deadband_pct`: 死区阈值百分比（默认 0.50%）
- `max_turnover_pct`: 最大允许换手率限制（默认 50.00%）

### 响应契约 `portfolio-rebalancing-response.v1`
- `schema_version`: `portfolio-rebalancing-response.v1`
- `request_id`: 请求标识
- `owner_id`: 所属用户 ID
- `status`: `READY` / `REVIEW_REQUIRED` / `BLOCKED`
- `actions`: 资产层级调仓操作列表：
  - `asset_id`: 资产标识
  - `asset_name`: 资产名称
  - `asset_type`: 资产类别
  - `current_weight_pct`: 当前持仓权重 %
  - `target_weight_pct`: 目标持仓权重 %
  - `delta_weight_pct`: 变动权重 %
  - `current_value_cny`: 当前市值 CNY
  - `target_value_cny`: 目标市值 CNY
  - `cash_delta_cny`: 变动金额 CNY（正数为买入，负数为卖出）
  - `action_type`: `BUY` / `SELL` / `REDUCE` / `HOLD`
  - `rationale`: 调仓原因说明
- `execution_steps`: 按流动性排序的操作步骤序列（`step_number`, `action_type`, `asset_id`, `amount_cny`, `estimated_liquidity_impact`）
- `metrics`:
  - `total_portfolio_value_cny`: 组合总市值
  - `total_turnover_pct`: 总换手率 %
  - `total_buy_cny`: 买入总额
  - `total_sell_cny`: 卖出总额
  - `net_cash_flow_cny`: 净现金流
- `issues`: 降级或风险提示列表
- `invalidation_conditions`: 调仓建议失效条件

## API 接口

- `GET /api/v1/advisor/rebalancing-template`：获取再平衡默认参数模板与示例输入。
- `POST /api/v1/advisor/rebalancing-runs`：提交持仓与目标，生成确定性再平衡方案。
