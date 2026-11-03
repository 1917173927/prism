"""Serve the offline product demo on loopback using only Python's standard library."""
import argparse
from functools import partial
from http.client import HTTPException
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import sys
from urllib.parse import unquote, urlsplit
from urllib.request import ProxyHandler, build_opener
import webbrowser

FROZEN = bool(getattr(sys, "frozen", False))
BASE = Path(sys.executable if FROZEN else __file__).resolve().parent
STATIC = BASE / "static" if FROZEN or (BASE / "static").is_dir() else BASE.parent / "app/api/static"
ENTRY = "/demos/product-demo/"
HEALTH = "/__prism_demo__/health"
SERVER_ID = "prism-offline-product-demo.v1"
ASSETS = {
    "/design-tokens.css", "/product-theme.css", "/wencai-zhitou-logo.svg",
    "/lightweight-charts.js", "/lightweight-charts.LICENSE.txt",
}


class DemoServer(ThreadingHTTPServer):
    # Windows SO_REUSEADDR can let a second process take over the same listener.
    # Require exclusive ownership there; normal POSIX restart behavior remains.
    allow_reuse_address = not hasattr(socket, "SO_EXCLUSIVEADDRUSE")

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class DemoHandler(SimpleHTTPRequestHandler):
    def _health(self, head=False):
        body = json.dumps({"service": SERVER_ID}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def do_GET(self):
        path = unquote(urlsplit(self.path).path)
        if path == HEALTH:
            self._health()
            return
        if path == "/":
            self.send_response(302)
            self.send_header("Location", ENTRY)
            self.end_headers()
            return
        if "\\" in path or ".." in path.split("/") or not (path.startswith(ENTRY) or path in ASSETS):
            self.send_error(404, "Only product demo resources are served")
            return
        super().do_GET()

    def do_HEAD(self):
        path = unquote(urlsplit(self.path).path)
        if path == HEALTH:
            self._health(head=True)
            return
        if "\\" in path or ".." in path.split("/") or not (path.startswith(ENTRY) or path in ASSETS):
            self.send_error(404, "Only product demo resources are served")
            return
        super().do_HEAD()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()


def existing_demo(port):
    """Recognize this preview before reusing a listener; never reuse arbitrary services."""
    base_url = f"http://127.0.0.1:{port}"
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(base_url + HEALTH, timeout=2) as response:
            if json.loads(response.read(1024)).get("service") == SERVER_ID:
                return True
    except (OSError, HTTPException, ValueError, AttributeError):
        pass
    # A previously started release has no health endpoint. Its offline entry and
    # frozen data script identify it without stopping a process or changing ports.
    try:
        with opener.open(base_url + ENTRY, timeout=2) as response:
            entry = response.read(65536)
        with opener.open(base_url + ENTRY + "data.js", timeout=2) as response:
            data = response.read(512)
        return (b'data-page="overview"' in entry and b'src="./demo.js"' in entry
                and b"window.PRISM_DEMO_DATA = " in data)
    except (OSError, HTTPException):
        return False


def open_demo(url):
    try:
        opened = webbrowser.open(url, new=2)
    except webbrowser.Error:
        opened = False
    if not opened:
        print(f"Open this address in your browser: {url}", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8860)
    parser.add_argument("--open", dest="open_browser", action="store_true", help="open the demo in your browser")
    parser.add_argument("--no-open", dest="open_browser", action="store_false", help="do not open a browser")
    parser.set_defaults(open_browser=FROZEN)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    url = f"http://127.0.0.1:{args.port}{ENTRY}#overview"
    if not (STATIC / "demos/product-demo/index.html").is_file():
        print("Cannot start: the demo files are missing. Extract the complete demo package first.", file=sys.stderr)
        return 1
    try:
        server = DemoServer(("127.0.0.1", args.port), partial(DemoHandler, directory=str(STATIC)))
    except OSError as error:
        if existing_demo(args.port):
            print(f"Reusing the running product demo: {url}", flush=True)
            if args.open_browser:
                open_demo(url)
            return 0
        print(f"Cannot start the demo on port {args.port}: {error}. Another service may be using this port. "
              "Close that service or run with --port followed by an available port.", file=sys.stderr)
        return 1
    with server:
        print(f"Product demo: {url}", flush=True)
        print("Screenshot mode: add ?capture=1 before #page. Ctrl+C stops this local preview.", flush=True)
        if args.open_browser:
            open_demo(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
