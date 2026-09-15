# 本地部署与数据维护

## 第1章 运行边界

当前交付运行于本地回环地址，默认 SQLite 保存已确认画像、持仓、决策与上下文，可显式选择 PostgreSQL 后端。远端 Git 仓库存放代码，不存放账户文件、数据库或供应商密钥。问财 OpenAPI 已完成本地真实查询 smoke test；券商同步不在当前范围内。

| 配置 | 默认 | 用途 | 验证边界 |
|---|---|---|---|
| `PRISM_DB_PATH` | `data/private/prism.sqlite3` | 本地持久化 | SQLite 回归与备份恢复 |
| `PRISM_DATABASE_URL` | 未设置 | PostgreSQL 连接配置，设置后优先于 SQLite | 真实 PostgreSQL 17.11 隔离回归；不自动搬迁旧数据 |
| `PRISM_SECRET_STORE_PATH` | `data/private/prism-secrets.json` | Windows DPAPI 保护的本地凭据文件 | 文件只保存密文；必须由同一 Windows 账户运行 Prism 才能解密 |
| `PRISM_AUTH_ACCOUNTS_FILE` | 未设置 | 一次性兼容导入旧 JSON 账户 | 新账户及会话均写入当前数据库 |
| `PRISM_DEV_NO_AUTH` | `false` | 显式开启无认证开发演示 | 仅本机开发；正式或共享环境禁止启用 |
| `HITHINK_FINANCE_API_KEY` | 未设置 | 扶摇服务端凭据 | 真实能力探测成功后可用 |
| `IWENCAI_API_KEY` / `IWENCAI_BASE_URL` | 未设置 / `https://openapi.iwencai.com` | 问财 OpenAPI 服务端凭据与地址 | 配置 Skill 版本头并完成真实查询后可用 |
| `WENCAI_SKILLHUB_CONTRACT_VERIFIED` | `false` | 问财响应契约人工确认闸门 | `true` 后允许问财 LIVE 能力 |
| `/api/health` | 无认证 | 进程和数据模式健康检查 | 不等于供应商可用性承诺 |

正常启动默认启用本地账户。未登录的页面导航重定向至 Prism 登录页，API 返回 JSON 401；服务端会话 Cookie 设置 `HttpOnly` 与 `SameSite=Lax`，HTTPS 下同时设置 `Secure`。会话最长 24 小时、连续空闲 2 小时失效；退出撤销当前会话，修改密码撤销该账户全部会话。只有显式设置 `PRISM_DEV_NO_AUTH=true` 才进入无认证开发演示，此时 `X-Owner-ID` 仅为数据命名空间，不构成访问保护。

## 第2章 启动与账户管理

在仓库根目录执行。首次启动可直接在登录页注册普通账户；owner ID 由服务端生成，新账户从空持仓、空画像和空聊天开始。管理员只能通过本地命令创建。密码通过交互输入，不放进命令历史；数据库只保存随机盐和 scrypt 摘要，不保存明文密码。

```powershell
.venv/Scripts/python.exe tools/local_account.py --username local-admin --owner demo-owner --admin
.venv/Scripts/python.exe -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

本地管理命令与服务入口使用相同的数据库选择规则：存在 `PRISM_DATABASE_URL` 时写入 PostgreSQL；否则使用显式 `--database`，再否则写入 `PRISM_DB_PATH` 或默认 SQLite 文件。为避免误写，设置 `PRISM_DATABASE_URL` 时禁止同时传入 `--database`。普通账户可在页面注册；命令中的 `--admin` 仅用于创建管理员。明确轮换现有密码时增加 `--replace`，其 owner 和角色必须保持一致，且该账户全部会话立即撤销。`PRISM_AUTH_ACCOUNTS_FILE` 仅保留旧 JSON 账户兼容导入和旧 Basic 客户端兼容，不再作为浏览器登录机制。此本地账户体系不替代公网身份提供方、速率限制和安全网关。

认证模式下，持仓、画像、聊天历史、偏好、工作流、审计记录和个人模型配置均按认证 owner 隔离。切换账户或退出时，页面中止未完成请求并清理当前账户的临时状态。Windows 本地运行时，模型密钥通过“更多 → 模型设置”填写，由当前 Windows 账户的 DPAPI 加密并按 owner 保存到 `PRISM_SECRET_STORE_PATH`；服务重启后继续生效，浏览器和接口不缓存或回读明文密钥。无认证开发演示仅使用一个本机密钥槽，不把可由调用者填写的 owner 标签误作身份边界。留空保存会删除当前作用域的密钥并恢复服务端默认。服务端默认模型继续由 `PRISM_LLM_API_KEY`、`DEEPSEEK_API_KEY` 等环境配置提供。在非 Windows 部署中，只有部署环境的 Secret/环境变量能够持久化；页面填写的个人密钥仅在当前服务进程内有效，不会明文落盘。

模拟首次使用：运行 `.venv\Scripts\python.exe tools/dev_preview.py --fresh --port 8874`。该命令是显式无认证开发入口，会设置 `PRISM_DEV_NO_AUTH=true`，在系统临时目录创建独立 SQLite，且不清空原数据库。正式账户模式拒绝 Mock/Fixture 业务结果；开发预览中的模拟回复和数据始终保留演示标识。

本地可在仓库根目录创建被 Git 忽略的 `.env`，启动脚本和 `tools/dev_preview.py` 会将其中的服务端变量注入当前进程；直接运行 Uvicorn 时需先在当前 shell 设置同名环境变量。供应商密钥不进入前端、数据库或 Git。

Markdown 资源已随仓库提供，正常启动无需 Node。修改 `app/api/static/markdown.src.js` 后运行 `npm ci`、`npm run build:markdown` 重新生成本地脚本。

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

## 第8章 跨市场大盘行情

“大盘鉴别”固定注册国内、港股和美股各4个指数。国内指数可复用已配置的同花顺金融数据服务；港美股原型默认读取无需账号或 API Key 的 Yahoo Finance 公开 Chart 接口。港股指数在 Yahoo 无数据或历史不足时，备用读取 ET Net 公开交互图中的指数 OHLCV；两者均为非正式公开来源，可能延迟、限流或中断，不使用 ETF、国内指数或演示价格替代。恒生综合指数使用 ET Net 代码 `HSC`，备用源不可用时才显示 `UNAVAILABLE`。

美国10年期国债收益率、Brent原油近月和COMEX黄金期货默认使用 Yahoo 代码 `^TNX`、`BZ=F`、`GC=F`，可通过 `YAHOO_US10Y_SYMBOL`、`YAHOO_BRENT_SYMBOL`、`YAHOO_GOLD_SYMBOL` 覆盖。任一因子不可用时仅该卡片降级，不阻断指数K线、量能和技术指标。国内及港股相关性只使用严格早于本地收盘日期的因子观测，避免引入随后才产生的美国市场数据；相关性不代表因果关系。

Lightweight Charts 5.2.1及Apache-2.0许可已随静态资源发布，不依赖运行时CDN。修改图表交互后应至少执行：

```powershell
node --check app/api/static/app.js
.venv/Scripts/python.exe -m pytest tests/unit/test_market_analysis.py tests/unit/test_yahoo_finance_provider.py tests/integration/test_prd_personalization_api.py
```
