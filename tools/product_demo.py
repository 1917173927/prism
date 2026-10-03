"""Serve the offline product demo on loopback using only Python's standard library."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

STATIC = Path(__file__).resolve().parents[1] / "app/api/static"
ENTRY = "/demos/product-demo/"
ASSETS = {
    "/design-tokens.css", "/product-theme.css", "/wencai-zhitou-logo.svg",
    "/lightweight-charts.js", "/lightweight-charts.LICENSE.txt",
}


class DemoHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path = unquote(urlsplit(self.path).path)
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
        if "\\" in path or ".." in path.split("/") or not (path.startswith(ENTRY) or path in ASSETS):
            self.send_error(404, "Only product demo resources are served")
            return
        super().do_HEAD()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8860)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    with ThreadingHTTPServer(("127.0.0.1", args.port), partial(DemoHandler, directory=str(STATIC))) as server:
        print(f"Product demo: http://127.0.0.1:{args.port}{ENTRY}#overview", flush=True)
        print("Screenshot mode: add ?capture=1 before #page. Ctrl+C stops this local preview.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
