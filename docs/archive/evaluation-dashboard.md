# Evaluation Dashboard：评测与监控看板对接书

Phase 36 提供了基于 Prism 固定评测集 `eval_cases/` 的 Evaluation Dashboard（评测与监控看板）模块。它将离线测试集执行与实时聚合能力暴露为标准、结构化且安全的指标看板，支持多维度系统质量评估。

## 架构原则与安全边界

1. **真实评测指标无伪造（No Fabricated Metrics）**：
   - 所有的指标数值（Pass Rate、Coverage Rate、Latency 等）均来自确定性测试用例的真实执行，严禁在后端硬编码虚假高分。
2. **多维度质量评估体系**：
   - 涵盖 Fact 真实性、Evidence 覆盖率、数值幻觉率（确定性架构下为 0.00%）、画像匹配度、风险识别率、合规阻断率与 P50/P95 响应延迟。
3. **安全隔离与非破坏性**：
   - 评测执行在内存隔离沙箱中运行，不污染生产/主数据库的决策事件或用户记忆。

## 契约定义

### 请求契约 `evaluation-dashboard-request.v1`
- `request_id`: 请求标识
- `operator_id`: 操作者/用户 ID
- `generated_at`: 请求生成时间戳
- `selected_cases`: 选定的测试案例列表（为空时默认运行全量固定测试集）
- `repeat_count`: 重复运行次数（默认 1，用于测试语义幂等一致性）

### 响应契约 `evaluation-dashboard-response.v1`
- `schema_version`: `evaluation-dashboard-response.v1`
- `request_id`: 请求标识
- `generated_at`: 完成时间
- `total_cases`: 总评测案例数
- `passed_cases`: 达标用例数
- `summary_scores`:
  - `case_pass_rate_pct`: 测试用例通过率 %
  - `profile_alignment_rate_pct`: 用户画像与约束对齐率 %
  - `evidence_coverage_rate_pct`: 决策证据闭环覆盖率 %
  - `hallucination_rate_pct`: 事实幻觉率 %（目标 0.00%）
  - `risk_detection_rate_pct`: 风险违规拦截覆盖率 %
  - `compliance_pass_rate_pct`: 合规规则通过率 %
  - `semantic_consistency_rate_pct`: 语义指纹重放一致性 %
- `latency_metrics`:
  - `p50_ms`: 50分位耗时
  - `p95_ms`: 95分位耗时
  - `p99_ms`: 99分位耗时
  - `max_ms`: 最大耗时
- `case_details`: 逐用例执行结果明细列表（`case_id`, `description`, `expected_status`, `actual_status`, `passed`, `latency_ms`, `receipt_digest`）

## API 接口

- `GET /api/v1/advisor/evaluation-dashboard-summary`：获取最新一次或默认基准评测报告。
- `POST /api/v1/advisor/evaluation-dashboard-runs`：触发测试集运行并返回最新评测看板。
