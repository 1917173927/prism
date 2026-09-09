# 问财 LIVE 数据接入说明

## 1. SkillHub CLI 与 LIVE 数据的边界

Iwencai SkillHub CLI 只负责安装和管理 Skill，不等于行情、财务或基金穿透接口。CLI 安装完成后，仍需确认具体 Skill 或官方 Provider 的运行协议、数据字段和权限。

当前仓库不会因为 CLI 已安装就自动开启 LIVE，也不会把未验证的 Skill 当作官方数据源。

## 2. 服务端配置

LIVE 只读取服务端环境变量，浏览器不会接收凭据：

```bash
export IWENCAI_API_KEY="<server-side-key>"
export IWENCAI_BASE_URL="https://openapi.iwencai.com"
export WENCAI_SKILLHUB_CONTRACT_VERIFIED="true"
export WENCAI_SKILL_ID="prism-investment-agent"
export WENCAI_SKILL_VERSION="1.0.0"
```

`IWENCAI_*` 与原有 `WENCAI_SKILLHUB_*` 配置均可使用，前者优先用于问财 OpenAPI。`WENCAI_SKILLHUB_CONTRACT_VERIFIED=true` 是人工确认闸门，表示当前 Base URL、鉴权方式和响应字段已经完成映射。缺少该变量时，系统保持 MOCK，LIVE 切换返回 409。

问财 OpenAPI 查询使用 `POST /v1/query2data`；新闻和研报使用 `POST /v1/comprehensive/search`。请求使用服务端 Bearer 鉴权，并附带 Skill 调用标识和 64 位追踪 ID。浏览器不会接收凭据。

## 3. LIVE 刷新流程

```text
PortfolioImportBundle
    -> POST /api/v1/advisor/portfolio/refresh
    -> WencaiSkillHubProvider
    -> strict field validation
    -> refreshed PortfolioImportBundle
    -> portfolio health deterministic calculation
```

刷新失败、字段缺失、报告期缺失或基金穿透不完整时，接口返回 `REVIEW_REQUIRED`，不返回旧数据作为最新结果，也不静默回退到 MOCK。

## 4. 当前验证边界

Provider 将问财 `datas`/`data` 响应保留为原始结构化记录，并执行字段存在性校验。当前已使用服务端配置完成真实问财查询 smoke test（HTTP 200、`status_code=0`、5 条结果）；配额、留存、展示授权和长期 SLA 仍需单独确认。
