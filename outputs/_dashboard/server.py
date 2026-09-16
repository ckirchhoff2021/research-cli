#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import mimetypes
import os
import re
import threading
import urllib.parse
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
OUTPUTS_ROOT = APP_DIR.parent
CACHE_PATH = APP_DIR / "cache.json"
CACHE_VERSION = 4
MAX_SUMMARY_BYTES = 96 * 1024

mimetypes.add_type("text/markdown", ".md")
mimetypes.add_type("application/json", ".json")
mimetypes.add_type("video/mp4", ".mp4")
mimetypes.add_type("audio/mpeg", ".mp3")
mimetypes.add_type("audio/wav", ".wav")
mimetypes.add_type("image/webp", ".webp")

META_EXTS = {
    "py", "js", "ts", "tsx", "jsx", "css", "sh", "sql", "yaml", "yml",
    "md", "txt", "html", "htm", "json", "toml", "xml", "csv", "log",
}

cache_lock = threading.Lock()
cache_store = {"version": CACHE_VERSION, "items": {}}


def load_cache() -> None:
    global cache_store
    try:
        raw = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        if raw.get("version") == CACHE_VERSION and isinstance(raw.get("items"), dict):
            cache_store = raw
    except (OSError, json.JSONDecodeError):
        cache_store = {"version": CACHE_VERSION, "items": {}}


def save_cache_locked() -> None:
    temporary = CACHE_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(cache_store, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(temporary, CACHE_PATH)


def is_hidden(path: Path) -> bool:
    return any(part.startswith(".") for part in path.parts)


def scan_tree(root: Path) -> dict:
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


def collect_files(node: dict) -> list[dict]:
    if node["type"] == "file":
        return [node]
    result: list[dict] = []
    for child in node.get("children", []):
        result.extend(collect_files(child))
    return result


def read_head(path: Path) -> str:
    with path.open("rb") as handle:
        return handle.read(MAX_SUMMARY_BYTES).decode("utf-8", errors="replace")


def clean_text(value: str, limit: int = 220) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit]


def summarize_code(text: str, ext: str) -> dict:
    description = ""
    patterns = [
        r'^\s*("""|\'\'\')([\s\S]*?)\1',
        r'^\s*"""(.*?)"""',
        r"^\s*'''(.*?)'''",
        r'^\s*/\*([\s\S]*?)\*/',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.MULTILINE)
        if match:
            description = clean_text(re.sub(r"^[#/*\s]+", "", match.group(match.lastindex or 1), flags=re.MULTILINE), 260)
            if description:
                break
    if not description:
        comments = []
        for line in text.splitlines()[:30]:
            stripped = line.strip()
            if stripped.startswith("#"):
                comments.append(stripped.lstrip("# "))
            elif stripped.startswith("//"):
                comments.append(stripped.lstrip("/ "))
            elif comments:
                break
        description = clean_text(" ".join(comments), 260)

    definition_patterns = [
        r"^[ \t]*(?:async\s+)?(?:def|class)\s+([A-Za-z_]\w*)",
        r"^[ \t]*(?:export\s+)?(?:async\s+)?(?:function|class)\s+([A-Za-z_$][\w$]*)",
        r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>",
    ]
    definitions: list[str] = []
    for pattern in definition_patterns:
        for match in re.finditer(pattern, text, re.MULTILINE):
            name = match.group(1)
            if name not in definitions and name not in {"main", "__init__"}:
                definitions.append(name)
            if len(definitions) >= 24:
                break
    if not description:
        description = infer_code_purpose(text, ext, definitions)
    return {"summary": description, "definitions": definitions}


def infer_code_purpose(text: str, ext: str, definitions: list[str]) -> str:
    imports = []
    for line in text.splitlines()[:80]:
        match = re.match(r"\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", line)
        if match:
            imports.append((match.group(1) or match.group(2) or "").split(".")[0])
        match = re.search(r"(?:import|require\()\s*['\"]([^\s'\"]+)['\"]", line)
        if match:
            imports.append(match.group(1).split("/")[-1])
    imports = list(dict.fromkeys(filter(None, imports)))[:7]
    haystack = " ".join([text[:3000], " ".join(definitions[:20]), " ".join(imports)]).lower()

    hints = []
    if re.search(r"moviepy|ffmpeg|video|\bmp4|concat|视频", haystack):
        hints.append("视频处理/拼接")
    if re.search(r"\bpil\b|image|jpeg|\bjpg\b|png|图片|draw", haystack):
        hints.append("图片生成或处理")
    if re.search(r"openai|ark|volcengine|dashscope|model|prompt|llm|agent|模型", haystack):
        hints.append("调用模型或 Agent 能力")
    if re.search(r"requests|httpx|crawler|curl|url|爬取|抓取", haystack):
        hints.append("网络请求或数据抓取")
    if re.search(r"\bjson\b|csv|dataframe|pandas", haystack):
        hints.append("数据读写与处理")
    if re.search(r"subprocess|os\.system|shell|命令", haystack):
        hints.append("执行本地自动化流程")
    hints = list(dict.fromkeys(hints))[:3]

    language = "Python" if ext == "py" else "JavaScript/TypeScript" if ext in {"js", "ts", "tsx", "jsx"} else "Shell" if ext == "sh" else "代码"
    parts = [f"{language}脚本"]
    parts.append(f"，主要用于{ '、'.join(hints) }" if hints else "")
    if definitions:
        parts.append(f"；定义了 {', '.join(definitions[:5])} 等函数/类")
    if imports:
        parts.append(f"，依赖 {', '.join(imports[:5])}")
    return clean_text("".join(parts) + "。", 260)


def summarize_markdown(text: str) -> dict:
    title = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            title = clean_text(stripped.lstrip("# "), 120)
            break
    paragraphs = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
    summary = ""
    for block in paragraphs:
        if block.startswith("#") or block.startswith("```") or block.startswith("|") or block.startswith(">"):
            continue
        plain = re.sub(r"\[[^\]]+\]\([^)]+\)", "", block)
        if "](#" in block or len(plain.strip()) < 20 or re.match(r"^\d+[\.\)]\s*$", plain.strip()):
            continue
        summary = clean_text(
            re.sub(r"[*_`#]+", "", re.sub(r"!\[[^\]]*\]\([^)]*\)", "", block)),
            240,
        )
        if len(summary) >= 24:
            break
    headings = [clean_text(line.lstrip("# "), 80) for line in text.splitlines() if line.strip().startswith("#")][:12]
    return {"title": title, "summary": summary, "headings": headings}


def summarize_html(text: str) -> dict:
    title_match = re.search(r"<title[^>]*>([\s\S]*?)</title>", text, re.IGNORECASE)
    h1_match = re.search(r"<h1[^>]*>([\s\S]*?)</h1>", text, re.IGNORECASE)
    description = ""
    meta_match = re.search(
        r"<meta[^>]+name=['\"]description['\"][^>]+content=['\"]([^'\"]+)['\"]",
        text,
        re.IGNORECASE,
    )
    if meta_match:
        description = clean_text(html.unescape(meta_match.group(1)), 240)
    title = ""
    if title_match:
        title = clean_text(html.unescape(re.sub(r"<[^>]+>", "", title_match.group(1))), 120)
    elif h1_match:
        title = clean_text(html.unescape(re.sub(r"<[^>]+>", "", h1_match.group(1))), 120)
    return {"title": title, "summary": description}


def summarize_json(text: str) -> dict:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {"summary": "JSON 文件，格式无法直接解析，可查看原始内容。"}

    title = ""
    summary = ""
    if isinstance(data, dict):
        for key in ("title", "name", "id", "topic", "model"):
            if isinstance(data.get(key), (str, int, float)):
                title = str(data[key])[:120]
                break
        for key in ("description", "summary", "prompt", "abstract"):
            if isinstance(data.get(key), str):
                summary = clean_text(data[key], 240)
                break
        if not summary:
            keys = [str(key) for key in list(data.keys())[:10]]
            summary = f"JSON 对象，包含 {len(data)} 个字段：{', '.join(keys)}"
        return {"title": title, "summary": summary, "detail": {"keys": list(data.keys())[:30]}}
    if isinstance(data, list):
        return {"title": title, "summary": f"JSON 数组，包含 {len(data)} 条记录。"}
    return {"summary": f"JSON 数据：{type(data).__name__}。"}


def summarize_plain(text: str) -> dict:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return {"summary": clean_text(" ".join(lines[:4]), 240)}


def build_meta(path: Path, ext: str) -> dict:
    text = read_head(path)
    if ext in {"py", "js", "ts", "tsx", "jsx", "css", "sh", "sql", "yaml", "yml", "toml"}:
        return {"kind": "code", **summarize_code(text, ext)}
    if ext == "md":
        return {"kind": "document", **summarize_markdown(text)}
    if ext in {"html", "htm"}:
        return {"kind": "web", **summarize_html(text)}
    if ext == "json":
        return {"kind": "data", **summarize_json(text)}
    return {"kind": "text", **summarize_plain(text)}


def meta_for_path(relative: str) -> dict | None:
    try:
        path = (OUTPUTS_ROOT / relative).resolve()
        path.relative_to(OUTPUTS_ROOT.resolve())
    except ValueError:
        return None
    if not path.is_file():
        return None

    try:
        stat = path.stat()
    except OSError:
        return None
    ext = path.suffix.lower().lstrip(".")
    if ext not in META_EXTS or stat.st_size > 2 * 1024 * 1024:
        return {"kind": "skipped", "title": "", "summary": ""}

    identity = {"mtime": stat.st_mtime, "size": stat.st_size}
    with cache_lock:
        cached = cache_store["items"].get(relative)
        if cached and all(cached.get(key) == identity[key] for key in identity):
            return cached

    try:
        item = {"mtime": stat.st_mtime, "size": stat.st_size, "title": "", "summary": "", "definitions": [], **build_meta(path, ext)}
    except Exception as exc:  # noqa: BLE001
        item = {"mtime": stat.st_mtime, "size": stat.st_size, "kind": "error", "title": "", "summary": "", "error": str(exc)}

    with cache_lock:
        cache_store["items"][relative] = item
    return item


def warm_cache(tree: dict, verbose: bool = True) -> int:
    candidates = [
        file_item["path"]
        for file_item in collect_files(tree)
        if file_item.get("ext") in META_EXTS and file_item.get("size", 0) <= 2 * 1024 * 1024
    ]
    changed = 0

    def worker(relative: str) -> bool:
        before = None
        with cache_lock:
            before = cache_store["items"].get(relative)
        item = meta_for_path(relative)
        return bool(item and item is not before)

    with ThreadPoolExecutor(max_workers=8) as executor:
        changed = sum(1 for result in executor.map(worker, candidates) if result)

    with cache_lock:
        save_cache_locked()
    if verbose:
        print(f"Summary cache ready: {len(candidates)} files scanned, {changed} updated.")
    return changed


class DashboardHandler(SimpleHTTPRequestHandler):
    server_version = "OutputsDashboard/2.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: object) -> None:
        if os.environ.get("DASHBOARD_QUIET") != "1":
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
            self.send_json(scan_tree(OUTPUTS_ROOT))
            return
        if parsed.path == "/api/health":
            self.send_json({"ok": True, "root": str(OUTPUTS_ROOT), "cacheItems": len(cache_store["items"])})
            return
        if parsed.path == "/api/meta":
            relative = urllib.parse.parse_qs(parsed.query).get("path", [""])[0]
            item = meta_for_path(relative)
            self.send_json({"items": {relative: item} if item else {}})
            return
        if parsed.path.startswith("/raw/"):
            self.serve_output(parsed.path[len("/raw/") :])
            return
        self.serve_app(parsed.path)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path != "/api/meta":
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            paths = payload.get("paths", [])
            if not isinstance(paths, list):
                raise ValueError("paths must be a list")
            items = {relative: meta_for_path(relative) for relative in paths[:300] if isinstance(relative, str)}
            with cache_lock:
                save_cache_locked()
            self.send_json({"items": {key: value for key, value in items.items() if value}})
        except (json.JSONDecodeError, ValueError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

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
                start, end = 0, stat.st_size - 1
                partial = False
                if range_header and range_header.startswith("bytes="):
                    token = range_header.removeprefix("bytes=").split(",", 1)[0].strip()
                    try:
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
                    except ValueError:
                        partial = False
                    if not partial:
                        self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                        self.send_header("Content-Range", f"bytes */{stat.st_size}")
                        self.send_header("Content-Length", "0")
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

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline dashboard for the outputs folder")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--no-warm", action="store_true", help="Do not pre-generate the local summary cache")
    parser.add_argument("--build-cache", action="store_true", help="Pre-generate summaries and exit")
    args = parser.parse_args()

    load_cache()
    tree = scan_tree(OUTPUTS_ROOT)
    if args.build_cache:
        changed = warm_cache(tree)
        print(f"Cache written to {CACHE_PATH} ({changed} updated).")
        return 0

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
    if not args.no_warm:
        threading.Thread(target=warm_cache, args=(tree,), daemon=True).start()
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
