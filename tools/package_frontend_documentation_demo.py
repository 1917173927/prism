"""Deliver the isolated product frontend with screenshots and documentation notes."""
import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from tools.package_product_demo import LAUNCH, RESOURCES, ROOT, STATIC, windows_runtime_files

SHOWCASE = ROOT / "docs/showcase/investor-workbench-20261003"
OUTPUT = ROOT / "output/frontend-documentation-demo"
README = """# 问财智投独立前端演示

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
"""
PRODUCT_GUIDE = """# 问财智投产品文档参考

## 第1章 产品定位与用户流程

问财智投面向个人投资者，将组合信息、市场观察、研究资料与风险解释组织在一个工作台中。页面入口以投资者要完成的任务命名；投资者画像用于风险与适当性约束，解释偏好用于调整回答的详细程度。

建议按“组合总览 → AI投资助手 → 研究资料 → 研究任务 → 风险分析”的顺序介绍研究流程，再补充市场观察、交易复盘、投资偏好与研究工具。

## 第2章 页面说明与截图选择

| 页面 | 用户要解决的问题 | 文档说明示例 | 对应截图 |
| --- | --- | --- | --- |
| 组合总览 | 我的资产如何配置，哪些风险需要关注？ | 集中展示资产、收益、持仓权重与参考风险提示，提供组合研究入口。 | `screenshots/02-overview.jpg` |
| AI投资助手 | 怎样围绕持仓和市场形成研究问题？ | 对话页将说明、关键风险与参考资料关联，便于进一步核对依据。 | `screenshots/01-copilot.jpg` |
| 市场观察 | 如何阅读指数收益、波动和回撤？ | 指数走势与收益指标同步切换，并明确指标观察窗口及板块观察范围。 | `screenshots/03-market.jpg` |
| 交易复盘 | 我的交易记录体现哪些行为习惯？ | 汇总持有周期、交易频率、计划执行与近期记录，帮助回顾投资行为。 | `screenshots/04-trading-style.jpg` |
| 投资偏好 | 我能承受哪些风险，希望怎样阅读分析？ | 投资者画像、问卷摘要与解释偏好分别展示；解释偏好不改变风险等级。 | `screenshots/05-profile.jpg` |
| 研究工具 | 本次研究需要哪些资料与分析工具？ | 按市场、公司、组合和资料分类选择工具，并查看当前可用状态。 | `screenshots/06-skill-store.jpg` |
| 研究资料 | 分析结论的原文依据在哪里？ | 按关键词查找资料，查看摘要、报告期间、发布时间与引用片段。 | `screenshots/07-research-knowledge.jpg` |
| 研究任务 | 研究进展怎样，还有哪些信息待补充？ | 展示研究目标、执行进度、处理结果与资料缺口，支持取消演示。 | `screenshots/08-live-research.jpg` |
| 风险分析 | 波动环境与资产联动应如何理解？ | 先说明波动状态与分散配置的用途，计算说明及矩阵按需展开。 | `screenshots/09-research-algorithms.jpg` |

## 第3章 演示与截图步骤

1. 启动演示，从组合总览介绍资产配置与最大单项持仓提示。
2. 进入AI投资助手，点击预设问题，再查看对应资料引用。
3. 进入市场观察，切换指数及日线／月线，展示指标随标的更新。
4. 在研究资料中搜索“组合”，展开引用；在研究工具中演示搜索与选择。
5. 在研究任务中运行固定流程，或立即取消，展示进度与结束状态。
6. 在风险分析中先讲解业务含义，再按需要展开计算说明与矩阵。
7. 截图前进入截图模式，必要时重置演示。桌面推荐1440×1000，平板1024×768，手机390×844。

响应式图片另含 `overview-1024.jpg`、`overview-390.jpg` 和 `research-algorithms-390.jpg`。风险页为完整长图，其余桌面图为首屏；可以按文档版面裁剪，但应保留或补充合成演示数据说明。

## 第4章 描述边界

| 主题 | 可使用的表述 | 应保留的说明 | Demo实际范围 |
| --- | --- | --- | --- |
| 演示数据 | 产品界面及交互样例 | 合成样例，不是真实账户 | 固定快照 |
| 波动环境 | 高／低波动状态的概率 | 不表示上涨／下跌概率 | 独立合成收益 |
| 资产联动 | 用于理解分散配置中的共同波动 | 三个示例资产未关联账户持仓 | 合成收益矩阵 |
| 市场风格 | 观察市场、规模、价值、盈利与投资特征 | 不等于个人持仓收益归因；缺少资料时不生成结果 | 当前显示资料缺口 |
| 研究与引用 | 展示研究进度、资料片段及核对过程 | 引用存在不等于结论得到支持 | 本地固定流程与文档 |
"""


def build(destination: Path, archive_path: Path):
    files = {}
    for resource in RESOURCES:
        files["static/" + resource] = (STATIC / resource).read_bytes()
    files["preview.py"] = (ROOT / "tools/product_demo.py").read_text(encoding="utf-8").encode("utf-8")
    files["start-demo.cmd"] = LAUNCH.encode("ascii")
    files.update(windows_runtime_files())
    files["README.md"] = README.encode("utf-8")
    files["PRODUCT-GUIDE.md"] = PRODUCT_GUIDE.encode("utf-8")
    images = sorted(SHOWCASE.glob("*.jpg"))
    if len(images) != 12:
        raise ValueError("Expected the 12 verified product screenshots")
    for image in images:
        files["screenshots/" + image.name] = image.read_bytes()
    gallery = (SHOWCASE / "index.html").read_text(encoding="utf-8")
    gallery = gallery.replace('href="prism-product-demo.zip"', 'href="../README.md"')
    gallery = gallery.replace("便携演示包</a>", "启动说明</a>")
    gallery = gallery.replace('href="../../frontend-product-demo.md"', 'href="../PRODUCT-GUIDE.md"')
    gallery = gallery.replace('<a href="../../submission/investor-workbench-design-review-20261003.md">设计复核记录</a>', "")
    files["screenshots/index.html"] = gallery.encode("utf-8")
    if destination.exists():
        unknown = {str(path.relative_to(destination)).replace("\\", "/") for path in destination.rglob("*") if path.is_file()} - files.keys()
        if unknown:
            raise ValueError("Destination has unrelated files; choose an empty directory")
    for name, content in files.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(archive_path, "w", ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr("prism-frontend-demo/" + name, content)
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=OUTPUT / "prism-frontend-demo")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/showcase/standalone-frontend-20261003/prism-frontend-demo-windows.zip")
    args = parser.parse_args()
    files = build(args.directory, args.output)
    print(f"Independent frontend: {args.directory}")
    print(f"Documentation package: {args.output}; {len(files)} files")


if __name__ == "__main__":
    main()
