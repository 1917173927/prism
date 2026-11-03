# 问财智投独立前端交付

## 第1章 使用入口

已为产品文档单独整理[Windows独立前端交付包](showcase/standalone-frontend-20261003/prism-frontend-demo-windows.zip)。完整解压后进入 `prism-frontend-demo`，双击 `start-demo.cmd` 或 `preview.exe`，即可打开九页交互演示。Windows 64位版自带运行时，无需安装Python、设置PATH、原项目、业务后端、数据库或密钥。其他系统可运行 `python preview.py --open`，需要Python 3.9以上。

本机展开目录为 `E:\prism\output\frontend-documentation-demo\prism-frontend-demo`；用户已解压的 `docs/showcase/standalone-frontend-20261003/prism-frontend-demo` 也已修复，用户另存文件保留。当前自带程序预览为 `http://127.0.0.1:8862/demos/product-demo/#overview`。交付包默认使用8860；发生占用时，可运行 `start-demo.cmd --port 8862`。首次启动窗口需保持打开。截图和产品说明可以直接使用，不要求启动运行环境。

## 第2章 交付内容

| 内容 | 文件或目录 | 产品用途 | 范围 |
| --- | --- | --- | --- |
| 交互前端 | `static` | 九页演示、导航、图表、搜索、引用、运行及取消 | 固定合成数据，本地状态 |
| 启动入口 | `start-demo.cmd`、`preview.exe`、`preview.py` | Windows自动打开，本机HTTP预览 | Windows自带运行时；其他系统需Python |
| 页面说明 | [PRODUCT-GUIDE.md](showcase/standalone-frontend-20261003/PRODUCT-GUIDE.md) | 每页用途、文档说明示例与演示顺序 | 投资工作台客户术语 |
| 产品截图 | 包内 `screenshots` | 九页桌面与三个响应式截图，共12张 | 风险页面保留完整长图 |
| 使用说明 | [README.md](showcase/standalone-frontend-20261003/README.md) | 解压、启动、截图模式及数据说明 | 保留演示数据标记 |

九页为AI投资助手、组合总览、市场观察、交易复盘、投资偏好、研究工具、研究资料、研究任务与风险分析。页面源码可独立交接，Lightweight Charts、CPython、PyInstaller及OpenSSL授权随包保留。构建清单提供源码、程序与授权SHA256，包内共29文件；原26文件Python版ZIP保留历史记录。

## 第3章 验证与归档

比较直接双击HTML与复用已验证本机预览器后，采用后者，保持稳定的资源地址及浏览器行为。直接双击深层HTML不列为已验证入口。

| 验证 | 方法 | 结果 | 证据 |
| --- | --- | --- | --- |
| 自动化 | 原23项回归、7项真实EXE/CMD、追加3项包保护 | 33项不同场景全部通过 | 无Python PATH、中文空格目录、停止重绑 |
| 浏览器 | 自带EXE三固定视口各九页 | 27页通过；无整体横向溢出、缺失图像及控制台错误 | `test-evidence/windows-demo-launcher-20261003` |
| 包完整性 | ZIP CRC、29文件与两个展开目录逐字节对齐 | 通过 | 源码、EXE、授权及逐文件SHA256 |
| Agent审核 | 35条相对引用、说明、截图及数据范围 | 全部有效，无私有资料文件 | 只读独立审查 |

验证范围为独立前端交付；真实金融数据、模型及研究容量沿用项目中的独立验收记录。Pages发布保持停用。复现交付包可在仓库中运行 `python -m tools.package_frontend_documentation_demo`；目标目录已有无关文件时拒绝混入，要求另选空目录。

Windows构建采用独立CPython 3.12.12环境，按 `tools/windows_product_demo/requirements-build.txt` 安装固定依赖，再运行 `python -m tools.build_windows_product_demo`。使用现有标准库HTTP服务，不新增服务器框架；冻结时从EXE所在目录读取资源。定位依据见[PyInstaller运行时说明](https://pyinstaller.org/en/stable/runtime-information.html)。构建可复核，不承诺跨环境的字节级一致。
