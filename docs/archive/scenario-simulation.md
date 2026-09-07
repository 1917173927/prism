# Scenario Simulation：确定性情景模拟与压力分析

Phase 33 提供了离线、确定性、owner-scoped 的 Scenario Simulation 最小纵切。它在同一已确认的 Risk Profile 与 `PortfolioImportBundle` 基线快照上，应用无状态的假设覆盖层（Scenario Overlay），重新执行完整的 Exposure -> Concentration -> Risk Budget Assessment -> Portfolio Optimization 确定性流水线，并生成严格可审计的基线 vs 模拟差分对比回执（`ScenarioSimulationResponse`）。

## 架构原则与安全边界

1. **Evidence First & Deterministic**：所有基线与模拟计算完全采用确定性 Decimal 算法（无随机种子、无浮点漂移、无自然语言生成）。
2. **假设与事实严格隔离**：
   - 真实持仓快照与上游证据保持原始只读状态。
   - 所有模拟结果与派生数值显式打上 `derived_values_are_hypothetical=true` 标记，且元数据与差分仅标记为 `SIMULATED`。
   - 严禁将任何模拟数据升格为 `VERIFIED` 事实或买卖建议。
3. **三态质量与防御性降级**：
   - 继承上游流水线的质量状态。若输入存在穿透缺失（如基金覆盖率低于 100%）或部分降级，模拟结果安全停在 `REVIEW_REQUIRED`。
   - 若上游计算失败或约束不可行，停在 `BLOCKED`。
   - 只有当基线与模拟双侧均完整就绪（READY）时才生成有效差分，绝不伪造虚假零值差分。

## 场景覆盖层定义

| 场景 ID | 覆盖层类型 | 参数与变化量 | 预期行为 |
| --- | --- | --- | --- |
| `BASELINE_READY` | `IDENTITY` | 无变化（delta = 0） | 基线与模拟完全一致，验证确定性幂等性与零差分闭合 |
| `TIGHTER_TECH_CAP` | `LIMIT_OVERRIDE` | `max_technology_weight_pct` 收紧 10.00% | 触发更严格的科技行业预算限额，观察目标重分配变化 |
| `TOP_ASSET_TRIM_10PP` | `PORTFOLIO_ALLOCATION_SHIFT` | 第一大资产权重削减 10.00% 并等比重分配至其余资产 | 观察资产集中度 HHI 与单一最大持仓权重变化 |
| `LOOKTHROUGH_PARTIAL` | `DATA_COVERAGE` | 基金/ETF穿透覆盖率降至 80.00% | 触发数据质量降级，状态转为 `REVIEW_REQUIRED` 并保留 Issue 审计追踪 |

## 差分指标体系

`ScenarioSimulationResponse` 提供两组有序差分：
1. **关键宏观指标差分（`metric_diffs`）**：
   - `metric:01:total_portfolio_value_cny`（组合总市值 CNY）
   - `metric:02:technology_weight_pct`（科技行业总暴露 %）
   - `metric:03:top_asset_weight_pct`（单一最大资产权重 %）
   - `metric:04:asset_hhi`（资产集中度 HHI 指数）
   - `metric:05:max_technology_cap_pct`（科技行业风险预算上限 %）
2. **组合目标权重差分（`target_diffs`）**：
   - 按 `target_id` 升序排列，逐一对比各资产在基线与模拟优化下的目标权重变化（`baseline_value`, `scenario_value`, `delta`）。

## API 契约与工作台交互

- `GET /api/v1/advisor/scenario-simulation-template`：获取场景目录与支持维度。
- `POST /api/v1/advisor/scenario-simulation-runs`：提交模拟请求并获取不可变回执。
- 前端工作台（`#scenario-simulation`）提供场景选择器、基线 vs 模拟卡片、结构化差分表格以及失效条件展示。
