"""拡張機能から受け取ったブラウザの Cookie を、yt-dlp が読める cookies.txt にする。

YouTube はボット判定のため、ログイン中のブラウザの Cookie がないと取得できないことがある。
yt-dlp の --cookies-from-browser は、Chromium 系ブラウザの起動中は Cookie のファイルが
ロックされていて読めない。そこで拡張機能が Cookie を読み、ダウンロードの依頼と一緒に送ってくる。

- サイトごとに最新の 1 つだけを %LOCALAPPDATA%\\YTDownloader\\cache\\cookies\\<site>.txt に置く。
  アプリに URL を貼り付けたときも、同じサイトなら直近に受け取った Cookie を使える。
- yt-dlp は終了時に Cookie のファイルを書き戻すので、ジョブごとに写しを作って渡し、終わったら消す。
"""
import logging
import os
import shutil
import time
import urllib.parse
from pathlib import Path
from typing import Optional

from ytdl.paths import CACHE_DIR

log = logging.getLogger(__name__)

COOKIE_DIR = CACHE_DIR / "cookies"
JOB_DIR = COOKIE_DIR / "jobs"
MAX_AGE = 14 * 24 * 3600  # これより古い Cookie は使わない（ログインが切れている可能性が高い）

# サイト名 → (URL のホスト, 受け付ける Cookie のドメイン)
SITES = {
    "youtube": (("youtube.com", "youtu.be"), ("youtube.com",)),
    "x": (("x.com", "twitter.com"), ("x.com",)),
}


def _matches(host: str, base: str) -> bool:
    return host == base or host.endswith("." + base)


def site_of(url: str) -> Optional[str]:
    try:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
    except ValueError:
        return None
    for site, (hosts, _) in SITES.items():
        if any(_matches(host, h) for h in hosts):
            return site
    return None


def _clean(text) -> str:
    return str(text).replace("\t", " ").replace("\r", "").replace("\n", "")


def save(url: str, cookies) -> bool:
    """拡張機能から届いた Cookie を、そのサイトの cookies.txt として保存する。"""
    site = site_of(url)
    if not site or not isinstance(cookies, list) or not cookies:
        return False
    domains = SITES[site][1]
    lines = ["# Netscape HTTP Cookie File", "# Written by YT Downloader from the browser extension", ""]
    for c in cookies[:400]:
        if not isinstance(c, dict):
            continue
        domain = _clean(c.get("domain", "")).lower()
        name, value = _clean(c.get("name", "")), _clean(c.get("value", ""))
        if not domain or not name or not any(_matches(domain.lstrip("."), d) for d in domains):
            continue
        host_only = bool(c.get("hostOnly"))
        if not host_only and not domain.startswith("."):
            domain = "." + domain
        path = _clean(c.get("path") or "/") or "/"
        try:
            expires = max(0, int(c.get("expires") or 0))
        except (TypeError, ValueError):
            expires = 0
        lines.append("\t".join([domain, "FALSE" if host_only else "TRUE", path,
                                "TRUE" if c.get("secure") else "FALSE", str(expires), name, value]))
    if len(lines) <= 3:
        return False
    COOKIE_DIR.mkdir(parents=True, exist_ok=True)
    target = COOKIE_DIR / f"{site}.txt"
    tmp = target.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, target)
    return True


def current(url: str) -> Optional[Path]:
    """その URL のサイトについて、使える cookies.txt があれば返す。"""
    site = site_of(url)
    if not site:
        return None
    path = COOKIE_DIR / f"{site}.txt"
    try:
        if time.time() - path.stat().st_mtime > MAX_AGE:
            return None
    except OSError:
        return None
    return path


def job_copy(url: str, job_id: str) -> Optional[Path]:
    """ジョブ用の写しを作る（yt-dlp が書き戻しても、ほかのジョブとぶつからない）。"""
    src = current(url)
    if not src:
        return None
    try:
        JOB_DIR.mkdir(parents=True, exist_ok=True)
        dst = JOB_DIR / f"{job_id}-{os.getpid()}.txt"
        shutil.copyfile(src, dst)
        return dst
    except OSError:
        log.exception("Cookie の写しを作れません")
        return None


def discard(path: Optional[Path]) -> None:
    if path:
        try:
            path.unlink()
        except OSError:
            pass


def cleanup_jobs() -> None:
    """前回の終了時に残った写しを消す（起動時に呼ぶ）。"""
    shutil.rmtree(JOB_DIR, ignore_errors=True)
