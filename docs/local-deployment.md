# 本地部署与数据维护

## 第1章 运行边界

当前交付运行于本地回环地址，默认 SQLite 保存已确认画像、持仓、决策与上下文，可显式选择 PostgreSQL 后端。远端 Git 仓库存放代码，不存放账户文件、数据库或供应商密钥。问财 OpenAPI 已完成本地真实查询 smoke test；券商同步不在当前范围内。

| 配置 | 默认 | 用途 | 验证边界 |
|---|---|---|---|
| `PRISM_DB_PATH` | `data/private/prism.sqlite3` | 本地持久化 | SQLite 回归与备份恢复 |
| `PRISM_DATABASE_URL` | 未设置 | PostgreSQL 连接配置，设置后优先于 SQLite | 真实 PostgreSQL 17.11 隔离回归；不自动搬迁旧数据 |
| `PRISM_AUTH_ACCOUNTS_FILE` | 未设置 | 启用 HTTP Basic 账户校验 | 本地回环；跨机器必须先配置 HTTPS |
| `HITHINK_FINANCE_API_KEY` | 未设置 | 扶摇服务端凭据 | 真实能力探测成功后可用 |
| `IWENCAI_API_KEY` / `IWENCAI_BASE_URL` | 未设置 / `https://openapi.iwencai.com` | 问财 OpenAPI 服务端凭据与地址 | 配置 Skill 版本头并完成真实查询后可用 |
| `WENCAI_SKILLHUB_CONTRACT_VERIFIED` | `false` | 问财响应契约人工确认闸门 | `true` 后允许问财 LIVE 能力 |
| `/api/health` | 无认证 | 进程和数据模式健康检查 | 不等于供应商可用性承诺 |

未设置认证文件时为开发模式，`X-Owner-ID` 只是数据命名空间，不构成访问保护。认证开启后所有页面及业务接口需要认证，服务端将身份绑定到固定 owner；普通账户无权修改全局模型和数据模式。认证文件无效时启动失败，不自动回退到开发模式。

## 第2章 启动与账户管理

在仓库根目录执行。密码通过交互输入，不放进命令历史；生成文件只保存随机盐和 scrypt 摘要。已有持仓属于 `demo-owner` 时，使用该 owner 可继续读取已有数据。运行前由使用者自行设置密码，不提供公共默认密码。

```powershell
.venv/Scripts/python.exe tools/local_account.py --username local-admin --owner demo-owner --admin
$env:PRISM_AUTH_ACCOUNTS_FILE = (Resolve-Path data/private/accounts.json).Path
.venv/Scripts/python.exe -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

普通账户省略 `--admin`，独立数据空间指定不同 `--owner`。明确更换已有密码时加入 `--replace`，变更后重启服务。浏览器通过标准认证提示框登录。HTTP Basic 没有应用级会话退出或过期机制；此实现不替代公网身份提供方、限流和安全网关。账户文件由本机操作系统权限保护，不应放入共享目录。

认证模式下，聊天历史、浏览器模型密钥和界面画像备注只保留在当前页面内存，刷新后清空；已确认风险问卷及持仓仍从服务端恢复。这样避免同一浏览器切换账户后从本地缓存读到另一账户的聊天或密钥。未启用认证的开发模式保留原缓存行为。

`GET /api/v1/auth/context` 返回当前身份及管理员标志；`GET /api/v1/access-audit?limit=100` 返回该 owner 的最近访问。审计只记录 owner、方法、路由模板、状态码和时间，不保存请求正文、密码或授权头。本地审计可被本机文件管理员修改，尚不具备独立审计服务的防篡改保证。

## 第3章 备份与恢复

工具使用 SQLite 在线备份接口读取已提交数据，包括 WAL 中的数据；输出必须是尚不存在的路径，并执行完整性校验。以下为示例路径，每次备份使用新文件名。

```powershell
.venv/Scripts/python.exe tools/database_backup.py backup --source data/private/prism.sqlite3 --destination data/private/backups/prism-backup.sqlite3
.venv/Scripts/python.exe tools/database_backup.py restore --source data/private/backups/prism-backup.sqlite3 --destination data/private/prism-restored.sqlite3
```

恢复后停止当前服务，将 `PRISM_DB_PATH` 指向恢复的新文件再启动；原库保留，可回退。账户文件和供应商环境变量需单独以安全方式备份，此工具不复制凭据。不要将备份提交到 Git。

## 第4章 真实 HTTP 观测

以下命令通过 TCP/HTTP 请求已经运行的服务，不使用进程内 ASGI。工具只执行 GET；选择路由决定测量范围。认证接口可通过临时环境变量 PRISM_LOAD_USERNAME、PRISM_LOAD_PASSWORD 配置，不把密码放入 URL 或命令参数，使用后清除环境变量。

```powershell
.venv/Scripts/python.exe tools/http_load_test.py --url http://127.0.0.1:8000/api/v1/advisor/portfolio/current --owner demo-owner --concurrency 100 --requests 100
```

输出包含时间窗口、P50/P95/P99、HTTP 状态和失败类型。单次全部成功只代表该样本；输出始终标记 sla_verified=false，不能作为长期 99.9% 可用性或扶摇上游性能证明。对外部服务压测前需明确其配额和许可。

## 第5章 工作流与历史记忆

开发者视图的研究轨道提供 AntV X6 工作流画布。读取后可拖动节点、通过前置/后续节点选择框添加或删除依赖；保存新版本时校验固定节点目录、环路及超时预算。流水线卡片按拓扑层显示可并行节点和依赖，可切换高级画布编辑。运行按钮执行服务端已保存的指定版本；若本地存在未保存修改，需先保存或重新读取，避免旧结果显示在新依赖图上。当前只连接既有八节点合成研究执行器，标记 MOCK；不支持任意代码节点，也不执行交易。定义按 owner 追加版本，运行状态返回当前页面，尚无独立运行历史表。

仓库已包含构建后的脚本及第三方许可，直接启动 Python 服务即可使用。修改画布源码时，使用 Node.js 20 或以上版本重新构建：

```powershell
npm ci
npm run build:workflow
```

上下文记忆中的检索按钮查询当前 owner 最近 100 条显式保存记录，结果附来源、保存时间、摘要哈希和匹配字段。配置服务端模型时，只发送查询和有限描述摘要，不发送持仓数量；未配置模型或模型失败时标注有限关键词匹配。所有结果为 HISTORICAL_ONLY，不自动恢复画像、持仓或决策输入。模型相关性排序不代表事实仍然有效；使用历史信息前应核对当前版本和行情。

## 第6章 可选 PostgreSQL

安装可选驱动后，以安全环境配置提供专用数据库 DSN；不要把含密码的 DSN 写入 Git、URL 或日志。本轮没有切换现有用户 SQLite 数据库。

```powershell
.venv/Scripts/python.exe -m pip install -e ".[dev,web,postgres]"
# 由本机安全配置注入 PRISM_DATABASE_URL 后启动服务
.venv/Scripts/python.exe -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

`create_app(database_url=...)` 或入口的 `PRISM_DATABASE_URL` 启用 PostgreSQL；显式配置无效时启动失败，不退回空 SQLite。数据库或专用 schema 必须由使用者预先准备，角色需要该 schema 的建表和读写权限。不要指定已有其他应用的业务 schema。

后端复用现有 owner 与内容校验，按编号执行 SQL 表结构迁移，DDL 与迁移登记在同一事务内。写事务使用数据库范围 advisory lock 保留 CAS 语义，锁等待上限 5 秒、语句上限 15 秒；当前采用单连接和串行写策略，不宣称高并发连接池性能。构造失败会关闭连接，事务失败回滚。

切换数据库不会自动把 SQLite 历史数据复制到 PostgreSQL。现有 SQLite 原库保留；停止服务、移除 PostgreSQL 配置并重新指向原 SQLite 可恢复原本地环境，但 PostgreSQL 期间新增的记录不会反向同步。数据库结构目前只支持向前迁移，不提供破坏性降级命令。第3章备份工具仅支持 SQLite；PostgreSQL 备份需使用其原生备份工具并单独验收。

真实数据库集成测试仅在显式提供测试 DSN 时运行；每项测试在专用测试数据库中新建随机 schema，结束删除该测试 schema。不要提供生产数据库或真实账户数据库。

```powershell
# 预先通过安全环境配置 PRISM_TEST_POSTGRES_DSN
.venv/Scripts/python.exe -m pytest tests/integration/test_postgres_store.py
```

未提供测试 DSN 时这些测试明确跳过，不使用 SQLite 或 mock 代替 PostgreSQL。

## 第7章 会话黑板与结构化核验

黑板显示已锁定的画像、持仓及来源。更新前提先展示当前服务端事实，确认请求携带预览指纹与预期版本；预览后事实或版本变化会返回 409，要求重新读取。修订进入 session_truth 追加记录，不修改持仓、问卷或重复复制历史 ContextMemory。

`POST /api/v1/advisor/session-truth/check` 必须指定已锁定版本，可提交 assertions（白名单字段、字符串数值、持仓 position_id）或 actions（BUY/SELL/HOLD、asset_id）。当前仅支持明确的 BUY 禁投校验；其他动作不冒充已完成交易审核。

| 检查 | 判定依据 | 容差 | 边界 |
|---|---|---|---|
| 数量 | 锁定持仓数量 | 0 | 精确一致 |
| 金额 | 锁定持仓市值 | 0.01 货币单位 | 不代表当前报价 |
| 画像数值 | 风险分数/回撤容忍 | 0.01 分/百分点 | 不调用模型计算 |
| 买入禁投 | 明确资产、类别或行业排除 | 精确匹配 | 无法解释的约束 UNVERIFIED |

结果附事实来源、版本及指纹。HALLUCINATED_DATA 在此表示结构化断言与已锁定事实不符或引用未知事实，不是对整段自然语言真实性的通用判定。本页流式分析中断记录最多保留20条，可点击定位对应消息；刷新或账户切换后清空，不将其冒充持久化审计。
