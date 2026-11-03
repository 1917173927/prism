"""Freeze the standard-library preview on Windows; do not collect app dependencies."""
import hashlib
from importlib.metadata import distribution, version
import json
import os
from pathlib import Path
import platform
import subprocess
import ssl
import sys

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "tools/windows_product_demo"
WORK = ROOT / "output/windows-demo-build"


def main():
    if os.name != "nt" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise SystemExit("Build the Windows x64 preview on a Windows x64 host")
    if version("PyInstaller") != "6.22.3":
        raise SystemExit("Install the pinned requirements-build.txt in an isolated build environment")
    if platform.python_version() != "3.12.12":
        raise SystemExit("Use the pinned CPython 3.12.12 Windows x64 build runtime")
    if ssl.OPENSSL_VERSION != "OpenSSL 3.5.5 27 Jan 2026":
        raise SystemExit("Use the recorded runtime with OpenSSL 3.5.5, matching its bundled license")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ, PATH=os.pathsep.join([
        sys.base_prefix, str(Path(sys.base_prefix) / "DLLs"),
        str(Path(os.environ["SystemRoot"]) / "System32"),
    ]))
    environment["PYINSTALLER_CONFIG_DIR"] = str(WORK / "cache")
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    assert WORK.resolve().is_relative_to(ROOT.resolve())
    subprocess.run([
        sys.executable, "-I", "-m", "PyInstaller", "--clean", "--noconfirm", "--onefile", "--console", "--noupx",
        "--name", "preview", "--distpath", str(OUTPUT), "--workpath", str(WORK / "work"),
        "--specpath", str(WORK), str(ROOT / "tools/product_demo.py"),
    ], cwd=WORK, env=environment, check=True)
    write_metadata()
    print(f"Windows preview built: {OUTPUT / 'preview.exe'}")


def write_metadata():
    """Archive the exact executable, source and licenses without rebuilding it."""
    installer = distribution("PyInstaller")
    installer_license = next(path for path in installer.files if str(path).endswith("/COPYING.txt"))
    license_files = [
        ("CPython runtime", Path(sys.base_prefix) / "LICENSE.txt"),
        ("PyInstaller bootloader and exception", installer.locate_file(installer_license)),
        ("OpenSSL 3.5.5; https://github.com/openssl/openssl/tree/openssl-3.5.5", OUTPUT / "licenses/openssl-3.5.5-LICENSE.txt"),
        ("OpenSSL authors", OUTPUT / "licenses/openssl-3.5.5-AUTHORS.md"),
    ]
    (OUTPUT / "runtime-LICENSE.txt").write_bytes(
        "\n\n".join(title + "\n" + path.read_text(encoding="utf-8") for title, path in license_files).encode("utf-8")
    )
    executable = OUTPUT / "preview.exe"
    manifest = {
        "platform": "Windows x64", "mode": "onefile console", "python": platform.python_version(),
        "pyinstaller": version("PyInstaller"),
        "openssl": ssl.OPENSSL_VERSION,
        "build_dependencies": {line.split("==")[0]: version(line.split("==")[0]) for line in
                               (OUTPUT / "requirements-build.txt").read_text(encoding="utf-8").splitlines()
                               if "==" in line},
        "source": "tools/product_demo.py",
        "source_sha256": hashlib.sha256((ROOT / "tools/product_demo.py").read_text(encoding="utf-8").encode("utf-8")).hexdigest(),
        "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "executable_bytes": executable.stat().st_size,
        "runtime_license_sha256": hashlib.sha256((OUTPUT / "runtime-LICENSE.txt").read_bytes()).hexdigest(),
    }
    (OUTPUT / "build-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
