from __future__ import annotations

from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[2]


def test_repository_has_one_windows_batch_launcher() -> None:
    launchers = sorted(path.name for path in ROOT.glob("*.bat"))

    assert launchers == ["start.bat"]


def test_windows_launcher_uses_cmd_compatible_line_endings() -> None:
    content = (ROOT / "start.bat").read_bytes()

    assert b"\r\n" in content
    assert b"\n" not in content.replace(b"\r\n", b"")


def test_windows_launcher_bootstraps_supported_runtime_dependencies() -> None:
    script = (ROOT / "start.bat").read_text(encoding="utf-8")

    assert 'set "PYTHON_EXE=%~dp0.venv\\Scripts\\python.exe"' in script
    assert "py -3.12 -m venv" in script
    assert "py -3.11 -m venv" in script
    assert 'pip install -e ".[web]"' in script
    assert "rapidocr_onnxruntime" in script
    assert "if errorlevel 1 goto :dependency_failed" in script
    assert "%errorlevel%" not in script


def test_declared_python_range_matches_ocr_runtime_support() -> None:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        project = tomllib.load(stream)["project"]

    assert project["requires-python"] == ">=3.11,<3.13"
