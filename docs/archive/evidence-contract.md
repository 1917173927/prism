# Evidence Contract

本文档定义 Prism 所有 Provider、研究、组合、风险、合规和展示模块共享的首版事实契约。可执行实现位于 [`app/contracts/evidence.py`](../app/contracts/evidence.py)。

## 目标

每条可行动建议必须形成闭合链：

```text
Recommendation
      -> Finding
      -> Fact
      -> Evidence
```

“附一个 URL”不等于证据链。系统必须知道来源记录的字段、值、期间、获取时间、质量，以及该事实如何经过确定性规则或结构化方法形成结论。

## 对象职责

### Evidence

Provider 的单个标准化观测，至少包含：

- 稳定 `evidence_id`；
- `provider`、`source` 与原字段 `field`；
- 值、单位和期间；
- `observed_at` 与带时区的 `retrieved_at`；
- 质量状态、质量说明和可选 lineage。

Evidence 质量状态：

| Status | 含义 | 可直接支持 `PASSED` 建议 |
|---|---|:---:|
| `VERIFIED` | 值存在且通过当前校验 | ✓ |
| `STALE` | 值可读但超出新鲜度窗口 | |
| `PARTIAL` | 返回不完整或缺少必要字段 | |
| `CONFLICTING` | 与独立来源存在尚未解决的口径/数值冲突 | |
| `INVALID` | 解析、范围、口径或完整性校验失败 | |

非 `VERIFIED` Evidence 必须携带 `quality_note`，不能只给一个状态码。

### Fact

Fact 是系统允许研究节点消费的标准化金融事实，而不是 LLM 推断。状态语义：

| Status | 值 | Evidence | Reason |
|---|---|---|---|
| `VERIFIED` | 必须存在 | 至少一个 | 不允许 |
| `UNAVAILABLE` | 必须为空 | 可选 | 必须存在 |
| `INVALID` | 必须为空 | 可选 | 必须存在 |
| `NOT_APPLICABLE` | 必须为空 | 可选 | 必须存在 |

因此，Provider 超时不能写成 `value=0`；零必须是具有有效证据的真实数值。

### Finding

Finding 是一个或多个 Fact 经过明确方法得到的判断。它必须包含 Fact 引用、严重程度、置信度和方法说明。Agent 语言不能绕过 Fact Registry 直接创造金融事实。

### Recommendation

Recommendation 是受画像与约束影响的行动区间，不是无条件买卖命令。它必须引用 Finding、给出失效条件，并携带独立合规状态：

- `PASSED`：引用链全部为 `VERIFIED` Fact 和 `VERIFIED` Evidence；
- `REVIEW_REQUIRED`：事实已核对，但存在陈旧、部分或冲突证据，需要人确认；
- `BLOCKED`：关键 Fact 缺失/无效或合规条件不满足，只能解释阻断原因。

## 闭包校验

`DecisionTrace` 在对象创建时拒绝：

- 重复 ID；
- Finding、Fact 或 Evidence 的悬空引用；
- VERIFIED Fact 与 Evidence 值/期间不一致；
- 可行动建议引用非 VERIFIED Fact；
- `PASSED` 建议引用非 VERIFIED Evidence。

这是一项系统边界，不是仅供 UI 展示的约定。API、存储和异步任务在接收/提交对象时都必须重新校验。

## Cross Validation 边界

首版契约只保存 `lineage_id`，用于识别多个表面来源是否来自同一上游记录。后续 Cross Validation Engine 负责：

- 区分真正独立来源与重复转载；
- 对齐时间和财务口径；
- 把支持、反对与尚未解决的冲突结构化；
- 决定 Fact 是 VERIFIED、INVALID，还是只能进入 REVIEW_REQUIRED/BLOCKED 路径。

不得以 Agent 数量投票代替这些检查。

## 版本与迁移

进入持久化层前将增加 `schema_version`、内容哈希和迁移策略。当前 `0.1.0` 契约只保证本仓库内的代码级兼容；在数据库迁移方案落地前不承诺外部 API 稳定性。
