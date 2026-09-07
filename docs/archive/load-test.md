# 早期负载测试工具

`tools.load_test` 是 Phase 19 的开发期基线工具，用来测量 fixture-first API 在本地
进程内并发下的行为，同时验证 owner 隔离、响应契约和 DecisionEvent 副作用。它不是
生产压测器，也不会连接同花顺 SkillHub、Tushare、真实账户或公网。

## 用法

在仓库根目录执行：

```powershell
python -m tools.load_test --scenario template --concurrency 100 --json
python -m tools.load_test --scenario research --concurrency 100 --json
python -m tools.load_test --scenario advisor --concurrency 100 --json
```

参数：

- `--scenario`：`template`、`research` 或 `advisor`；
- `--concurrency`：并行虚拟 owner 数，范围 1–1000，默认 100；
- `--requests-per-user`：每个 owner 顺序执行的操作数，范围 1–1000，默认 1；
- `--timeout-seconds`：单个 HTTP 请求超时，范围大于 0 且不超过 300 秒；
- `--json`：输出可被 CI/脚本读取的 `load-test-report.v1` JSON，否则输出简短文本。

`advisor` 操作先通过既有 query-template API 取得 owner-bound 模板，再提交
`advisor-query.v1`，所以一次逻辑操作包含两次 HTTP 请求；其 operation latency 是
这两步的端到端耗时，`total_requests` 则记录真实 HTTP 请求数。`template` 只读模板，
`research` 运行固定矩阵请求。每个 owner/query/request ID 都由参数确定性生成。

## 报告字段

报告包含：

- `logical_operations`、`total_requests`、`completed`、`failed` 和总耗时；
- 操作耗时的 `min_ms`、`p50_ms`、`p95_ms`、`p99_ms`、`max_ms`；空样本以 `count: 0`
  和空数值表示，不用 0 冒充延迟；
- HTTP `status_counts`、安全 `error_counts`、`owner_mismatch_count`；
- `store_rows_before/after`。Template/Research 预期不写入事件，Advisor 预期每个
  逻辑操作写入一条 owner-scoped DecisionEvent；不符预期会计入
  `STORE_SIDE_EFFECT` 并使运行失败。

失败只保留稳定类别，例如 `TIMEOUT`、`TRANSPORT_ERROR`、`INVALID_JSON`、
`API_<ERROR_CODE>`、`CONTRACT_ERROR`、`OWNER_MISMATCH` 或 `PIPELINE_NOT_READY`，
不输出原始异常、响应正文、凭据或私有持仓。HTTP 非 2xx、owner/ID 不闭合、Research
非 READY、Advisor 非 PASS 和敏感响应均算失败。

## 测量解释

默认 transport 是 `httpx.ASGITransport`，请求直接进入同一 Python 进程的 FastAPI
app factory；它适合回归并发、契约和隔离，不包含真实 TCP、反向代理、TLS、连接池、
进程/容器调度、外部 Provider 延迟或生产数据库。因此报告的毫秒数只能回答“当前
合成 fixture 在这台机器上的本地基线”，不能回答赛题的真实 `≥100` 用户、`≤3 秒`
投顾响应或 `≥99.9%` 可用性是否达标。

运行结果应保留原始 JSON 和运行环境，比较 P50/P95/P99、错误类别及副作用，而不是
只比较平均值。若机器、Python、fixture 或 transport 改变，必须重新记录，不能调样本
或填补缺失值来制造指标。

## 复用边界与后续工作

工具复用现有 `create_app`、owner dependency、Advisor/Research contracts 和
`SQLiteDecisionEventStore`，不复制 Provider、Risk、Gate、Recommendation 或
Research 状态机。Provider cache、connection pooling、retry/circuit breaker、
分布式 tracing、生产持久化、认证、云压测和真实外部 SLA 仍是后续获得授权与部署
环境后单独规划的工作；本工具不会把本地基线升级为生产承诺。
