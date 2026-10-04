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

macOS 需要 Git、Python 3.11 或 3.12，以及 [`uv`](https://docs.astral.sh/uv/getting-started/installation/)。安装好 `uv` 后，在项目目录运行：

```bash
uv sync --extra dev --extra web
./start_mac.sh
```

然后访问 <http://127.0.0.1:8000/>。按 `Ctrl+C` 停止服务。

## 第7章 数据和实时查询

账户与分析数据默认保存在项目目录的 `data/private/prism.sqlite3`。需要连接实时数据时，按 `docs/local-deployment-operations.md` 配置对应服务的密钥。Windows 启动脚本会读取项目目录中的 `.env` 文件；不要把这个文件发送给他人或提交到 Git。

更多账户、数据库和备份说明见[本地部署运维参考](local-deployment-operations.md)。
