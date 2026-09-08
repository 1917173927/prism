# 本地部署与数据维护

## 第1章 运行边界

当前交付运行于本地回环地址，默认 SQLite 保存已确认画像、持仓、决策与上下文。远端 Git 仓库存放代码，不存放账户文件、数据库或供应商密钥。PostgreSQL、正式问财授权和券商接入尚未验收。

| 配置 | 默认 | 用途 | 验证边界 |
|---|---|---|---|
| `PRISM_DB_PATH` | `data/private/prism.sqlite3` | 本地持久化 | SQLite 回归与备份恢复 |
| `PRISM_AUTH_ACCOUNTS_FILE` | 未设置 | 启用 HTTP Basic 账户校验 | 本地回环；跨机器必须先配置 HTTPS |
| `HITHINK_FINANCE_API_KEY` | 未设置 | 扶摇服务端凭据 | 真实能力探测成功后可用 |
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
