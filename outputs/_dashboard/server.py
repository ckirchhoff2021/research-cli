#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
OUTPUTS_ROOT = APP_DIR.parent

mimetypes.add_type("text/markdown", ".md")
mimetypes.add_type("application/json", ".json")
mimetypes.add_type("video/mp4", ".mp4")
mimetypes.add_type("audio/mpeg", ".mp3")
mimetypes.add_type("audio/wav", ".wav")
mimetypes.add_type("image/webp", ".webp")


def is_hidden(path: Path) -> bool:
    return any(part.startswith(".") for part in path.parts)


def scan_directory(root: Path) -> dict:
    def walk(directory: Path) -> dict:
        children: list[dict] = []
        total_size = 0
        latest_mtime = directory.stat().st_mtime

        for child in sorted(directory.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
            rel = child.relative_to(root)
            if is_hidden(rel) or rel.parts[0] == "_dashboard":
                continue

            try:
                stat = child.stat()
            except OSError:
                continue

            if child.is_dir():
                node = walk(child)
                total_size += node["size"]
                latest_mtime = max(latest_mtime, node["mtime"])
            elif child.is_file():
                node = {
                    "type": "file",
                    "name": child.name,
                    "path": rel.as_posix(),
                    "ext": child.suffix.lower().lstrip("."),
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                }
                total_size += stat.st_size
                latest_mtime = max(latest_mtime, stat.st_mtime)
            else:
                continue
            children.append(node)

        rel_dir = directory.relative_to(root)
        return {
            "type": "directory",
            "name": "outputs" if str(rel_dir) == "." else directory.name,
            "path": "" if str(rel_dir) == "." else rel_dir.as_posix(),
            "children": children,
            "size": total_size,
            "mtime": latest_mtime,
        }

    tree = walk(root)
    tree["root"] = str(root)
    return tree


class DashboardHandler(SimpleHTTPRequestHandler):
    server_version = "OutputsDashboard/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: object) -> None:
        if os.environ.get("DASHBOARD_QUIET") == "1":
            return
        super().log_message(fmt, *args)

    def send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path == "/api/tree":
            try:
                self.send_json(scan_directory(OUTPUTS_ROOT))
            except Exception as exc:  # noqa: BLE001
                self.send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if parsed.path == "/api/health":
            self.send_json({"ok": True, "root": str(OUTPUTS_ROOT)})
            return

        if parsed.path.startswith("/raw/"):
            self.serve_output(parsed.path[len("/raw/") :])
            return

        self.serve_app(parsed.path)

    def safe_child(self, base: Path, quoted_relative: str) -> Path | None:
        relative = urllib.parse.unquote(quoted_relative)
        candidate = (base / relative).resolve()
        try:
            candidate.relative_to(base.resolve())
        except ValueError:
            return None
        return candidate

    def serve_output(self, quoted_relative: str) -> None:
        path = self.safe_child(OUTPUTS_ROOT, quoted_relative)
        if path is None or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return
        self.serve_file(path)

    def serve_app(self, request_path: str) -> None:
        relative = urllib.parse.unquote(request_path.lstrip("/"))
        if not relative:
            path = APP_DIR / "index.html"
        else:
            path = self.safe_child(APP_DIR, relative)
            if path is None:
                self.send_error(HTTPStatus.FORBIDDEN, "Forbidden")
                return

        if not path.is_file():
            path = APP_DIR / "index.html"
        self.serve_file(path, fallback_mime="text/html")

    def serve_file(self, path: Path, fallback_mime: str = "application/octet-stream") -> None:
        try:
            stat = path.stat()
            with path.open("rb") as handle:
                mime = mimetypes.guess_type(path.name)[0] or fallback_mime
                if mime.startswith("text/") or mime in ("application/json", "application/javascript"):
                    mime += "; charset=utf-8"

                range_header = self.headers.get("Range")
                start = 0
                end = stat.st_size - 1
                partial = False

                if range_header and range_header.startswith("bytes="):
                    token = range_header.removeprefix("bytes=").split(",", 1)[0].strip()
                    if token.startswith("-"):
                        length = int(token[1:])
                        if length:
                            start = max(0, stat.st_size - length)
                    else:
                        raw_start, raw_end = token.split("-", 1)
                        start = int(raw_start)
                        if raw_end:
                            end = int(raw_end)
                    end = min(end, stat.st_size - 1)
                    partial = 0 <= start <= end < stat.st_size
                    if not partial:
                        self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                        self.send_header("Content-Range", f"bytes */{stat.st_size}")
                        self.end_headers()
                        return

                self.send_response(HTTPStatus.PARTIAL_CONTENT if partial else HTTPStatus.OK)
                self.send_header("Content-type", mime)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Last-Modified", self.date_time_string(int(stat.st_mtime)))
                self.send_header("Cache-Control", "no-cache")
                if partial:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{stat.st_size}")
                    self.send_header("Content-Length", str(end - start + 1))
                else:
                    self.send_header("Content-Length", str(stat.st_size))
                self.end_headers()

                if self.command != "HEAD":
                    handle.seek(start)
                    remaining = end - start + 1
                    while remaining > 0:
                        chunk = handle.read(min(1024 * 1024, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
        except BrokenPipeError:
            return
        except FileNotFoundError:
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline dashboard for the outputs folder")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()

    class Server(ThreadingHTTPServer):
        daemon_threads = True

    server = None
    actual_port = None
    for port in range(args.port, args.port + 20):
        try:
            server = Server((args.host, port), DashboardHandler)
            actual_port = port
            break
        except OSError:
            continue
    if server is None:
        raise SystemExit(f"Could not find an available port from {args.port} to {args.port + 19}")

    url = f"http://{args.host}:{actual_port}/"
    print(f"Outputs dashboard running at {url}")
    print(f"Serving {OUTPUTS_ROOT}")
    print("Press Ctrl+C to stop.")
    if not args.no_open:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
