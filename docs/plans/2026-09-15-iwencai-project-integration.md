# 问财 SkillHub 项目级真实接入计划

## 目标

将问财 SkillHub 的官方接口契约、Skill 路由与凭据配置纳入 Prism 项目，使后端无需依赖开发机全局 CLI 即可调用真实服务，并以真实探测结果裁决 LIVE 可用状态。

## 已确认约束

- 官方入口为 `https://openapi.iwencai.com`。
- 综合搜索使用 `/v1/comprehensive/search`，结构化查询使用 `/v1/query2data`。
- 每次请求必须带 Bearer 凭据、Skill ID、Skill Version、Plugin 占位头与随机 Trace ID。
- LIVE 失败不得回退 Fixture/Mock。
- 凭据不得写入 Git；Windows 本地部署复用现有 DPAPI 保护存储，保存一次后跨重启生效。

## 路径比较与选择

| 路径 | 优点 | 缺点 | 结论 |
| --- | --- | --- | --- |
| 安装官方 CLI 到当前用户目录 | 快速验证单机 Agent 调用 | 部署依赖全局目录，项目后端不可直接复用 | 仅作为官方契约来源，不作为运行时依赖 |
| 项目内置契约清单与 HTTP 适配器 | 可测试、可打包、可部署，后端直接调用 | 需要维护明确的 Skill 路由 | 采用 |

## 实施范围

1. 增加项目内 `iwencai_skills.json`，登记九个官方 Skill 的版本、端点和 ProviderOperation 映射。
2. 修正并扩展 `WencaiSkillHubProvider`，按操作选择 Skill，严格验证官方响应状态。
3. 增加问财配置保存、读取和真实探测 API，复用 DPAPI 密钥存储。
4. RuntimeModeController 以项目中实际 Provider 的配置与探测结果判断问财能力，不再只认进程环境变量。
5. 扩展聊天语义搜索的新闻、公告、研报频道参数，保持默认公告兼容。
6. 运行单元、集成及真实九 Skill 探测；完成后由独立子代理复审。

## 验证标准

- 构建产物包含九 Skill 清单。
- 凭据保存后响应不回显明文，应用重建后仍可读取。
- 九个 Skill 的真实最小请求均返回可判定的官方响应；失败须保留明确错误，不得伪造成功。
- 聊天路径在 LIVE 下能够实际调用综合搜索。
- 相关测试及全量测试通过，复审无未处理的高优先级问题。
