from __future__ import annotations

import argparse
import json
import mimetypes
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from backend.discovery import RunRegistry
from backend.limits import build_limits, KNOWN_LIMITS

THIS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = THIS_DIR.parent
REGISTRY = RunRegistry(PROJECT_ROOT)


class VisualizerHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: str | None = None, **kwargs):
        super().__init__(*args, directory=str(THIS_DIR), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.handle_api(parsed)
            return
        if parsed.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def handle_api(self, parsed):
        try:
            if parsed.path == "/api/health":
                self.send_json({"ok": True})
                return
            if parsed.path == "/api/limits":
                self.send_json({"limits": KNOWN_LIMITS})
                return
            if parsed.path == "/api/runs":
                params = parse_qs(parsed.query)
                force = params.get("refresh", ["0"])[0] == "1"
                runs = [meta.to_json() for meta in REGISTRY.ensure_scanned(force)]
                self.send_json({"runs": runs})
                return
            if parsed.path.startswith("/api/run/"):
                tail = parsed.path[len("/api/run/") :].strip("/")
                if tail.endswith("/source"):
                    run_id = tail[: -len("/source")].strip("/")
                    text = REGISTRY.load_source_text(run_id)
                    self.send_text(text)
                    return
                run_id = tail
                strategy = REGISTRY.load_normalized(run_id)
                self.send_json(strategy)
                return
            self.send_error(HTTPStatus.NOT_FOUND, "Unknown API route")
        except KeyError:
            self.send_error(HTTPStatus.NOT_FOUND, "Run not found")
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def send_json(self, payload, status=HTTPStatus.OK):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def send_text(self, text: str, status=HTTPStatus.OK):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass



def main():
    parser = argparse.ArgumentParser(description="Prosperity visualizer local server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("text/css", ".css")

    server = ThreadingHTTPServer((args.host, args.port), VisualizerHandler)
    print(f"Prosperity visualizer running on http://{args.host}:{args.port}")
    print(f"Project root: {PROJECT_ROOT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server…")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
