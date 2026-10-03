"""Package only the offline product demo and its declared local dependencies."""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app/api/static"
WINDOWS_RUNTIME = ROOT / "tools/windows_product_demo"
RESOURCES = [
    "demos/product-demo/index.html", "demos/product-demo/demo.css",
    "demos/product-demo/demo.js", "demos/product-demo/data.js",
    "design-tokens.css", "product-theme.css", "wencai-zhitou-logo.svg",
    "lightweight-charts.js", "lightweight-charts.LICENSE.txt",
]
LAUNCH = '''@echo off
setlocal
cd /d "%~dp0"
if exist "preview.exe" (
  "preview.exe" --open %*
  goto :done
)
py -3 -c "import sys; raise SystemExit(sys.version_info < (3, 9))" >nul 2>nul
if not errorlevel 1 (
  py -3 "preview.py" --open %*
  goto :done
)
py -c "import sys; raise SystemExit(sys.version_info < (3, 9))" >nul 2>nul
if not errorlevel 1 (
  py "preview.py" --open %*
  goto :done
)
python -c "import sys; raise SystemExit(sys.version_info < (3, 9))" >nul 2>nul
if not errorlevel 1 (
  python "preview.py" --open %*
  goto :done
)
for /f "delims=" %%P in ('where python 2^>nul') do (
  "%%P" -c "import sys; raise SystemExit(sys.version_info < (3, 9))" >nul 2>nul
  if not errorlevel 1 (
    "%%P" "preview.py" --open %*
    goto :done
  )
)
echo Python 3.9 or newer is required. Install Python with its Windows launcher or add Python to PATH.
pause
exit /b 1
:done
set "demo_exit_code=%errorlevel%"
if errorlevel 1 pause
endlocal & exit /b %demo_exit_code%
'''.replace("\n", "\r\n")
GUIDE = '''Prism 产品演示

启动：Windows 64位电脑双击 start-demo.cmd，将自动打开浏览器；随包启动程序无需安装Python。其他系统运行 python preview.py --open，需要Python 3.9或以上。
重复启动会复用已有演示服务。首次启动的窗口需保持打开；关闭该窗口将停止服务。
如 8860 被其他服务占用，窗口会说明原因；可运行 start-demo.cmd --port 8861 改用其他端口。
打开：http://127.0.0.1:8860/demos/product-demo/#overview
截图：http://127.0.0.1:8860/demos/product-demo/?capture=1#overview

9 页导航可直接切换。截图模式隐藏演示工具栏，“演示数据”标记一直保留。
Esc 先关闭引用，未打开引用时退出截图模式。重置演示恢复固定初始状态。
所有资料、数值、工具选择和任务状态均为演示样例；不连接真实金融数据、模型或账户。
不含用户数据、凭据或模型权重；Lightweight Charts 授权见 static/lightweight-charts.LICENSE.txt。
Windows启动程序构建版本及运行时授权见 build-manifest.json、runtime-LICENSE.txt。
'''


def windows_runtime_files():
    """Include only the verified standalone runtime built from this preview source."""
    files = {name: (WINDOWS_RUNTIME / name).read_bytes() for name in
             ["preview.exe", "runtime-LICENSE.txt", "build-manifest.json"]}
    manifest = json.loads(files["build-manifest.json"])
    source = (ROOT / "tools/product_demo.py").read_text(encoding="utf-8").encode("utf-8")
    if not files["preview.exe"].startswith(b"MZ") or manifest["executable_sha256"] != hashlib.sha256(files["preview.exe"]).hexdigest():
        raise ValueError("Windows preview executable is damaged or does not match its build manifest")
    if manifest["source_sha256"] != hashlib.sha256(source).hexdigest():
        raise ValueError("Windows preview is out of date; rebuild with tools.build_windows_product_demo")
    if manifest["runtime_license_sha256"] != hashlib.sha256(files["runtime-LICENSE.txt"]).hexdigest():
        raise ValueError("Windows runtime license does not match its build manifest")
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "output/product-demo/prism-product-demo.zip")
    args = parser.parse_args()
    for resource in RESOURCES:
        if not (STATIC / resource).is_file():
            parser.error(f"Missing required demo resource: {resource}")
    runtime_files = windows_runtime_files()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(args.output, "w", ZIP_DEFLATED) as archive:
        for resource in RESOURCES:
            archive.write(STATIC / resource, "prism-product-demo/static/" + resource)
        archive.writestr("prism-product-demo/preview.py", (ROOT / "tools/product_demo.py").read_text(encoding="utf-8"))
        archive.writestr("prism-product-demo/start-demo.cmd", LAUNCH)
        archive.writestr("prism-product-demo/README.txt", GUIDE)
        for name, content in runtime_files.items():
            archive.writestr("prism-product-demo/" + name, content)
    print(f"Portable demo: {args.output}")


if __name__ == "__main__":
    main()
