"""Loopback-only review desk; serves only its own UI and recorded evidence."""
from __future__ import annotations

import hashlib
import argparse
import webplay
import io
import json
import mimetypes
from pathlib import Path
import secrets
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse
import webbrowser
import zipfile

from engine import BASE, RUNS, GAME_ROOT, ReviewEngine, builds, codex_info, validate_game
from providers import ProfileStore, test_vision

TOKEN = secrets.token_urlsafe(32)
ENGINE = ReviewEngine()
INFO = None
WEB = BASE / "web"
PROFILES = ProfileStore()


def permitted_asset(job_id, name):
    if job_id not in ENGINE.jobs:
        raise ValueError("找不到这次检查")
    folder = (RUNS / job_id).resolve()
    path = (folder / name).resolve()
    if not path.is_relative_to(folder) or not path.is_file() or path.suffix.lower() not in [".png", ".json", ".log"]:
        raise ValueError("证据文件不存在")
    if "saves" in path.relative_to(folder).parts or path.name in ["codex_events.jsonl"]:
        raise ValueError("此文件不在证据展示范围内")
    return path


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def send(self, code, payload, mime="application/json; charset=utf-8", extra=None):
        if not isinstance(payload, bytes):
            payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        if extra:
            for key, value in extra.items():
                self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def host_ok(self):
        port = self.server.server_port
        return self.headers.get("Host") in [f"127.0.0.1:{port}", f"localhost:{port}"]

    def do_GET(self):
        if not self.host_ok():
            return self.send(403, {"error": "只允许本机访问"})
        path = unquote(urlparse(self.path).path)
        try:
            if path == "/api/health":
                return self.send(200, {"app": "revision-room", "version": 5, "installId": hashlib.sha256(str(BASE.resolve()).casefold().encode()).hexdigest()[:16]})
            if path == "/api/bootstrap":
                return self.send(200, {"token": TOKEN, "webplayAvailable": webplay.available(), "builds": builds(), "codex": INFO, "active": ENGINE.active, "history": ENGINE.history(), "ai": PROFILES.public()})
            if path == "/api/history":
                return self.send(200, {"active": ENGINE.active, "history": ENGINE.history()})
            if path == "/api/demo":
                return self.send(200, json.loads((WEB / "demo" / "report.json").read_text(encoding="utf-8")))
            if path in ["/demo/hud.png", "/demo/inventory.png"]:
                return self.send(200,(WEB / path.lstrip("/")).read_bytes(),"image/png")
            if path == "/demo/practice.html":
                page = (WEB / "demo" / "scene.html").read_text(encoding="utf-8")
                page = page.replace("</html>", '<script src="/demo/practice.js"></script></html>')
                return self.send(200, page.encode("utf-8"), "text/html; charset=utf-8")
            if path == "/demo/practice.js":
                return self.send(200, (WEB / "demo" / "practice.js").read_bytes(), "text/javascript; charset=utf-8")
            if path == "/demo/scene.html":
                return self.send(200,(WEB / "demo" / "scene.html").read_bytes(),"text/html; charset=utf-8")
            if path.startswith("/api/runs/"):
                parts = path.split("/")
                job_id = parts[3]
                if len(parts) == 4:
                    return self.send(200, ENGINE.get(job_id))
                if len(parts) == 5 and parts[4] == "markdown":
                    return self.send(200, ENGINE.markdown(job_id).encode("utf-8"), "text/markdown; charset=utf-8",
                                     {"Content-Disposition": f'attachment; filename="revision-{job_id}.md"'})
                if len(parts) == 5 and parts[4] == "bundle":
                    report = ENGINE.get(job_id)
                    archive = io.BytesIO()
                    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
                        z.writestr("report.md", ENGINE.markdown(job_id))
                        z.writestr("report.json", json.dumps(report, ensure_ascii=False, indent=2))
                        for item in report["screenshots"]:
                            z.write(permitted_asset(job_id, item["path"]), item["path"])
                        for item in report["checks"]:
                            z.write(permitted_asset(job_id, item["evidence"]), item["evidence"])
                    return self.send(200, archive.getvalue(), "application/zip",
                                     {"Content-Disposition": f'attachment; filename="revision-{job_id}.zip"'})
            if path.startswith("/evidence/"):
                parts = path.split("/", 3)
                if len(parts) != 4:
                    raise ValueError("证据地址不完整")
                file = permitted_asset(parts[2], parts[3])
                mime = "image/png" if file.suffix == ".png" else "text/plain; charset=utf-8"
                return self.send(200, file.read_bytes(), mime)
            files = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css", "/favicon.svg": "favicon.svg"}
            if path in files:
                file = WEB / files[path]
                mime = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml"}[file.suffix]
                return self.send(200, file.read_bytes(), mime + "; charset=utf-8")
            self.send(404, {"error": "没有这个页面"})
        except (ValueError, OSError, KeyError, IndexError) as e:
            self.send(404, {"error": str(e)})

    def do_POST(self):
        if not self.host_ok() or self.headers.get("X-Revision-Token") != TOKEN:
            return self.send(403, {"error": "操作来源无效，请刷新修订室"})
        origin = self.headers.get("Origin")
        if origin and origin not in [f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"]:
            return self.send(403, {"error": "不接受其他网页发起的操作"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            limit = 35 * 1024 * 1024 if urlparse(self.path).path in {"/api/import", "/api/import-review"} else 1024 * 1024
            if length < 0 or length > limit:
                return self.send(413, {"error": "请求内容过大"})
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self.send(415, {"error": "需要 JSON 请求"})
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise ValueError("请求格式无效")
            path = urlparse(self.path).path
            if path == "/api/web-play":
                return self.send(202, {"id": webplay.start(ENGINE, body)})
            if path == "/api/import-review":
                if "review" not in body:
                    raise ValueError("请提供已有评审 JSON")
                return self.send(200, {"id": ENGINE.start_images(body)})
            if path == "/api/import":
                if "review" in body:
                    raise ValueError("请从导入已有评审入口提交")
                provider = PROFILES.resolve(body.get("reviewer", "codex"))
                return self.send(202, {"id": ENGINE.start_images(body, provider)})
            if path == "/api/profiles/save":
                return self.send(200, PROFILES.save(body))
            if path == "/api/profiles/test":
                return self.send(200, test_vision(PROFILES.draft(body)))
            if path == "/api/profiles/delete":
                return self.send(200, PROFILES.delete(body.get("id")))
            if path == "/api/profiles/select":
                PROFILES.select(body.get("id"))
                return self.send(200, {"ok": True})
            if path == "/api/start":
                vision = body.get("vision", True) is True
                provider = PROFILES.resolve(body.get("reviewer", "codex")) if vision else None
                job_id = ENGINE.start(str(body.get("path", "")), vision=vision, provider=provider)
                return self.send(202, {"id": job_id})
            if path == "/api/shutdown":
                if ENGINE.active:
                    raise ValueError("请先等当前评审结束")
                self.send(200, {"ok": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if path == "/api/cancel":
                ENGINE.cancel(body.get("id"))
                return self.send(200, {"ok": True})
            if path == "/api/finding":
                ENGINE.set_finding_state(body.get("id"), body.get("finding"), body.get("state"))
                return self.send(200, {"ok": True})
            if path == "/api/pick":
                script = ("Add-Type -AssemblyName System.Windows.Forms; "
                          "$dlg=New-Object System.Windows.Forms.OpenFileDialog; $dlg.Filter='Game (*.exe)|*.exe'; "
                          "if($dlg.ShowDialog() -eq 'OK'){[Console]::OutputEncoding=[Text.Encoding]::UTF8; [Console]::Write($dlg.FileName)}")
                result = subprocess.run(["powershell.exe", "-NoProfile", "-STA", "-Command", script],
                                        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                selected = result.stdout.strip()
                if selected:
                    selected = str(validate_game(selected))
                return self.send(200, {"path": selected})
            return self.send(404, {"error": "没有这个操作"})
        except (ValueError, OSError, TypeError, subprocess.TimeoutExpired) as e:
            self.send(400, {"error": str(e)})


def main():
    global INFO
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=4185)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()
    INFO = codex_info()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"修订室：http://127.0.0.1:{args.port}", flush=True)
    if args.open:
        webbrowser.open(f"http://127.0.0.1:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        if ENGINE.active:
            ENGINE.cancel(ENGINE.active)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
