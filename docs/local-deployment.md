# 本地部署教程

## 第1章 准备环境

Windows 电脑需要安装 Git 和 64 位 Python 3.11 或 3.12。下载 Python 时勾选将 Python 加入 PATH。

## 第2章 下载项目

打开 PowerShell，执行：

```powershell
git clone https://github.com/daoyezongzi/prism.git
cd prism
```

## 第3章 启动 Windows 版本

在项目目录执行：

```powershell
.\start.bat
```

首次启动会自动创建 Python 环境并安装 Prism 运行需要的组件。安装时间取决于网络速度。启动后，浏览器会自动打开 Prism。

如果浏览器没有打开，请访问 <http://127.0.0.1:8000/>。这个地址只能在运行 Prism 的电脑上使用。访问 <http://127.0.0.1:8000/api/health> 可以查看服务状态。

## 第4章 创建账户并进入工作台

在登录页面选择“注册”，填写用户名和密码。用户名至少 3 个字符，密码至少 12 个字符。注册完成后会自动进入工作台。

## 第5章 停止与再次启动

要停止 Prism，请回到启动程序的窗口并按 `Ctrl+C`。下次使用时，打开项目目录，再次执行 `.\start.bat`。

## 第6章 macOS 启动方法

macOS 需要 Git、Python 3.11 或 3.12，以及 [`uv`](https://docs.astral.sh/uv/getting-started/installation/)。安装好 `uv` 后，在项目目录安装 Prism 运行依赖：

```bash
uv sync --extra dev --extra web
```

如果要用 `.env` 设置模型或数据服务，请先按第7章完成设置，再运行启动命令。也可以直接启动，登录后点击工作台顶部的“API 配置”设置模型。

```bash
./start_mac.sh
```

然后访问 <http://127.0.0.1:8000/>。按 `Ctrl+C` 停止服务。


## 第7章 配置 `.env`

`.env.example` 是配置样例。首次配置时，在项目目录复制一份并编辑新文件：

```powershell
Copy-Item .env.example .env
notepad .env
```

Windows 的 `start.bat` 会自动读取 `.env`。修改后请重新启动 Prism。文件里的每一项都写成 `名称=内容`；保留没有要改的项目原值或空值。`.env` 可能含有密钥，Git 已忽略此文件，请勿发送给他人或提交到 Git。

macOS 的启动脚本不会自动读取 `.env`。复制文件后，用文本编辑器填写并保存：

```bash
cp .env.example .env
open -e .env
```

保存后，在同一个终端窗口、启动 Prism 前运行：

```bash
set -a
source .env
set +a
```

首次安装时，先按第6章运行 `uv sync --extra dev --extra web`。然后在同一个终端运行 `./start_mac.sh`。修改 `.env` 后请先按 `Ctrl+C` 停止 Prism，再重新运行启动命令。以后每次打开新的终端窗口，都要先运行 `set -a`、`source .env`、`set +a`，再执行 `./start_mac.sh`。

### 一、模型服务

最简单的设置方法是启动后点击工作台顶部的“API 配置”，选择 DeepSeek、通义千问或 OpenAI，填写 API Key、Base URL 和服务商提供的模型名称，再点击“保存配置”。页面会自动测试连接。Windows 会用本机账户保护网页保存的密钥；macOS 的网页设置只在当前服务运行期间有效。

也可以在 `.env` 设置服务端默认模型：

| 变量 | 作用 | 默认值 | 一般设置方法 |
|---|---|---|---|
| `PRISM_LLM_API_KEY` | 模型服务的 API Key | 空 | 填入服务商提供的 Key |
| `PRISM_LLM_BASE_URL` | 模型服务地址 | `https://api.deepseek.com/v1` | 使用其他服务时填写它给出的 Base URL |
| `PRISM_LLM_MODEL` | 模型名称 | `deepseek-v4-flash` | 保留默认值，或填写账户可用的模型名称 |

使用通义千问或 OpenAI 时，请同时填写该服务的 API Key、Base URL 和模型名称。只填写 API Key 时，程序仍会采用默认 DeepSeek 地址和模型。项目也支持 `DEEPSEEK_API_KEY`、`OPENAI_API_KEY`、`DASHSCOPE_API_KEY`、`OPENAI_BASE_URL` 和 `OPENAI_MODEL` 这些兼容变量；新配置建议填写 `PRISM_LLM_` 开头的项目变量。模型 Key 只供语言模型使用；行情和证券资料需要各自的数据服务 Key。

### 二、其他配置

多数人只需配置自己已有的服务 Key。其他项目可以保留样例里的值；空白项目表示暂不设置。

| 变量 | 作用 | 默认值 | 一般设置方法 |
|---|---|---|---|
| `HITHINK_FINANCE_API_KEY` | 扶摇金融数据服务 Key | 空 | 要使用该服务的实时行情时填写 |
| `HITHINK_FINANCE_BASE_URL` | 扶摇服务地址 | `https://fuyao.aicubes.cn` | 通常保留默认值 |
| `IWENCAI_API_KEY` | 问财 OpenAPI Key | 空 | 要使用问财数据能力时填写 |
| `IWENCAI_BASE_URL` | 问财 OpenAPI 地址 | `https://openapi.iwencai.com` | 通常保留默认值 |
| `WENCAI_SKILLHUB_CONTRACT_VERIFIED` | 标记问财接口规则已完成确认 | `false` | 保持 `false`；完成真实接口检查后再按运维说明更改 |
| `YAHOO_US10Y_SYMBOL` | 美国十年期国债代码 | `^TNX` | 通常保留默认值，无需 Key |
| `YAHOO_BRENT_SYMBOL` | Brent 原油代码 | `BZ=F` | 通常保留默认值，无需 Key |
| `YAHOO_GOLD_SYMBOL` | COMEX 黄金代码 | `GC=F` | 通常保留默认值，无需 Key |
| `IFIND_QUANT_REFRESH_TOKEN` | 旧版 iFinD 测试配置 | 空 | 普通本地使用无需填写 |
| `PRISM_AUTH_ACCOUNTS_FILE` | 导入旧版 HTTP Basic 账户文件 | 空 | 新安装留空，直接在登录页注册 |
| `PRISM_DEV_NO_AUTH` | 关闭账户登录检查 | `false` | 正常使用保持 `false`；仅本机演示才设为 `true` |
| `PRISM_DB_PATH` | 自选 SQLite 数据文件位置 | 空，默认 `data/private/prism.sqlite3` | 通常留空 |
| `PRISM_DATABASE_URL` | PostgreSQL 数据库连接地址 | 空 | 已安装并准备 PostgreSQL 后再填写；填写后优先使用 PostgreSQL |
| `PRISM_RESEARCH_PROVIDER_LIMIT` | 每个进程同时访问数据服务的上限 | `100` | 通常保留默认值 |
| `PRISM_RESEARCH_MODEL_LIMIT` | 每个进程同时访问模型服务的上限 | `8` | 通常保留默认值 |
| `PRISM_SECRET_STORE_PATH` | Windows 加密密钥文件位置 | 空，默认 `data/private/prism-secrets.json` | 通常留空；Windows 密钥只能由同一账户读取 |

问财配置也支持 `WENCAI_SKILLHUB_API_KEY` 和 `WENCAI_SKILLHUB_BASE_URL` 两个兼容变量。通常填写样例中的 `IWENCAI_*` 项目即可。

普通本地运行不需要启用 PostgreSQL。`PRISM_DATABASE_URL`、`PRISM_DB_PATH` 和 `PRISM_SECRET_STORE_PATH` 留空即可使用默认文件。有关账户迁移、数据库和密钥服务的详细内容见[本地部署运维参考](local-deployment-operations.md)。

## 第8章 本机数据

账户与分析数据默认保存在项目目录的 `data/private/prism.sqlite3`。备份本地数据时，按[本地部署运维参考](local-deployment-operations.md)中的说明操作。
