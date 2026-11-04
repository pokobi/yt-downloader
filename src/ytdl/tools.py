"""yt-dlp / FFmpeg / Deno を専用フォルダで管理し、起動時に自動更新する。

方針
- 新しい版があるときだけダウンロードする（同じ版なら通信は数KBだけ）。
- 必ず SHA-256 を照合し、実際に起動できることを確かめてから入れ替える。
- 更新に失敗しても、手元の版（なければシステムに入っているもの）で動き続ける。
- ダウンロード中のジョブがあるときは入れ替えない（DownloadManager が待つ）。
"""
import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal

from ytdl.net import download_file, github_latest_tag, http_get
from ytdl.paths import BIN_DIR, VERSIONS_FILE

log = logging.getLogger(__name__)

CREATE_NO_WINDOW = 0x08000000
YTDLP_REPOS = {"stable": "yt-dlp/yt-dlp", "nightly": "yt-dlp/yt-dlp-nightly-builds"}
FFMPEG_VERSION_URL = "https://www.gyan.dev/ffmpeg/builds/release-version"
FFMPEG_ZIP_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
DENO_REPO = "denoland/deno"
DENO_ASSET = "deno-x86_64-pc-windows-msvc.zip"
HEX64 = re.compile(r"\b[0-9a-fA-F]{64}\b")


def run_quiet(args, timeout=30) -> str:
    out = subprocess.run(args, capture_output=True, timeout=timeout, creationflags=CREATE_NO_WINDOW)
    if out.returncode != 0:
        raise RuntimeError(f"{Path(args[0]).name} が起動できません (code {out.returncode})")
    return out.stdout.decode("utf-8", "replace").strip()


@dataclass
class ToolState:
    name: str
    path: Optional[Path] = None
    version: str = ""
    source: str = ""  # "managed" / "system" / ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.path is not None and self.path.exists()

    def describe(self) -> str:
        if not self.ok:
            return "未導入" + (f"（{self.error}）" if self.error else "")
        where = "アプリ管理" if self.source == "managed" else "システム"
        return f"{self.version or '不明'}（{where}）"


class ToolManager(QObject):
    status_changed = Signal(str, float)  # 表示テキスト, 進み具合(0〜1、-1は不定)
    update_finished = Signal(bool)  # True = ダウンロードに必要なツールがそろっている

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self.cancel_event = threading.Event()
        self.versions = self._load_versions()
        self.ytdlp = ToolState("yt-dlp")
        self.ffmpeg = ToolState("FFmpeg")
        self.deno = ToolState("Deno")
        self.last_status = "準備中"
        self.resolve()

    # ---------- 状態 ----------
    @property
    def updating(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def ready(self) -> bool:
        return self.ytdlp.ok

    def _load_versions(self) -> dict:
        try:
            return json.loads(VERSIONS_FILE.read_text(encoding="utf-8-sig"))
        except Exception:
            return {}

    def _save_versions(self) -> None:
        try:
            BIN_DIR.mkdir(parents=True, exist_ok=True)
            VERSIONS_FILE.write_text(json.dumps(self.versions, indent=2), encoding="utf-8")
        except Exception:
            log.exception("versions.json を保存できません")

    def resolve(self) -> None:
        """使うツールの場所を決める。アプリ管理の版を優先し、なければシステムの版。"""
        self._resolve_one(self.ytdlp, BIN_DIR / "yt-dlp.exe", "yt-dlp", "yt-dlp")
        self._resolve_one(self.ffmpeg, BIN_DIR / "ffmpeg.exe", "ffmpeg", "ffmpeg")
        self._resolve_one(self.deno, BIN_DIR / "deno.exe", "deno", "deno")

    def _resolve_one(self, st: ToolState, managed: Path, key: str, which: str) -> None:
        if managed.exists():
            st.path, st.source = managed, "managed"
            st.version = self.versions.get(key, "")
            return
        found = shutil.which(which)
        if found:
            st.path, st.source, st.version = Path(found), "system", ""
            try:
                first = run_quiet([found, "--version"] if key != "ffmpeg" else [found, "-version"])
                st.version = first.splitlines()[0][:60]
            except Exception:
                pass
        else:
            st.path, st.source, st.version = None, "", ""

    def last_check_age(self) -> float:
        return time.time() - float(self.versions.get("last_check", 0))

    # ---------- 更新 ----------
    def start_update(self, force: bool = False) -> bool:
        with self._lock:
            if self.updating:
                return False
            self.cancel_event.clear()
            self._thread = threading.Thread(target=self._run, args=(force,), daemon=True, name="tool-update")
            self._thread.start()
            return True

    def _emit(self, text: str, frac: float = -1) -> None:
        self.last_status = text
        self.status_changed.emit(text, frac)

    def _run(self, force: bool) -> None:
        BIN_DIR.mkdir(parents=True, exist_ok=True)
        steps: list[tuple[ToolState, Callable[[bool], None]]] = [
            (self.ytdlp, self._update_ytdlp),
            (self.ffmpeg, self._update_ffmpeg),
            (self.deno, self._update_deno),
        ]
        for st, fn in steps:
            if self.cancel_event.is_set():
                break
            st.error = ""
            try:
                fn(force)
            except Exception as e:  # 1つ失敗しても他は続ける
                st.error = _short_error(e)
                log.warning("%s の更新に失敗: %s", st.name, e, exc_info=True)
        self.versions["last_check"] = time.time()
        self._save_versions()
        self.resolve()
        errors = [f"{s.name}: {s.error}" for s in (self.ytdlp, self.ffmpeg, self.deno) if s.error]
        if not self.ytdlp.ok:
            self._emit("yt-dlp を用意できません。ネット接続を確認してください", 0)
        elif errors:
            self._emit("一部の更新に失敗（今の版で続行）", 1)
        else:
            self._emit("準備完了", 1)
        self.update_finished.emit(self.ready)

    def _progress_cb(self, label: str):
        last = [0.0]

        def cb(done: int, total: int) -> None:
            now = time.monotonic()
            if now - last[0] < 0.2 and done != total:
                return
            last[0] = now
            if total:
                self._emit(f"{label} {done / 1048576:.0f}/{total / 1048576:.0f}MB", done / total)
            else:
                self._emit(f"{label} {done / 1048576:.0f}MB")
        return cb

    # yt-dlp
    def _update_ytdlp(self, force: bool) -> None:
        channel = self.settings.update_channel
        repo = YTDLP_REPOS.get(channel, YTDLP_REPOS["stable"])
        self._emit("yt-dlp の更新を確認中…")
        tag = github_latest_tag(repo)
        target = BIN_DIR / "yt-dlp.exe"
        if (not force and target.exists() and self.versions.get("yt-dlp") == tag
                and self.versions.get("yt-dlp_channel") == channel):
            return
        base = f"https://github.com/{repo}/releases/download/{tag}"
        sums = http_get(f"{base}/SHA2-256SUMS").decode("utf-8", "replace")
        expected = next((ln.split()[0] for ln in sums.splitlines() if ln.strip().endswith(" yt-dlp.exe")), None)
        if not expected:
            raise RuntimeError("チェックサムが見つかりません")
        tmp = BIN_DIR / "yt-dlp.exe.download"
        try:
            got = download_file(f"{base}/yt-dlp.exe", tmp, self._progress_cb(f"yt-dlp {tag} を取得中"),
                                self.cancel_event)
            if got.lower() != expected.lower():
                raise RuntimeError("チェックサムが一致しません")
            run_quiet([str(tmp), "--version"], timeout=60)
            os.replace(tmp, target)
        finally:
            tmp.unlink(missing_ok=True)
        self.versions["yt-dlp"] = tag
        self.versions["yt-dlp_channel"] = channel
        log.info("yt-dlp を %s (%s) に更新", tag, channel)

    # FFmpeg
    def _update_ffmpeg(self, force: bool) -> None:
        self._emit("FFmpeg の更新を確認中…")
        ver = http_get(FFMPEG_VERSION_URL).decode("ascii", "replace").strip()
        if not re.fullmatch(r"\d+(\.\d+)*", ver):
            raise RuntimeError(f"版番号を読めません: {ver[:20]!r}")
        if (not force and (BIN_DIR / "ffmpeg.exe").exists() and (BIN_DIR / "ffprobe.exe").exists()
                and self.versions.get("ffmpeg") == ver):
            return
        m = HEX64.search(http_get(FFMPEG_ZIP_URL + ".sha256").decode("ascii", "replace"))
        if not m:
            raise RuntimeError("チェックサムが見つかりません")
        tmp_zip = BIN_DIR / "ffmpeg.zip.download"
        new_files: list[tuple[Path, Path]] = []
        try:
            got = download_file(FFMPEG_ZIP_URL, tmp_zip, self._progress_cb(f"FFmpeg {ver} を取得中"),
                                self.cancel_event, timeout=60)
            if got.lower() != m.group(0).lower():
                raise RuntimeError("チェックサムが一致しません")
            self._emit("FFmpeg を展開中…")
            with zipfile.ZipFile(tmp_zip) as z:
                for name in ("ffmpeg.exe", "ffprobe.exe"):
                    member = next((n for n in z.namelist() if n.endswith("/bin/" + name)), None)
                    if not member:
                        raise RuntimeError(f"{name} が zip 内にありません")
                    tmp = BIN_DIR / (name + ".download")
                    with z.open(member) as src, open(tmp, "wb") as dst:
                        shutil.copyfileobj(src, dst, 1024 * 1024)
                    new_files.append((tmp, BIN_DIR / name))
            run_quiet([str(new_files[0][0]), "-version"])
            for tmp, final in new_files:
                os.replace(tmp, final)
        finally:
            tmp_zip.unlink(missing_ok=True)
            for tmp, _ in new_files:
                tmp.unlink(missing_ok=True)
        self.versions["ffmpeg"] = ver
        log.info("FFmpeg を %s に更新", ver)

    # Deno（yt-dlp が YouTube の解析に使う JavaScript 実行環境）
    def _update_deno(self, force: bool) -> None:
        self._emit("Deno の更新を確認中…")
        tag = github_latest_tag(DENO_REPO)
        ver = tag.lstrip("v")
        target = BIN_DIR / "deno.exe"
        if not force and target.exists() and self.versions.get("deno") == ver:
            return
        base = f"https://github.com/{DENO_REPO}/releases/download/{tag}"
        m = HEX64.search(http_get(f"{base}/{DENO_ASSET}.sha256sum").decode("utf-8", "replace"))
        if not m:
            raise RuntimeError("チェックサムが見つかりません")
        tmp_zip = BIN_DIR / "deno.zip.download"
        tmp_exe = BIN_DIR / "deno.exe.download"
        try:
            got = download_file(f"{base}/{DENO_ASSET}", tmp_zip, self._progress_cb(f"Deno {ver} を取得中"),
                                self.cancel_event, timeout=60)
            if got.lower() != m.group(0).lower():
                raise RuntimeError("チェックサムが一致しません")
            with zipfile.ZipFile(tmp_zip) as z, z.open("deno.exe") as src, open(tmp_exe, "wb") as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)
            run_quiet([str(tmp_exe), "--version"])
            os.replace(tmp_exe, target)
        finally:
            tmp_zip.unlink(missing_ok=True)
            tmp_exe.unlink(missing_ok=True)
        self.versions["deno"] = ver
        log.info("Deno を %s に更新", ver)


def _short_error(e: Exception) -> str:
    text = str(e) or e.__class__.__name__
    if "urlopen error" in text or "timed out" in text or "getaddrinfo" in text:
        return "ネットに接続できません"
    return text[:80]
