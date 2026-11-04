"""HTTP の小さなヘルパー（標準ライブラリだけで動く）。"""
import hashlib
import threading
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from ytdl import VERSION

USER_AGENT = f"YTDownloader/{VERSION} (+local app)"


class Cancelled(Exception):
    pass


def _request(url: str, method: str = "GET") -> urllib.request.Request:
    return urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT})


def http_get(url: str, timeout: float = 20, limit: int = 5_000_000) -> bytes:
    with urllib.request.urlopen(_request(url), timeout=timeout) as resp:
        return resp.read(limit)


def github_latest_tag(repo: str, timeout: float = 20) -> str:
    """GitHub の最新リリースのタグ名を返す（API を使わないので回数制限にかからない）。"""
    with urllib.request.urlopen(_request(f"https://github.com/{repo}/releases/latest", "HEAD"),
                                timeout=timeout) as resp:
        final = resp.geturl()
    if "/releases/tag/" not in final:
        raise RuntimeError(f"最新版のタグを取得できません: {final}")
    return urllib.parse.unquote(final.rsplit("/releases/tag/", 1)[1]).strip("/")


def download_file(url: str, dest: Path,
                  progress: Optional[Callable[[int, int], None]] = None,
                  cancel: Optional[threading.Event] = None,
                  timeout: float = 30) -> str:
    """url を dest に保存し、SHA-256 を返す。progress(受信バイト, 全体バイト)。"""
    sha = hashlib.sha256()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(_request(url), timeout=timeout) as resp, open(dest, "wb") as f:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            chunk = resp.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            sha.update(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    if total and done != total:
        raise RuntimeError(f"ダウンロードが途中で切れました ({done}/{total} bytes)")
    return sha.hexdigest()
