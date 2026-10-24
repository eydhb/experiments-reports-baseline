"""Local-only HTTP workbench; imports repositories as data and never executes them."""

import argparse
import json
import mimetypes
import os
from pathlib import Path
import re
import subprocess
import threading
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__
from .agent import analyze
from .model import ModelClient
from .repository import Repository

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class AppServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, data_dir):
        super().__init__(address, Handler)
        self.repositories = {}
        self.repo_lock = threading.Lock()
        self.analysis_slots = threading.BoundedSemaphore(2)
        self.import_slots = threading.BoundedSemaphore(2)
        self.data_dir = Path(data_dir or PROJECT_ROOT / "data").resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def import_repository(self, data):
        source = data.get("source", "sample")
        if source == "sample":
            path = PROJECT_ROOT / "sample_repo"
        elif source == "local":
            raw = data.get("path")
            if not isinstance(raw, str) or not raw.strip():
                raise ValueError("请输入本地仓库的绝对路径。")
            path = Path(raw).expanduser()
            if not path.is_absolute():
                raise ValueError("本地仓库必须使用绝对路径。")
        elif source == "github":
            url = data.get("url", "")
            if not isinstance(url, str) or not re.fullmatch(
                r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?/?", url
            ):
                raise ValueError("请输入公开 GitHub 仓库根地址，例如 https://github.com/owner/repo。")
            path = self.data_dir / ("repo-" + uuid.uuid4().hex[:12])
            env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
            try:
                proc = subprocess.run(
                    ["git", "-c", "credential.helper=", "-c", "core.hooksPath=",
                     "-c", "protocol.file.allow=never", "-c", "http.followRedirects=false",
                     "clone", "--depth", "1", "--", url.rstrip("/"), str(path)],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    timeout=120, env=env, check=False,
                )
            except FileNotFoundError:
                raise ValueError("找不到 Git，请安装 Git 后重试；也可以导入本地目录。") from None
            except subprocess.TimeoutExpired:
                raise ValueError("GitHub 导入超过 120 秒，请先在本地克隆，再使用本地目录导入。") from None
            if proc.returncode:
                raise ValueError("GitHub 克隆失败，请确认仓库公开、地址正确且网络可用。") from None
        else:
            raise ValueError("未知仓库来源。")
        repository = Repository(path)
        index = repository.list_files()
        if not index["files"]:
            raise ValueError("目录中没有可读取的源码或文本文件。")
        identifier = uuid.uuid4().hex
        with self.repo_lock:
            if len(self.repositories) >= 40:
                raise ValueError("当前会话已导入 40 个仓库，请重启服务后继续。")
            self.repositories[identifier] = repository
        return {"id": identifier, "name": repository.root.name, "path": str(repository.root),
                "source": source, "file_count": len(index["files"]), "files": index["files"][:1000],
                "truncated": index.get("truncated", False) or len(index["files"]) > 1000}


class Handler(BaseHTTPRequestHandler):
    server: AppServer

    def log_message(self, format, *args):
        # Avoid logging query strings that may contain a local path.
        pass

    def _respond(self, status, body, content_type="application/json; charset=utf-8"):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; script-src 'self'; style-src 'self'; "
                         "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(body)

    def _allowed(self):
        port = self.server.server_port
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host", "") not in hosts:
            self._respond(403, {"error": "只允许通过本机地址访问。"})
            return False
        origin = self.headers.get("Origin")
        if origin and origin not in {f"http://{host}" for host in hosts}:
            self._respond(403, {"error": "拒绝跨站请求。"})
            return False
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            self._respond(403, {"error": "拒绝跨站请求。"})
            return False
        return True

    def _repository(self, identifier):
        if not isinstance(identifier, str):
            raise ValueError("repository_id 必须为字符串。")
        with self.server.repo_lock:
            repository = self.server.repositories.get(identifier)
        if repository is None:
            raise KeyError("仓库不存在，请先导入仓库。")
        return repository

    def do_GET(self):
        if not self._allowed():
            return
        url = urllib.parse.urlsplit(self.path)
        try:
            if url.path == "/api/status":
                client = ModelClient()
                self._respond(200, {"engine": "LangGraph", "model_available": client.available,
                                    "model": client.model, "version": __version__})
            elif url.path == "/api/file":
                query = urllib.parse.parse_qs(url.query)
                repository = self._repository(query.get("repository_id", [""])[0])
                start = int(query.get("start_line", ["1"])[0])
                end = int(query.get("end_line", [str(start + 119)])[0])
                if end - start >= 400:
                    raise ValueError("一次最多读取 400 行。")
                result = repository.read_file(query.get("path", [""])[0], start, end)
                self._respond(200, result)
            else:
                names = {"/": "index.html", "/index.html": "index.html",
                         "/app.js": "app.js", "/styles.css": "styles.css"}
                if url.path not in names:
                    self._respond(404, {"error": "页面不存在。"})
                    return
                path = PROJECT_ROOT / "web" / names[url.path]
                mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
                self._respond(200, path.read_bytes(), mime + "; charset=utf-8")
        except KeyError:
            self._respond(404, {"error": "仓库不存在，请先导入仓库。"})
        except (ValueError, OSError) as exc:
            self._respond(400, {"error": str(exc)[:500]})

    def do_POST(self):
        if not self._allowed():
            return
        try:
            if self.headers.get_content_type() != "application/json":
                raise ValueError("请求必须使用 application/json。")
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 32_000:
                raise ValueError("请求为空或超过 32 KB。")
            try:
                data = json.loads(self.rfile.read(length))
            except (ValueError, UnicodeDecodeError):
                raise ValueError("请求不是有效 JSON。") from None
            if not isinstance(data, dict):
                raise ValueError("JSON 请求必须为对象。")
            route = urllib.parse.urlsplit(self.path).path
            if route == "/api/import":
                if not self.server.import_slots.acquire(blocking=False):
                    self._respond(429, {"error": "已有两个仓库正在导入，请稍后重试。"})
                    return
                try:
                    result = {"repository": self.server.import_repository(data)}
                finally:
                    self.server.import_slots.release()
            elif route == "/api/analyze":
                repository = self._repository(data.get("repository_id", ""))
                if not self.server.analysis_slots.acquire(blocking=False):
                    self._respond(429, {"error": "已有两个分析正在运行，请稍后重试。"})
                    return
                try:
                    result = analyze(repository, data.get("issue"), data.get("mode", "offline"))
                    result["repository"] = {"id": data["repository_id"], "name": repository.root.name}
                finally:
                    self.server.analysis_slots.release()
            else:
                self._respond(404, {"error": "接口不存在。"})
                return
            self._respond(200, result)
        except KeyError:
            self._respond(404, {"error": "仓库不存在，请先导入仓库。"})
        except (ValueError, OSError) as exc:
            self._respond(400, {"error": str(exc)[:500]})
        except Exception:
            self._respond(500, {"error": "分析遇到内部错误，请查看配置并重试。"})


def create_server(host="127.0.0.1", port=0, data_dir=None):
    if host != "127.0.0.1":
        raise ValueError("此原型仅允许绑定 127.0.0.1。")
    return AppServer((host, port), data_dir)


def main():
    parser = argparse.ArgumentParser(description="Issue Locator 本地定位工作台")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    server = create_server(port=args.port)
    print(f"Issue Locator: http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
