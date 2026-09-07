# Provider Cache 与显式降级

Phase 30 为既有 `FinancialProvider` 增加一个可选的、fixture-first resilience
边界。默认 `execute_with_budget(provider, request)` 行为不变；需要启用时显式传入
`ProviderExecutionPolicy`：

```python
from app.providers import (
    InMemoryProviderCache,
    ProviderExecutionPolicy,
    execute_with_budget,
)

cache = InMemoryProviderCache(ttl_ms=30_000, stale_grace_ms=120_000)
policy = ProviderExecutionPolicy(cache=cache, fallback=secondary_provider)
result = await execute_with_budget(primary_provider, request, policy=policy)
```

## 两个正交维度

`ProviderResult.status` 仍然只有 `SUCCESS`、`PARTIAL`、`EMPTY`、`FAILED` 四态，描述
payload 本身；`ProviderResult.serving_mode` 描述它如何被送达：

| serving mode | 含义 | 是否写入缓存 | Evidence 资格 |
|---|---|---:|---|
| `DIRECT` | 主 Provider 本次直连 | SUCCESS/PARTIAL 才写入 | 按原四态 |
| `CACHE_FRESH` | 同一 provider+request fingerprint 的 fresh 命中 | 否 | 按原四态 |
| `FALLBACK_PROVIDER` | 主 Provider 失败后一次备用 Provider 成功 | 否 | provider/source 保留备用身份 |
| `CACHE_STALE_FALLBACK` | 主/备用均不可用，命中 stale grace 内缓存 | 否 | normalization 变为 `STALE`，不能通过 VERIFIED bridge |

`CACHE_FRESH` 和 `CACHE_STALE_FALLBACK` 必须带 `cache_age_ms`；其它模式不得带该
字段。缓存返回时只重绑定当前 `request_id`，fingerprint、records、retrieved_at 和
lineage 保持原值。这样相同语义请求不会因为 request ID 不同而重复回源，也不会因为
缓存命中而伪造新的取得时间。

## 安全边界

- key 是 `(provider.name, compute_request_fingerprint(request))`，不包含 request ID。
- ProviderRequest 中含 owner/profile/portfolio/questionnaire/context-memory/account/
  holding/position 等私人语义的请求直接 bypass；它们仍可执行，但不进公共 cache。
- ProviderResult 里含 owner/profile/portfolio/account 等私人语义或
  credential/API key/authorization/password/secret/token/cookie 等关键字的 payload
  不进入 cache；缓存不是秘密存储。
- 只有经过 `validate_result_for_request` 的 SUCCESS/PARTIAL 可写入；EMPTY/FAILED 永不
  写入。容量是线程安全 LRU，entry 到期后从内存删除，不持久化、不跨进程。
- 失败顺序是：fresh cache → primary → 一次 fallback → stale cache → FAILED。primary
  返回 EMPTY 时立即返回 EMPTY，不调用 fallback，以保留“范围内确实无结果”的语义。
- 所有 fallback 请求共享原始 timeout 总预算；没有预算就不会启动第二次调用。异常
  只映射成已有安全 ProviderIssue，不回显原始异常。

## 研究链路

`execute_research_run(..., policy=policy)` 会把 policy 传给每个并行节点，并只接受主
或备用 provider identity。节点结果新增 `provider`、`provider_serving_mode` 和
`provider_cache_age_ms` 安全字段。stale cache 会让节点成为 `PARTIAL`，其 Evidence
为 `STALE`，所以后续 cross-validation/evidence bridge 自动要求人工复核；备用源则
保留自己的 provider/source/lineage，可被审计和比较。

## 仍未实现

这是本地、有界的 provider resilience 骨架，不是实时 SkillHub 客户端。生产 Redis/
数据库缓存、跨进程一致性、Circuit Breaker、动态限流、重试策略、在线鉴权、云持久化
与完整 Evidence drill-down UI 继续留在后续阶段。
