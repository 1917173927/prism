## 第1章 部署配置

| 项目 | 值 | 用途 | 说明 |
|---|---|---|---|
| 实例 | `112.124.45.166` | 阿里云杭州 ECS | Alibaba Cloud Linux 3，2 核 2 GiB |
| 域名 | `prism.endercrysta2.xyz` | 网站入口 | 阿里云 DNS 管理；根域名和 www 保留原服务 |
| 应用版本 | `10b481bbff52c37554e84b3cac99f5efecbcaf9a` | 已验证代码 | 不包含开发目录中未提交的研究线程改动 |
| 运行环境 | Python 3.11、Uvicorn 单进程 | 应用服务 | 安装 `web,research` 可选依赖 |
| 持久数据 | `/var/lib/prism` | SQLite、运行数据 | 全新部署，不迁移华为云历史数据 |

## 第2章 安装与服务

使用系统包管理器安装 `python3.11 python3.11-pip nginx certbot python3-certbot-nginx libxcb libglvnd-glx`。后两项提供 OCR 所需的系统动态库。保留系统 Python 3.6，不修改其默认链接。将已验证提交中的 `app tools pyproject.toml README.md eval_cases deploy` 导出至 `/opt/prism`，在 `/opt/prism/.venv` 创建独立 Python 环境并安装项目。

`httpx` 必须属于核心运行依赖。原声明仅将其列在开发依赖中，首次生产启动已复现 `ModuleNotFoundError: httpx`；本次修正声明并更新锁文件，重新安装后启动通过。

复用 `deploy/huawei/prism.service` 中与厂商无关的 systemd 服务配置，安装至 `/etc/systemd/system/prism.service`。服务以 `prism` 系统用户运行，监听 `127.0.0.1:8000`。供应商环境变量使用权限为 0600 的 `/etc/prism/prism.env`，禁止在版本库中保存密钥。默认认证强制启用。

将 `deploy/aliyun/prism.nginx.conf` 安装至 `/etc/nginx/conf.d/prism.conf`。运行 `nginx -t` 通过后启用服务。该文件是首次部署 HTTP 配置；证书安装后由 Certbot 在服务器上增加 TLS 和跳转配置，更新时不得以 HTTP 模板覆盖已生效的 TLS 配置。

## 第3章 DNS 与 HTTPS

新增主机记录 `prism`，类型 A，值为 `112.124.45.166`。根域名 `@` 和 `www` 保留原记录，不切换原站点。

安全组开放网站端口 80、443；22 端口供维护连接，应用端口 8000 不对公网开放。验证公开 DNS 返回新 IP 后，通过 Certbot 申请子域名证书并启用 HTTP 到 HTTPS 跳转，开启 `certbot-renew.timer`。证书与私钥保留在服务器 `/etc/letsencrypt`，不提交到 Git。

## 第4章 验收与维护

验收项目包括应用与 Nginx 服务状态、健康接口、未登录 API 拒绝访问、登录页面、HTTPS 证书和 HTTP 跳转。首次用户自行注册。模型和金融数据服务凭据需另行配置；进程健康不代表供应商能力已开通。

更新前使用项目 SQLite 在线备份工具生成新备份文件，保存当前代码版本与环境配置。只部署通过验证的提交。数据库迁移不支持自动降级，恢复时将备份写入新路径并核验，禁止覆盖现有库。运行依赖的实际版本应在服务器上用 `pip freeze` 归档，便于复现。

## 第5章 2026年11月9日验收记录

| 检查项 | 结果 | 证据 | 限制 |
|---|---|---|---|
| 应用与网关 | PASS | prism、nginx 均 active 且 enabled | 已启用开机启动 |
| 登录与认证 | PASS | 本机登录页 200，未认证身份接口 401；Nginx 转发登录页 200 | 尚未由实际用户注册 |
| Python 环境 | PASS | pip check 通过；httpx、RapidOCR、hmmlearn 导入成功 | 未配置模型或行情服务密钥 |
| 回归验证 | PASS | 27 项认证及模型相关测试通过；uv 锁文件一致性检查通过 | 先前完整测试为 1210 通过、16 跳过 |
| 域名解析 | PASS | 服务器解析 prism 子域名得到 112.124.45.166 | 根域名与 www 保留原站点 |
| 公网域名与 HTTPS | BLOCKED | 阿里云返回 403、Non-compliance ICP Filing；ACME 验证失败 | 用户确认仅完成实名认证，尚未 ICP 备案 |

当前仅完成服务器部署，不能宣称域名已上线。先在阿里云办理 ICP 备案，备案通过且拦截解除后再运行 Certbot 签发证书、验证 HTTPS 以及续期流程。`certbot-renew.timer` 已启动，但当前没有签发成功的站点证书。
