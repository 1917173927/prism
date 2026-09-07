# Phase 21：MVP 固定评测集

`eval_cases/` 是 Prism 本地 fixture-first 纵切的可版本化验收样本。它们用于回答
“同一证据在不同用户约束下是否产生不同且可解释的结果”，不是市场预测、收益率或
真实 Provider 的准确率测试。

## Case contract

每个 JSON 文件使用 `mvp-eval-case.v1`，包含一个结构化问卷、Portfolio 变体、Provider
变体和明确预期。当前固定集覆盖：

| Case | 覆盖 | 预期 |
| --- | --- | --- |
| `balanced-hold` | 中等风险、完整分散组合 | `PASS` / `HOLD` / Receipt |
| `conservative-reduce` | 保守短期画像 | `PASS` / `REDUCE` / Receipt |
| `growth-hold` | 高风险长期画像 | `PASS` / `HOLD` / Receipt |
| `technology-concentration-blocked` | 科技集中、聚合 breach | `BLOCKED` |
| `missing-lookthrough-blocked` | ETF 穿透缺失 | `BLOCKED` |
| `provider-partial-review` | 一条 Provider lineage 为 `PARTIAL` | `REVIEW_REQUIRED` |
| `provider-conflict-error` | 两条 lineage 冲突、完整性拒绝 | 安全 `ERROR` |
| `owner-mismatch-rejected` | 跨 owner 请求 | 合约前拒绝 |
| `naive-time-rejected` | 无时区问卷 | 合约前拒绝 |

案例只引用既有 advisor manifest/template，并在临时目录复制 Provider fixture 做最小
变体。运行时的 profile scorer、Portfolio exposure、risk/compliance gate、research
bridge、Recommendation 和 Receipt 都来自已有模块；评测器不包含金融公式。

## Running

在仓库根目录执行：

```powershell
python -m tools.evaluate_mvp
python -m tools.evaluate_mvp --json
python -m tools.evaluate_mvp --repeat 3 --json
python -m tools.evaluate_mvp --case balanced-hold --case conservative-reduce
```

`--repeat` 只比较语义 fingerprint，耗时允许变化。`--json` 输出
`mvp-evaluation-report.v1`，其中只有 case 摘要、状态、action 集合、trace 计数、错误
分类和 P50/P95 本地耗时；不会输出 raw exception、原始粘贴内容、凭据或外部 URL。

## Metrics boundary

- `case_pass_rate`：实际结果满足 case 预期的比例；
- `profile_alignment_rate`：status 与 action 集合同时匹配的比例；
- `risk_detection_coverage`：预期 REVIEW/BLOCKED 的 case 被保持为对应降级状态的比例；
- `compliance_block_coverage`：预期 BLOCKED case 保持阻断的比例；
- `evidence_coverage`：预期 Receipt 的 case 同时拥有 Evidence、Fact、Finding 的比例；
- `semantic_replay_equality`：重复运行时语义 fingerprint 不变的比例；
- `latency_p50_ms` / `latency_p95_ms`：当前机器上进程内 fixture 运行耗时。

这些数值是回归和架构证据，不是 Fact Accuracy、Hallucination Rate、投资收益、回测
胜率或真实部署 SLA。真实 SkillHub/Wencai 鉴权、配额、数据新鲜度和评委环境仍需官方
输入后另行评估。
