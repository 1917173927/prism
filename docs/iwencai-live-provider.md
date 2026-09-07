# 问财 LIVE 数据接入说明

## 1. SkillHub CLI 与 LIVE 数据的边界

Iwencai SkillHub CLI 只负责安装和管理 Skill，不等于行情、财务或基金穿透接口。CLI 安装完成后，仍需确认具体 Skill 或官方 Provider 的运行协议、数据字段和权限。

当前仓库不会因为 CLI 已安装就自动开启 LIVE，也不会把未验证的 Skill 当作官方数据源。

## 2. 服务端配置

LIVE 只读取服务端环境变量，浏览器不会接收凭据：

```bash
export WENCAI_SKILLHUB_API_KEY="<server-side-key>"
export WENCAI_SKILLHUB_BASE_URL="<verified-official-base-url>"
export WENCAI_SKILLHUB_CONTRACT_VERIFIED="true"
```

`WENCAI_SKILLHUB_CONTRACT_VERIFIED=true` 是人工确认闸门，表示当前 Base URL、鉴权方式和响应字段已经根据官方文档或脱敏测试响应完成映射。缺少该变量时，系统保持 MOCK，LIVE 切换返回 409。

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

Provider 只接受明确的规范字段，例如 `price_cny`、`observed_at`、`sector` 和基金 `top_holdings`。当前没有注入真实官方凭据和已确认的官方响应契约，因此默认不能宣称 LIVE 已接通。
