# 问财智投独立前端演示

## 第1章 快速使用

1. 完整解压 `prism-frontend-demo-windows.zip`，打开其中的 `prism-frontend-demo` 文件夹。
2. 双击 `start-demo.cmd`。浏览器会自动打开九页交互演示；首次启动的窗口需保持打开。
3. 写产品文档时，可直接使用 `screenshots` 中的12张图片，并参考 `PRODUCT-GUIDE.md`。
4. 点击页面中的“截图模式”隐藏演示工具栏；“演示数据”标记会持续显示。

Windows 64位版随包提供独立启动程序，无需安装Python或设置PATH。全部前端资源与预览器均已包含，不需要 Prism 源码、业务后端、数据库、账户或数据接口密钥。其他系统使用 `preview.py`，需要Python 3.9或以上。

## 第2章 文件与入口

| 文件或目录 | 用途 | 使用方式 | 依赖 |
| --- | --- | --- | --- |
| `start-demo.cmd`、`preview.exe` | Windows 64位启动入口 | 双击CMD，自动打开演示 | 随包运行时，无需安装 |
| `preview.py` | 本机预览器 | 其他系统运行 `python preview.py --open` | Python 标准库 |
| `static` | 完整前端与固定演示数据 | 原始 HTML、CSS、JavaScript 可独立交接 | 浏览器 |
| `PRODUCT-GUIDE.md` | 九页用途、文档措辞与截图建议 | 供产品文档写作参考 | 文本阅读器 |
| `screenshots/index.html` | 图片索引 | 浏览器打开，或直接使用目录中的 JPEG | 无运行环境要求 |

运行时授权与构建信息分别见 `runtime-LICENSE.txt`、`build-manifest.json`。

默认入口：`http://127.0.0.1:8860/demos/product-demo/#overview`。
截图入口：`http://127.0.0.1:8860/demos/product-demo/?capture=1#overview`。

重复启动会复用已运行的演示。若8860被其他程序占用，运行 `start-demo.cmd --port 8861`，随后打开提示中的新地址。关闭首次启动的窗口会停止演示服务；图片与页面说明仍可单独使用。

## 第3章 数据与使用范围

页面使用固定合成样例，展示产品界面与交互。研究任务为本地步骤演示；研究资料为固定文档关键词匹配；工具选择只改变当前演示状态。它们不证明真实金融数据、实际模型调用或真实研究容量。

本机HTTP预览为已验证启动方式。请完整解压后启动；不要在压缩包内直接运行，也不将直接双击深层HTML作为本交付的已验证启动方式。Lightweight Charts授权随包保留在 `static/lightweight-charts.LICENSE.txt`。Pages发布未启用。
