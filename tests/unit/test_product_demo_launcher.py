"""Check repeat launches, occupied ports and the actual Windows entry scripts."""
from contextlib import contextmanager
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import shutil
import subprocess
import sys
from threading import Thread
from zipfile import ZipFile

import pytest

from tools import product_demo

ROOT = Path(__file__).resolve().parents[2]


@contextmanager
def running_server(handler):
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server.server_address[1]
        finally:
            server.shutdown()
            thread.join(timeout=3)
            assert not thread.is_alive()


class OtherService(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Another application is using this port.")

    def log_message(self, *args):
        pass


class LegacyDemo(OtherService):
    def do_GET(self):
        body = {
            product_demo.ENTRY: b'<script src="./demo.js"></script><section data-page="overview"></section>',
            product_demo.ENTRY + "data.js": b"/* Frozen synthetic product snapshot. */\r\nwindow.PRISM_DEMO_DATA = {};",
        }.get(self.path)
        self.send_response(200 if body is not None else 404)
        self.end_headers()
        if body is not None:
            self.wfile.write(body)


def test_repeat_launch_reuses_the_identified_demo_and_opens_its_address(monkeypatch, capsys):
    opened = []
    monkeypatch.setattr(product_demo, "open_demo", opened.append)
    with running_server(partial(product_demo.DemoHandler, directory=str(product_demo.STATIC))) as port:
        assert product_demo.existing_demo(port)
        assert product_demo.main(["--port", str(port), "--open"]) == 0
    assert opened == [f"http://127.0.0.1:{port}{product_demo.ENTRY}#overview"]
    assert "Reusing the running product demo" in capsys.readouterr().out


def test_existing_release_without_health_endpoint_can_be_reused():
    with running_server(LegacyDemo) as port:
        assert product_demo.existing_demo(port)
        assert product_demo.main(["--port", str(port), "--no-open"]) == 0


def test_other_service_is_rejected_without_opening_the_wrong_application(monkeypatch, capsys):
    opened = []
    monkeypatch.setattr(product_demo, "open_demo", opened.append)
    with running_server(OtherService) as port:
        assert not product_demo.existing_demo(port)
        assert product_demo.main(["--port", str(port), "--open"]) == 1
    assert not opened
    assert "Another service may be using this port" in capsys.readouterr().err


def test_missing_demo_has_an_actionable_error(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(product_demo, "STATIC", tmp_path)
    assert product_demo.main(["--no-open"]) == 1
    assert "Extract the complete demo package" in capsys.readouterr().err


def test_browser_failure_keeps_the_local_address_available(monkeypatch, capsys):
    monkeypatch.setattr(product_demo.webbrowser, "open", lambda *args, **kwargs: False)
    product_demo.open_demo("http://127.0.0.1:8860/demos/product-demo/#overview")
    assert "Open this address in your browser" in capsys.readouterr().out


def test_portable_package_uses_the_same_identified_launcher(tmp_path):
    package = tmp_path / "product-demo.zip"
    subprocess.run([sys.executable, "-m", "tools.package_product_demo", "--output", str(package)],
                   cwd=ROOT, check=True, capture_output=True, timeout=30)
    with ZipFile(package) as archive:
        preview = archive.read("prism-product-demo/preview.py")
        assert preview.decode("utf-8") == (ROOT / "tools/product_demo.py").read_text(encoding="utf-8")
        launcher = archive.read("prism-product-demo/start-demo.cmd").decode("ascii")
        assert 'python "preview.py" --open %*' in launcher
        assert 'py -3 "preview.py" --open %*' in launcher
        archive.extractall(tmp_path / "portable demo space")
    script = tmp_path / "portable demo space/prism-product-demo/preview.py"
    with running_server(partial(product_demo.DemoHandler, directory=str(product_demo.STATIC))) as port:
        result = subprocess.run([sys.executable, str(script), "--no-open", "--port", str(port)],
                                cwd=tmp_path, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert b"Reusing the running product demo" in result.stdout


@pytest.mark.skipif(os.name != "nt", reason="Runs the real Windows CMD interpreter")
@pytest.mark.parametrize("other_service", [False, True])
def test_windows_repo_cmd_handles_spaces_and_preserves_failure_status(tmp_path, other_service):
    workspace = tmp_path / "prism demo space"
    (workspace / "tools").mkdir(parents=True)
    (workspace / "app/api/static/demos/product-demo").mkdir(parents=True)
    (workspace / "app/api/static/demos/product-demo/index.html").write_text("demo", encoding="utf-8")
    shutil.copyfile(ROOT / "tools/product_demo.py", workspace / "tools/product_demo.py")
    shutil.copyfile(ROOT / "start-product-demo.cmd", workspace / "start-product-demo.cmd")
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(workspace / ".venv")],
                   check=True, capture_output=True, timeout=30)
    cmd = Path(os.environ["SystemRoot"]) / "System32/cmd.exe"
    handler = OtherService if other_service else partial(product_demo.DemoHandler, directory=str(product_demo.STATIC))
    with running_server(handler) as port:
        # CMD receives its own quoting rules, rather than Python list2cmdline's
        # backslash escaping for ordinary Windows executables.
        result = subprocess.run(f'"{cmd}" /d /c call "{workspace / "start-product-demo.cmd"}" --no-open --port {port}',
                                cwd=tmp_path, capture_output=True, input=b"\n", timeout=15)
    assert result.returncode == (1 if other_service else 0), result.stderr.decode(errors="replace")
    if other_service:
        assert b"Another service may be using this port" in result.stderr
    else:
        assert b"Reusing the running product demo" in result.stdout


@pytest.mark.skipif(os.name != "nt", reason="Runs the real Windows CMD interpreter")
def test_windows_portable_cmd_falls_back_to_python_without_py(tmp_path):
    from tools.package_product_demo import LAUNCH

    workspace = tmp_path / "portable demo space"
    (workspace / "static/demos/product-demo").mkdir(parents=True)
    (workspace / "static/demos/product-demo/index.html").write_text("demo", encoding="utf-8")
    shutil.copyfile(ROOT / "tools/product_demo.py", workspace / "preview.py")
    (workspace / "start-demo.cmd").write_bytes(LAUNCH.encode("ascii"))
    executable_dir = tmp_path / "python fallback"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(executable_dir)],
                   check=True, capture_output=True, timeout=30)
    environment = dict(os.environ, PATH=str(executable_dir / "Scripts"))
    cmd = str(Path(os.environ["SystemRoot"]) / "System32/cmd.exe")
    with running_server(partial(product_demo.DemoHandler, directory=str(product_demo.STATIC))) as port:
        result = subprocess.run(f'"{cmd}" /d /c call "{workspace / "start-demo.cmd"}" --no-open --port {port}',
                                cwd=tmp_path, env=environment, capture_output=True, input=b"\n", timeout=15)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert b"Reusing the running product demo" in result.stdout
