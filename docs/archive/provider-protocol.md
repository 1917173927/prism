# Provider Protocol

本文档定义 Prism 接入金融数据提供者（Provider）的基础协议与四态结果语义。可执行实现位于 [`app/providers/`](../app/providers/)。

## 目标与原则

1. **确定性与可审计**：每次请求分离“调用关联标识 (`request_id`)”与“语义查询指纹 (`request_fingerprint`)”；
2. **四态语义隔离**：严格区分 `SUCCESS`、`PARTIAL`、`EMPTY` 与 `FAILED`，禁止相互伪装；
3. **零伪造与零默认**：失败不产生假 Evidence，缺失字段不转成 `0`，`0` 必须是真实观测数值；
4. **深度不可变与安全脱敏**：采用 `FrozenDict` 确保请求参数与记录深层不可变；禁止包含 `token`, `api_key`, `secret`, `password` 等敏感键（支持递归层级校验），诊断与日志自动递归脱敏；
5. **离线优先 (Fixture-First)**：在无真实凭据或外部网络时，通过严格校验的合成 Fixture 驱动全链路测试。

## 核心对象与接口

### 1. `ProviderRequest`

调用方发起数据查询的不可变契约：

- `request_id`: 单次调用的唯一跟踪 ID；
- `operation`: 明确操作类别（`MARKET_DATA`, `COMPANY_DATA`, `INDUSTRY_DATA`, `MACRO_DATA`, `FUND_DATA`, `SEARCH_NEWS`, `SEARCH_REPORTS`）；
- `subject`: 标的代码或主题（如基金代码、股票代码、宏观指标）；
- `as_of`: 可选基准时间（必须为带时区的 datetime）；
- `required_fields`: 任务完成必需字段元组；
- `parameters`: `FrozenDict` 不可变字典（递归禁止在任何嵌套层级出现敏感键）；
- `timeout_ms`: 毫秒级超时预算（默认 3000ms）。

### 2. `ProviderResult` 四态不变量

| Status | 记录数 (`records`) | 缺失字段与 Issue | 说明与约束 |
|---|---|---|---|
| `SUCCESS` | $\ge 1$ 条 | 无 missing_fields；无 issues | **逐记录验证**：每条记录必须包含全部 `required_fields` 且值非 None，可转为 `VERIFIED` Evidence |
| `PARTIAL` | $\ge 1$ 条 | 至少有 missing_fields 或 issue | 取得部分数据；`missing_fields` 必须为请求中定义且在记录中实际缺失的字段，只能转为带 `quality_note` 的 `PARTIAL` Evidence |
| `EMPTY` | 必须为 0 条 | 无错误 issue；必须有 `scope_description` | 查询成功且明确无数据，不生成 Evidence |
| `FAILED` | 必须为 0 条 | 至少 1 个 issue | 超时、网络、鉴权或解析失败，不生成 Evidence，不伪造零值 |

### 3. `FinancialProvider` Protocol

Provider 接口只暴露一个异步入口：

```python
class FinancialProvider(Protocol):
    @property
    def name(self) -> str:
        ...

    async def execute(self, request: ProviderRequest) -> ProviderResult:
        ...
```

### 4. 语义指纹 (`request_fingerprint`)

使用 Canonical JSON 对 `schema_version`、`operation`、`subject`、`as_of`、排序后的 `required_fields` 及规范化 `parameters` 进行 SHA-256 哈希，输出 64 位小写十六进制摘要。

指纹具备以下特性：
- 忽略参数键的声明顺序；
- 忽略非语义参数（`request_id` 与 `timeout_ms`）；
- 任何语义变更（指标、标的、时间、参数值）均会导致指纹变化。

### 5. 有界执行与安全诊断 (`execute_with_budget`)

异步执行包装器提供：
- 严格受 `request.timeout_ms` 约束的超时控制；
- 超时统一转换为 `FAILED / ProviderIssueCode.TIMEOUT`，标记 `retriable=True`；
- 任务取消转换为 `FAILED / ProviderIssueCode.CANCELLED`；
- 未知异常统一转换为 `FAILED / ProviderIssueCode.INTERNAL_ERROR`，且自动脱敏异常信息与诊断字典，防止泄漏敏感凭据与堆栈。

### 6. Evidence Normalization 与记录标识

纯函数 `normalize_result_to_evidence(result: ProviderResult) -> tuple[Evidence, ...]`：
- `SUCCESS` $\rightarrow$ 提取各字段为 `VERIFIED` Evidence，`quality_note=None`；
- `PARTIAL` $\rightarrow$ 提取各字段为 `PARTIAL` Evidence，附带真实缺失字段说明的 `quality_note`；
- `EMPTY` / `FAILED` $\rightarrow$ 返回空元组 `()`；
- 稳定生成包含记录标识和 request fingerprint 的 Evidence ID：`ev:{provider}:{source}:{record_identity}:{field}:{period}:{request_fingerprint}`；各组件进行无分隔符歧义的编码，同一来源下重复记录身份会被拒绝，确保多条记录与不同请求不会发生 ID 碰撞并满足 `DecisionTrace` 闭包校验。参与归一化的记录必须提供 `record_id` 或 `lineage_id`，不能退化为数组下标。

### 7. `FixtureFinancialProvider`

基于 `tests/fixtures/providers/` 目录下的纯合成 JSON 数据（如 `fund_data_success.json`, `fund_data_partial.json`, `fund_data_empty.json`, `fund_data_failed.json`）：
- 初始化时加载并严格校验模板 Request 与 Result（拒绝非法结构与不满足契约的模板）；
- 严格检查并拒绝重复语义指纹的 Fixture 文件；
- 纯内存命中，零网络依赖；
- 自动将返回结果的 `request_id` 与 `request_fingerprint` 绑定至当前请求；
- 未匹配指纹时返回结构化 `FAILED / UNSUPPORTED_OPERATION`。

## 当前实现与后续边界

本协议已通过 100 并发隔离测试与四态契约验收。真实外部数据源（如同花顺问财 SkillHub、Tushare）将在获得比赛专用接口凭据及授权后，以实现 `FinancialProvider` 的适配器接入。
