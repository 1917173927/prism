"""Package only the offline product demo and its declared local dependencies."""
import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app/api/static"
RESOURCES = [
    "demos/product-demo/index.html", "demos/product-demo/demo.css",
    "demos/product-demo/demo.js", "demos/product-demo/data.js",
    "design-tokens.css", "product-theme.css", "wencai-zhitou-logo.svg",
    "lightweight-charts.js", "lightweight-charts.LICENSE.txt",
]
PREVIEW = '''from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
root = Path(__file__).resolve().parent / "static"
print("Open http://127.0.0.1:8860/demos/product-demo/#overview", flush=True)
with ThreadingHTTPServer(("127.0.0.1", 8860), partial(SimpleHTTPRequestHandler, directory=str(root))) as server:
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
'''
LAUNCH = '@echo off\r\ncd /d "%~dp0"\r\npy -3 preview.py\r\nif errorlevel 1 pause\r\n'
GUIDE = '''Prism 产品演示

启动：安装有 Python 3 的 Windows 电脑双击 start-demo.cmd；其他系统运行 python preview.py。
打开：http://127.0.0.1:8860/demos/product-demo/#overview
截图：http://127.0.0.1:8860/demos/product-demo/?capture=1#overview

9 页导航可直接切换。截图模式隐藏演示工具栏，DEMO 标记一直保留。
Esc 先关闭引用，未打开引用时退出截图模式。重置演示恢复固定初始状态。
所有资料、数值、技能和任务状态均为演示样例；不连接真实金融数据、模型或账户。
不含用户数据、凭据或模型权重；Lightweight Charts 授权见 static/lightweight-charts.LICENSE.txt。
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "output/product-demo/prism-product-demo.zip")
    args = parser.parse_args()
    for resource in RESOURCES:
        if not (STATIC / resource).is_file():
            parser.error(f"Missing required demo resource: {resource}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(args.output, "w", ZIP_DEFLATED) as archive:
        for resource in RESOURCES:
            archive.write(STATIC / resource, "prism-product-demo/static/" + resource)
        archive.writestr("prism-product-demo/preview.py", PREVIEW)
        archive.writestr("prism-product-demo/start-demo.cmd", LAUNCH)
        archive.writestr("prism-product-demo/README.txt", GUIDE)
    print(f"Portable demo: {args.output}")


if __name__ == "__main__":
    main()
