"""ブラウザ拡張機能からの依頼を受け取る小さなローカル HTTP サーバー。

安全のための制限
- 127.0.0.1 でだけ待ち受ける（他の PC からは届かない）。
- Host ヘッダーを確認する（DNS リバインディング対策）。
- ダウンロードなど状態を変える要求は、この拡張機能の Origin
  (chrome-extension://<固定ID>) からだけ受け付ける。Web ページからは送れない。
"""
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from PySide6.QtCore import QObject, Signal

from ytdl import APP_NAME, EXTENSION_ID, SERVER_HOST, SERVER_PORT, VERSION
from ytdl.jobs import is_x_post, normalize_url, probe_post

log = logging.getLogger(__name__)

ALLOWED_ORIGIN = f"chrome-extension://{EXTENSION_ID}"
ALLOWED_HOSTS = {f"127.0.0.1:{SERVER_PORT}", f"localhost:{SERVER_PORT}"}


class Bridge(QObject):
    """サーバースレッド → メインスレッドへの受け渡し。"""
    download_requested = Signal(str, str, object, int)  # url, mode, playlist(None/True/False), items
    show_requested = Signal()


class LocalServer:
    def __init__(self, manager):
        self.manager = manager
        self.bridge = Bridge()
        self.httpd: Optional[ThreadingHTTPServer] = None
        self.probes = threading.BoundedSemaphore(3)  # 同時に動かす yt-dlp の確認は 3 つまで
        self.error = ""

    @property
    def running(self) -> bool:
        return self.httpd is not None

    def start(self) -> bool:
        handler = _make_handler(self)
        try:
            self.httpd = ThreadingHTTPServer((SERVER_HOST, SERVER_PORT), handler)
        except OSError as e:
            self.error = f"ポート {SERVER_PORT} を使えません（{e.strerror or e}）"
            log.error(self.error)
            return False
        self.httpd.daemon_threads = True
        threading.Thread(target=self.httpd.serve_forever, daemon=True, name="local-server").start()
        log.info("拡張機能用サーバーを開始: %s:%s", SERVER_HOST, SERVER_PORT)
        return True

    def stop(self) -> None:
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None

    def snapshot(self) -> dict:
        jobs = sorted(self.manager.all_jobs(), key=lambda j: j.created, reverse=True)[:8]
        return {
            "app": APP_NAME, "version": VERSION,
            "ready": self.manager.tools.ready, "updating": self.manager.tools.updating,
            "status": self.manager.tools.last_status,
            "active": self.manager.active_count(),
            "default_mode": self.manager.settings.default_mode,
            "jobs": [j.to_api() for j in jobs],
        }


def _make_handler(server: LocalServer):
    class Handler(BaseHTTPRequestHandler):
        server_version = "YTDownloader"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # 標準のアクセスログは出さない
            pass

        # ---------- 共通 ----------
        def _host_ok(self) -> bool:
            return self.headers.get("Host", "") in ALLOWED_HOSTS

        def _origin(self) -> str:
            return self.headers.get("Origin", "")

        def _send(self, code: int, body: dict) -> None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            if self._origin() == ALLOWED_ORIGIN:
                self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
                self.send_header("Vary", "Origin")
            self.end_headers()
            self.wfile.write(data)

        def _read_json(self) -> Optional[dict]:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return None
            if length <= 0:
                return None
            if length > 64 * 1024:
                self.close_connection = True
                return None
            try:
                data = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return None
            return data if isinstance(data, dict) else None

        # ---------- メソッド ----------
        def do_OPTIONS(self):
            if not self._host_ok() or self._origin() != ALLOWED_ORIGIN:
                self._send(403, {"ok": False, "error": "forbidden"})
                return
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Private-Network", "true")
            self.send_header("Access-Control-Max-Age", "600")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            if not self._host_ok():
                self._send(403, {"ok": False, "error": "forbidden"})
                return
            origin = self._origin()
            if origin and origin != ALLOWED_ORIGIN:
                self._send(403, {"ok": False, "error": "forbidden"})
                return
            if self.path.split("?")[0] == "/api/status":
                self._send(200, {"ok": True, **server.snapshot()})
            else:
                self._send(404, {"ok": False, "error": "not found"})

        def do_POST(self):
            if not self._host_ok() or self._origin() != ALLOWED_ORIGIN:
                self._send(403, {"ok": False, "error": "forbidden"})
                return
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                self._send(415, {"ok": False, "error": "json only"})
                return
            path = self.path.split("?")[0]
            body = self._read_json()  # 接続を使い回すので、本文は必ず読み切る
            if body is None and path == "/api/show":
                body = {}
            if body is None:
                self._send(400, {"ok": False, "error": "bad request"})
                return
            if path == "/api/download":
                url = normalize_url(str(body.get("url", "")))
                mode = body.get("mode")
                playlist = body.get("playlist")
                if not url:
                    self._send(400, {"ok": False, "error": "URL が正しくありません"})
                    return
                if mode not in ("video", "audio", None, "default"):
                    self._send(400, {"ok": False, "error": "mode が正しくありません"})
                    return
                if playlist not in (True, False, None):
                    playlist = None
                items = body.get("items")
                items = items if isinstance(items, int) and not isinstance(items, bool) and 1 <= items <= 50 else 0
                server.bridge.download_requested.emit(url, mode or "default", playlist, items)
                self._send(202, {"ok": True})
            elif path == "/api/probe":
                # X の投稿に動画が何本あるか（このスレッドで yt-dlp を待つ。サーバーは要求ごとに別スレッド）
                url = normalize_url(str(body.get("url", "")))
                if not url or not is_x_post(url):
                    self._send(400, {"ok": False, "error": "X の投稿の URL ではありません"})
                    return
                if server.probes.acquire(timeout=0):
                    try:
                        res = probe_post(url, server.manager.settings, server.manager.tools)
                    finally:
                        server.probes.release()
                else:
                    res = {"ok": False, "error": "確認の依頼が多すぎます。少し待ってから開き直してください"}
                self._send(200, res)
            elif path == "/api/show":
                server.bridge.show_requested.emit()
                self._send(200, {"ok": True})
            else:
                self._send(404, {"ok": False, "error": "not found"})

    return Handler
