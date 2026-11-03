"""Verify that the documentation delivery runs without the original repository."""
from html.parser import HTMLParser
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, build_opener
from zipfile import ZipFile

import pytest

from tools import package_frontend_documentation_demo as package
from tools import package_product_demo


class ResourceLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attributes):
        for name, value in attributes:
            if name == "src" or (name == "href" and tag in {"link", "a"}):
                if value and not value.startswith("#") and not urlsplit(value).scheme:
                    self.links.append(value)


@pytest.mark.parametrize("damage, reason", [
    ("executable", "damaged"), ("source", "out of date"), ("license", "license does not match"),
])
def test_package_rejects_damaged_or_stale_windows_runtime(tmp_path, monkeypatch, damage, reason):
    files = package_product_demo.windows_runtime_files()
    if damage == "executable":
        files["preview.exe"] += b"damaged"
    elif damage == "source":
        manifest = json.loads(files["build-manifest.json"])
        manifest["source_sha256"] = "0" * 64
        files["build-manifest.json"] = json.dumps(manifest).encode("utf-8")
    else:
        files["runtime-LICENSE.txt"] += b"damaged"
    for name, content in files.items():
        (tmp_path / name).write_bytes(content)
    monkeypatch.setattr(package_product_demo, "WINDOWS_RUNTIME", tmp_path)
    with pytest.raises(ValueError, match=reason):
        package.build(tmp_path / "delivery", tmp_path / "frontend.zip")
    assert not (tmp_path / "frontend.zip").exists()
    assert not (tmp_path / "delivery").exists()


def test_package_is_self_contained_and_preserves_verified_resources(tmp_path):
    destination = tmp_path / "independent demo space"
    archive_path = tmp_path / "frontend.zip"
    files = package.build(destination, archive_path)
    assert len(files) == 29
    assert len([name for name in files if name.endswith(".jpg")]) == 12
    assert not any(part in {".git", ".env", "__pycache__"} for name in files for part in Path(name).parts)
    for resource in package.RESOURCES:
        assert files["static/" + resource] == (package.STATIC / resource).read_bytes()
    for name, content in files.items():
        assert (destination / name).read_bytes() == content
    with ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == {"prism-frontend-demo/" + name for name in files}
        for name, content in files.items():
            assert archive.read("prism-frontend-demo/" + name) == content
    for document in ["static/demos/product-demo/index.html", "screenshots/index.html"]:
        parser = ResourceLinks()
        parser.feed(files[document].decode("utf-8"))
        for link in parser.links:
            target = (destination / document).parent / urlsplit(link).path
            assert target.resolve().is_relative_to(destination.resolve())
            assert target.is_file(), (document, link)


def test_package_refuses_to_mix_unrelated_files(tmp_path):
    destination = tmp_path / "delivery"
    destination.mkdir()
    private = destination / "private-account.txt"
    private.write_text("not part of the demo", encoding="utf-8")
    archive = tmp_path / "frontend.zip"
    with pytest.raises(ValueError, match="unrelated files"):
        package.build(destination, archive)
    assert private.read_text(encoding="utf-8") == "not part of the demo"
    assert not archive.exists()
    assert list(destination.iterdir()) == [private]


def test_extracted_preview_runs_outside_the_repo_and_serves_only_demo(tmp_path):
    archive_path = tmp_path / "frontend.zip"
    package.build(tmp_path / "assembled", archive_path)
    isolated = tmp_path / "outside repository with spaces"
    with ZipFile(archive_path) as archive:
        archive.extractall(isolated)
    demo = isolated / "prism-frontend-demo"
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    process = subprocess.Popen(
        [sys.executable, "-I", str(demo / "preview.py"), "--no-open", "--port", str(port)],
        cwd=isolated, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    opener = build_opener(ProxyHandler({}))
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 10
        while True:
            try:
                with opener.open(base + "/__prism_demo__/health", timeout=1) as response:
                    assert b"prism-offline-product-demo.v1" in response.read()
                break
            except URLError:
                assert process.poll() is None, "Independent preview exited before startup"
                assert time.monotonic() < deadline, "Independent preview did not start"
                time.sleep(0.05)
        for resource in package.RESOURCES:
            with opener.open(base + "/" + resource, timeout=2) as response:
                assert response.read() == (demo / "static" / resource).read_bytes()
        for forbidden in ["/.env", "/preview.py", "/api/v1/portfolio", "/demos/product-demo/%2e%2e/%2e%2e/preview.py"]:
            with pytest.raises(HTTPError) as error:
                opener.open(base + forbidden, timeout=2)
            assert error.value.code == 404
    finally:
        process.terminate()
        process.wait(timeout=5)
