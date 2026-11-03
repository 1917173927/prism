"""Exercise the shipped Windows demo with no Python available on PATH."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
from threading import Thread
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener
from zipfile import ZipFile

import pytest

from tools import package_frontend_documentation_demo as package


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Runs the shipped Windows executable and CMD")
SYSTEM32 = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32"


@pytest.fixture
def independent_windows_demo(tmp_path):
    archive_path = tmp_path / "frontend.zip"
    files = package.build(tmp_path / "assembled", archive_path)
    with ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        archive.extractall(tmp_path / "独立前端 演示包")
    demo = tmp_path / "独立前端 演示包/prism-frontend-demo"
    assert (demo / "preview.exe").is_file(), "Build and include the Windows preview executable"
    unrelated = tmp_path / "陌生 工作目录"
    unrelated.mkdir()
    environment = dict(os.environ, PATH=str(SYSTEM32))
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    return demo, unrelated, environment, files


def _command(demo, mode, port):
    if mode == "exe":
        return [str(demo / "preview.exe"), "--no-open", "--port", str(port)]
    # CMD quoting differs from normal Windows executable argument escaping.
    return f'"{SYSTEM32 / "cmd.exe"}" /d /c call "{demo / "start-demo.cmd"}" --no-open --port {port}'


def _cleanup_owned_process(process):
    if process.poll() is None:
        try:
            process.send_signal(signal.CTRL_BREAK_EVENT)
            process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            # Frozen one-file programs have a bootloader parent and child.
            # Terminate only the test-owned process and its descendants.
            subprocess.run(
                [str(SYSTEM32 / "taskkill.exe"), "/PID", str(process.pid), "/T", "/F"],
                capture_output=True, timeout=10, check=False,
            )
            process.wait(timeout=10)


def _run_to_exit(command, cwd, environment):
    process = subprocess.Popen(
        command, cwd=cwd, env=environment, stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    try:
        stdout, stderr = process.communicate(b"\n", timeout=30)
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    finally:
        _cleanup_owned_process(process)


def _available_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def _assert_port_released(port):
    deadline = time.monotonic() + 10
    while True:
        try:
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", port))
                listener.listen(1)
            return
        except OSError:
            assert time.monotonic() < deadline, "The stopped demo retained its listening port"
            time.sleep(0.05)


@pytest.mark.parametrize("mode", ["exe", "cmd"])
def test_independent_windows_entry_serves_resources_reuses_and_releases_port(independent_windows_demo, mode):
    demo, unrelated, environment, _ = independent_windows_demo
    port = _available_port()
    opener = build_opener(ProxyHandler({}))
    base = f"http://127.0.0.1:{port}"
    with (unrelated / "preview-output.log").open("wb") as output:
        process = subprocess.Popen(
            _command(demo, mode, port), cwd=unrelated, env=environment,
            stdin=subprocess.DEVNULL, stdout=output, stderr=output,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        try:
            deadline = time.monotonic() + 30
            while True:
                try:
                    with opener.open(base + "/__prism_demo__/health", timeout=1) as response:
                        assert json.loads(response.read())["service"] == "prism-offline-product-demo.v1"
                    break
                except URLError:
                    assert process.poll() is None, "Independent Windows preview exited before startup"
                    assert time.monotonic() < deadline, "Independent Windows preview did not start"
                    time.sleep(0.05)
            for resource in package.RESOURCES:
                url = base + "/" + resource
                expected = (demo / "static" / resource).read_bytes()
                with opener.open(url, timeout=3) as response:
                    assert response.status == 200
                    assert response.read() == expected
                    assert response.headers["Cache-Control"] == "no-store"
                with opener.open(Request(url, method="HEAD"), timeout=3) as response:
                    assert response.status == 200
                    assert response.read() == b""
                    assert int(response.headers["Content-Length"]) == len(expected)
            with opener.open(Request(base + "/__prism_demo__/health", method="HEAD"), timeout=3) as response:
                assert response.status == 200
                assert response.read() == b""
            with opener.open(base + "/", timeout=3) as response:
                assert response.geturl() == base + "/demos/product-demo/"
            forbidden = [
                "/.env", "/preview.exe", "/preview.py", "/api/v1/portfolio",
                "/demos/product-demo/unknown.txt",
                "/demos/product-demo/%2e%2e/%2e%2e/preview.exe",
                "/demos/product-demo/%2e%2e%2f%2e%2e%2fpreview.exe",
                "/demos/product-demo/%2e%2e%5cpreview.exe",
            ]
            for path in forbidden:
                for method in ["GET", "HEAD"]:
                    with pytest.raises(HTTPError) as error:
                        opener.open(Request(base + path, method=method), timeout=3)
                    assert error.value.code == 404, (path, method)
            result = _run_to_exit(_command(demo, mode, port), unrelated, environment)
            assert result.returncode == 0, result.stderr.decode(errors="replace")
            assert b"Reusing the running product demo" in result.stdout
            assert process.poll() is None
        finally:
            _cleanup_owned_process(process)
    _assert_port_released(port)


class OtherService(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"An unrelated service owns this port.")

    def log_message(self, *args):
        pass


@contextmanager
def _other_service():
    with ThreadingHTTPServer(("127.0.0.1", 0), OtherService) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server.server_address[1]
        finally:
            server.shutdown()
            thread.join(timeout=3)
            assert not thread.is_alive()


@pytest.mark.parametrize("mode", ["exe", "cmd"])
def test_independent_windows_entry_rejects_foreign_service(independent_windows_demo, mode):
    demo, unrelated, environment, _ = independent_windows_demo
    with _other_service() as port:
        result = _run_to_exit(_command(demo, mode, port), unrelated, environment)
    assert result.returncode == 1, result.stderr.decode(errors="replace")
    assert b"Another service may be using this port" in result.stderr


@pytest.mark.parametrize("mode", ["exe", "cmd"])
def test_independent_windows_entry_rejects_incomplete_extraction(independent_windows_demo, mode):
    demo, unrelated, environment, _ = independent_windows_demo
    (demo / "static/demos/product-demo/index.html").unlink()
    port = _available_port()
    result = _run_to_exit(_command(demo, mode, port), unrelated, environment)
    assert result.returncode == 1, result.stderr.decode(errors="replace")
    assert b"Extract the complete demo package" in result.stderr
    _assert_port_released(port)


def test_windows_documentation_delivery_contains_executable_license_and_build_manifest(independent_windows_demo):
    demo, _, _, files = independent_windows_demo
    assert len(files) == 29
    assert files["preview.exe"][:2] == b"MZ"
    assert (demo / "runtime-LICENSE.txt").stat().st_size > 0
    assert isinstance(json.loads((demo / "build-manifest.json").read_text(encoding="utf-8")), dict)
    assert (demo / "start-demo.cmd").read_bytes() == package.LAUNCH.encode("ascii")
