# 问财 LIVE 数据接入说明

## 1. 项目级安装与 CLI 边界

Prism 不依赖当前用户目录中的 SkillHub CLI。九个官方 Skill 的 ID、版本、端点与下载包哈希登记在 `app/providers/iwencai_skills.json`，该文件随 Python wheel 安装；后端由 `WencaiSkillHubProvider` 直接调用官方 OpenAPI。

官方 Skill 包仅用于核对公开契约，项目不执行下载包中的脚本。系统不会因为浏览器已登录或 CLI 已安装就自动开启 LIVE，也不会把未验证的 Skill 当作官方数据源。

## 2. 凭据配置

Windows 桌面部署推荐调用 `PUT /api/v1/runtime/wencai-settings` 保存一次凭据。密钥进入 `data/private/prism-secrets.json` 的 DPAPI 密文槽 `provider:wencai`，不会写入 Git、SQLite 或 API 响应。应用热重载和服务重启后自动恢复。

保存后调用 `POST /api/v1/runtime/wencai-settings/test`。后端会对九个 Skill 各发起一次最小真实请求；全部返回 `SUCCESS`、`PARTIAL` 或 `EMPTY` 后才持久化 `contract_verified=true` 并开放问财 LIVE 能力。

容器或服务器也可继续使用环境变量：

LIVE 只读取服务端环境变量，浏览器不会接收凭据：

```bash
export IWENCAI_API_KEY="<server-side-key>"
export IWENCAI_BASE_URL="https://openapi.iwencai.com"
export WENCAI_SKILLHUB_CONTRACT_VERIFIED="true"
```

`IWENCAI_*` 与原有 `WENCAI_SKILLHUB_*` 配置均可使用。环境部署中的 `WENCAI_SKILLHUB_CONTRACT_VERIFIED=true` 是运维确认闸门；桌面部署由真实探测自动管理该状态。

结构化查询使用 `POST /v1/query2data`；公告、新闻和研报使用 `POST /v1/comprehensive/search`。请求按 ProviderOperation 自动选择项目清单中的 Skill ID，并要求响应明确返回 `status_code=0`。所有请求使用服务端 Bearer 鉴权，并附带 Skill、Plugin 占位头及 64 位随机追踪 ID。

| 能力 | 项目内 Skill ID | ProviderOperation |
| --- | --- | --- |
| 公告 / 新闻 | `announcement-search` / `news-search` | `SEARCH_NEWS`，由 `channel` 区分 |
| 研报 | `report-search` | `SEARCH_REPORTS` |
| 行情 / 财务 / 行业 / 宏观 | `hithink-market-query` / `hithink-finance-query` / `hithink-industry-query` / `hithink-macro-query` | 对应四类结构化操作 |
| 基金 / 可转债 | `hithink-fund-query` / `hithink-cb-selector` | `FUND_DATA` / `CONVERTIBLE_BOND_DATA` |

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

2026-09-15 已用当前官方凭据完成九个 Skill 的真实最小请求，九项均为 HTTP 200 且 Provider `SUCCESS`；LIVE 聊天的公告查询完成 LLM 工具调用、问财真实返回、SSE 输出闭环。该结果证明当前凭据和调用契约可用，不等于正式配额、留存、展示授权或长期 SLA 已验收。
