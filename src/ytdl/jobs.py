"""ダウンロードのキュー管理。

yt-dlp は別プロセス（yt-dlp.exe）として動かす。万一 yt-dlp が落ちてもアプリ本体は無事で、
キャンセルはプロセスごと確実に止められる。進み具合は --progress-template で
機械的に読める形にして受け取る。
"""
import collections
import itertools
import json
import logging
import os
import subprocess
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Qt, Signal

from ytdl.net import http_get
from ytdl.paths import BIN_DIR, CACHE_DIR
from ytdl.tools import CREATE_NO_WINDOW

log = logging.getLogger(__name__)

QUEUED, RUNNING, POST, DONE, ERROR, CANCELLED = "queued", "running", "post", "done", "error", "cancelled"
ACTIVE_STATES = (QUEUED, RUNNING, POST)
FINAL_STATES = (DONE, ERROR, CANCELLED)

P_MARK, PP_MARK, INFO_MARK, FILE_MARK = "__YTDL_P__", "__YTDL_PP__", "__YTDL_INFO__", "__YTDL_FILE__"
POSTPROCESSOR_LABELS = {
    "Merger": "映像と音声を結合中", "ExtractAudio": "音声に変換中", "EmbedThumbnail": "サムネイルを埋め込み中",
    "FFmpegMetadata": "メタデータを書き込み中", "Metadata": "メタデータを書き込み中",
    "SponsorBlock": "SponsorBlock を処理中", "ModifyChapters": "不要な区間を削除中",
    "FixupM3u8": "ファイルを修正中", "VideoRemuxer": "形式を変換中", "MoveFiles": "仕上げ中",
}
_ids = itertools.count(1)


def normalize_url(text: str) -> Optional[str]:
    text = text.strip().strip("<>\"'")
    if not text:
        return None
    if text.startswith(("www.", "youtu", "x.com/", "twitter.com/", "mobile.x.com/")):
        text = "https://" + text
    try:
        u = urllib.parse.urlparse(text)
    except ValueError:
        return None
    if u.scheme not in ("http", "https") or not u.netloc or len(text) > 4000:
        return None
    return text


X_HOSTS = ("x.com", "twitter.com", "mobile.x.com", "mobile.twitter.com", "www.x.com", "www.twitter.com")


def is_x_post(url: str) -> bool:
    """X（旧 Twitter）の投稿の URL か。"""
    try:
        u = urllib.parse.urlparse(url)
    except ValueError:
        return False
    return (u.hostname or "").lower() in X_HOSTS and "/status/" in u.path


def extract_urls(text: str) -> list[str]:
    urls = []
    for part in text.replace("\r", "\n").replace("\t", "\n").replace(" ", "\n").split("\n"):
        url = normalize_url(part)
        if url and url not in urls:
            urls.append(url)
    return urls


@dataclass
class Job:
    url: str
    mode: str  # "video" / "audio"
    playlist: bool
    items: int = 0  # X の複数動画の投稿で、何本目だけを取るか（0 は全部）
    id: str = field(default_factory=lambda: f"j{next(_ids)}")
    title: str = ""
    uploader: str = ""
    thumb_url: str = ""
    video_id: str = ""
    summary: str = ""
    status: str = QUEUED
    stage: str = "待機中"
    progress: float = 0.0
    speed: str = ""
    eta: str = ""
    item_index: int = 0
    item_count: int = 0
    files: list = field(default_factory=list)
    error: str = ""
    log: collections.deque = field(default_factory=lambda: collections.deque(maxlen=500))
    created: float = field(default_factory=time.time)
    # 内部用
    proc: Optional[subprocess.Popen] = None
    cancel_requested: bool = False
    parts: int = 1
    part_index: int = 0

    @property
    def display_title(self) -> str:
        return self.title or self.url

    @property
    def active(self) -> bool:
        return self.status in ACTIVE_STATES

    def to_api(self) -> dict:
        return {"id": self.id, "title": self.display_title, "status": self.status, "stage": self.stage,
                "progress": round(self.progress, 3), "mode": self.mode, "error": self.error}


def build_command(job: Job, s, tools) -> list[str]:
    """設定から yt-dlp のコマンドラインを組み立てる。"""
    ytdlp = str(tools.ytdlp.path)
    cmd = [ytdlp, "--ignore-config", "--no-colors", "--newline", "--encoding", "utf-8",
           "--no-simulate", "--no-quiet", "--progress",
           "--cache-dir", str(CACHE_DIR / "yt-dlp"),
           "--no-mtime", "--trim-filenames", "150", "--windows-filenames",
           "--extractor-retries", "3", "--concurrent-fragments", "4",
           "-P", s.save_dir]
    if tools.ffmpeg.ok:
        cmd += ["--ffmpeg-location", str(tools.ffmpeg.path.parent)]
    if tools.deno.ok:
        cmd += ["--js-runtimes", f"deno:{tools.deno.path}"]
    if s.cookies_browser:
        cmd += ["--cookies-from-browser", s.cookies_browser]

    x_post = is_x_post(job.url)
    names = {"title_id": "%(title)s [%(id)s]", "uploader_title": "%(uploader|不明)s - %(title)s"}
    if x_post:
        # X の動画にはタイトルがなく、yt-dlp が「投稿者 - 本文の冒頭」をタイトルにする
        # （複数動画なら末尾に #番号）。投稿者を重ねて付けないようにする
        names.pop("uploader_title")
    base = names.get(s.filename, "%(title)s")
    if x_post:
        # 1 つの投稿の動画は、プレイリスト用のフォルダを作らずにそのまま並べる
        if job.items:
            cmd += ["--yes-playlist", "--playlist-items", str(job.items)]
        cmd += ["-o", f"{base}.%(ext)s"]
    elif job.playlist:
        cmd += ["--yes-playlist", "-o",
                f"%(playlist_title|)s/%(playlist_index&{{}} - |)s{base}.%(ext)s"]
    else:
        cmd += ["--no-playlist", "-o", f"{base}.%(ext)s"]

    if job.mode == "audio":
        cmd += ["-f", "ba/b", "-x"]
        if s.audio_format != "best":
            cmd += ["--audio-format", s.audio_format]
            if s.audio_format in ("mp3", "m4a", "opus"):
                cmd += ["--audio-quality", f"{s.audio_quality}K"]
        if s.embed_thumbnail and s.audio_format != "wav":
            cmd += ["--embed-thumbnail"]
    else:
        height = "" if s.video_quality == "best" else f":{s.video_quality}"
        if s.video_codec == "h264" and s.video_container != "webm":
            # H.264 を解像度より優先する（YouTube の H.264 は多くが 1080p まで）
            sort = f"vcodec:h264,res{height},acodec:aac"
        else:
            sort = {"mp4": f"res{height},ext:mp4:m4a", "webm": f"res{height},ext:webm:webm"}.get(
                s.video_container, f"res{height}")
        merge = {"mp4": "mp4/mkv", "webm": "webm/mkv"}.get(s.video_container, "mkv")
        cmd += ["-f", "bv*+ba/b", "-S", sort, "--merge-output-format", merge]
        if s.embed_thumbnail and s.video_container != "webm":
            cmd += ["--embed-thumbnail"]
    if s.embed_metadata:
        cmd += ["--embed-metadata"]
    if s.sponsorblock:
        cats = "sponsor,selfpromo,interaction" + (",music_offtopic" if job.mode == "audio" else "")
        cmd += ["--sponsorblock-remove", cats]

    cmd += [
        "--progress-template",
        f"download:{P_MARK}%(progress.status)s|%(progress.downloaded_bytes)s|%(progress.total_bytes)s|"
        f"%(progress.total_bytes_estimate)s|%(progress.speed)s|%(progress.eta)s|"
        f"%(progress.fragment_index)s|%(progress.fragment_count)s",
        "--progress-template", f"postprocess:{PP_MARK}%(progress.status)s|%(progress.postprocessor)s",
        "--print", f"before_dl:{INFO_MARK}%(.{{id,title,uploader,thumbnail,format_id,playlist_index,"
                   f"n_entries,playlist_title}})j",
        "--print", f"after_move:{FILE_MARK}%(filepath)j",
        "--", job.url,
    ]
    return cmd


def _num(v: str) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fmt_speed(bps: Optional[float]) -> str:
    if not bps:
        return ""
    if bps >= 1048576:
        return f"{bps / 1048576:.1f} MB/s"
    return f"{bps / 1024:.0f} KB/s"


def _fmt_eta(sec: Optional[float]) -> str:
    if sec is None:
        return ""
    sec = int(sec)
    if sec >= 3600:
        return f"残り {sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}"
    return f"残り {sec // 60}:{sec % 60:02d}"


ERROR_HINTS = [
    ("Sign in to confirm", "YouTube にボット判定されました。設定でブラウザの Cookie を使うか、時間をおいて再試行してください。"),
    ("Private video", "非公開の動画です。"),
    ("Video unavailable", "動画が見つかりません（削除・非公開・地域制限、または URL の間違い）。"),
    ("This video is unavailable", "動画が見つかりません（削除・非公開・地域制限、または URL の間違い）。"),
    ("Incomplete YouTube ID", "URL が途中で切れています。"),
    ("members-only", "メンバー限定の動画です。設定でブラウザの Cookie を使うと取得できる場合があります。"),
    ("age", "年齢制限があります。設定でブラウザの Cookie を使うと取得できる場合があります。"),
    ("HTTP Error 403", "アクセスを拒否されました。ツールの更新後に再試行してください。"),
    ("Requested format is not available", "選んだ形式がありません。画質や形式を変えて再試行してください。"),
    ("Unsupported URL", "対応していない URL です。"),
    ("NSFW tweet requires authentication", "センシティブな内容の投稿のため、X へのログインが必要です。設定でブラウザの Cookie を使うと取得できる場合があります。"),
    ("only be available when logged in", "X へのログインが必要な投稿です。設定でブラウザの Cookie を使うと取得できる場合があります。"),
    ("No video could be found in this tweet", "この投稿には動画がありません。"),
    ("Requested tweet is unavailable", "投稿が見つかりません（削除・非公開、または URL の間違い）。"),
    ("could not find", "ブラウザの Cookie を読めませんでした。ブラウザを閉じてから再試行してください。"),
    ("Failed to decrypt", "ブラウザの Cookie を読めませんでした（暗号化のため）。Firefox か「使わない」を選んでください。"),
]


def error_hint(message: str) -> str:
    low = message.lower()
    for key, hint in ERROR_HINTS:
        if key.lower() in low:
            return hint
    return ""


class DownloadManager(QObject):
    job_added = Signal(object)
    job_changed = Signal(object)
    job_removed = Signal(str)
    job_finished = Signal(object)
    thumb_loaded = Signal(str, bytes)
    counts_changed = Signal()
    _pump_request = Signal()  # どのスレッドから emit しても、メインスレッドで _pump が動く

    def __init__(self, settings, tools):
        super().__init__()
        self.settings = settings
        self.tools = tools
        self.jobs: dict[str, Job] = {}
        self._lock = threading.RLock()
        self._pump_request.connect(self._pump, Qt.ConnectionType.QueuedConnection)

    # ---------- 公開メソッド（メインスレッドから呼ぶ） ----------
    def add(self, url: str, mode: Optional[str] = None, playlist: Optional[bool] = None, items: int = 0) -> Job:
        mode = mode if mode in ("video", "audio") else self.settings.default_mode
        if playlist is None:
            playlist = self.settings.playlist
        job = Job(url=url, mode=mode, playlist=bool(playlist), items=max(0, int(items or 0)),
                  summary=self.settings.summary(mode))
        with self._lock:
            self.jobs[job.id] = job
        log.info("追加: %s (%s)", url, mode)
        self.job_added.emit(job)
        self.counts_changed.emit()
        self.schedule_pump()
        return job

    def cancel(self, job_id: str) -> None:
        job = self.jobs.get(job_id)
        if not job or not job.active:
            return
        job.cancel_requested = True
        if job.status == QUEUED:
            self._finish(job, CANCELLED, "キャンセルしました")
        elif job.proc and job.proc.poll() is None:
            job.stage = "キャンセル中…"
            self.job_changed.emit(job)
            _kill_tree(job.proc.pid)

    def cancel_all(self) -> None:
        for job in list(self.jobs.values()):
            self.cancel(job.id)

    def retry(self, job_id: str) -> None:
        job = self.jobs.get(job_id)
        if not job or job.active:
            return
        job.status, job.stage, job.progress, job.error = QUEUED, "待機中", 0.0, ""
        job.speed = job.eta = ""
        job.cancel_requested = False
        job.files.clear()
        job.summary = self.settings.summary(job.mode)
        self.job_changed.emit(job)
        self.counts_changed.emit()
        self.schedule_pump()

    def remove(self, job_id: str) -> None:
        job = self.jobs.get(job_id)
        if not job:
            return
        if job.active:
            self.cancel(job_id)
            if job.active:
                return
        with self._lock:
            self.jobs.pop(job_id, None)
        self.job_removed.emit(job_id)
        self.counts_changed.emit()

    def clear_finished(self) -> None:
        for job in list(self.jobs.values()):
            if job.status in FINAL_STATES:
                self.remove(job.id)

    def all_jobs(self) -> list:
        """別スレッドから呼んでも安全なコピー。"""
        with self._lock:
            return list(self.jobs.values())

    def active_count(self) -> int:
        return sum(1 for j in self.all_jobs() if j.active)

    def running_count(self) -> int:
        return sum(1 for j in self.all_jobs() if j.status in (RUNNING, POST))

    def schedule_pump(self) -> None:
        self._pump_request.emit()

    # ---------- 内部 ----------
    def _pump(self) -> None:
        if self.tools.updating:
            for j in self.jobs.values():
                if j.status == QUEUED and j.stage != "ツールの更新を待っています":
                    j.stage = "ツールの更新を待っています"
                    self.job_changed.emit(j)
            return  # 更新が終わると update_finished から再度呼ばれる
        if not self.tools.ready:
            for j in list(self.jobs.values()):
                if j.status == QUEUED:
                    self._finish(j, ERROR, "yt-dlp を用意できていません。ネット接続を確認して「ツールを更新」を押してください")
            return
        limit = max(1, min(5, int(self.settings.concurrency)))
        queued = sorted((j for j in self.jobs.values() if j.status == QUEUED), key=lambda j: j.created)
        free = limit - self.running_count()
        for job in queued[:max(0, free)]:
            job.status, job.stage = RUNNING, "情報を取得中…"
            self.job_changed.emit(job)
            threading.Thread(target=self._worker, args=(job,), daemon=True, name=f"dl-{job.id}").start()
        for job in queued[max(0, free):]:
            if job.stage != "順番待ち":
                job.stage = "順番待ち"
                self.job_changed.emit(job)
        self.counts_changed.emit()

    def _finish(self, job: Job, status: str, stage: str, error: str = "") -> None:
        job.status, job.stage, job.error = status, stage, error
        job.speed = job.eta = ""
        if status == DONE:
            job.progress = 1.0
        self.job_changed.emit(job)
        self.job_finished.emit(job)
        self.counts_changed.emit()
        self.schedule_pump()

    def _worker(self, job: Job) -> None:
        try:
            Path(self.settings.save_dir).mkdir(parents=True, exist_ok=True)
            cmd = build_command(job, self.settings, self.tools)
            job.log.append("$ " + " ".join(f'"{c}"' if " " in c else c for c in cmd))
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"
            env["PATH"] = str(BIN_DIR) + os.pathsep + env.get("PATH", "")
            job.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        stdin=subprocess.DEVNULL, env=env, cwd=self.settings.save_dir,
                                        creationflags=CREATE_NO_WINDOW)
        except Exception as e:
            log.exception("yt-dlp を起動できません")
            self._finish(job, ERROR, "起動に失敗", str(e))
            return

        last_emit = 0.0
        last_error = ""
        assert job.proc.stdout is not None
        for raw in job.proc.stdout:
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if not line:
                continue
            changed = self._parse_line(job, line)
            if line.startswith("ERROR:"):
                last_error = line[6:].strip()
            if not line.startswith(P_MARK):
                job.log.append(line)
            now = time.monotonic()
            if changed and (now - last_emit > 0.15 or job.status == POST):
                last_emit = now
                self.job_changed.emit(job)
        code = job.proc.wait()
        job.proc = None

        if job.cancel_requested:
            self._finish(job, CANCELLED, "キャンセルしました")
        elif code == 0 or (job.files and not last_error):
            n = len(job.files)
            self._finish(job, DONE, "完了" if n <= 1 else f"完了（{n} 件）")
        elif job.files:
            self._finish(job, ERROR, f"一部失敗（{len(job.files)} 件は完了）", last_error)
        else:
            self._finish(job, ERROR, "失敗", last_error or f"yt-dlp が終了コード {code} で止まりました")

    def _parse_line(self, job: Job, line: str) -> bool:
        if line.startswith(P_MARK):
            parts = line[len(P_MARK):].split("|")
            if len(parts) < 8:
                return False
            status, done, total, est, speed, eta, fi, fc = parts[:8]
            d, t, e = _num(done), _num(total), _num(est)
            frac = None
            if d is not None and (t or e):
                frac = min(1.0, d / (t or e))
            elif _num(fi) and _num(fc):
                frac = min(1.0, _num(fi) / _num(fc))
            if status == "finished":
                job.part_index = min(job.parts, job.part_index + 1)
                frac = 0.0 if job.part_index < job.parts else 1.0
            if frac is not None:
                overall = (min(job.part_index, job.parts - 1) + frac) / job.parts if job.parts > 1 else frac
                job.progress = max(0.0, min(1.0, overall))
            job.speed, job.eta = _fmt_speed(_num(speed)), _fmt_eta(_num(eta))
            if job.status != POST:
                if job.parts > 1:
                    job.stage = "映像を取得中" if job.part_index == 0 else "音声を取得中"
                else:
                    job.stage = "ダウンロード中"
            return True
        if line.startswith(PP_MARK):
            status, _, name = line[len(PP_MARK):].partition("|")
            job.status = POST
            job.stage = POSTPROCESSOR_LABELS.get(name.strip(), "処理中") + "…"
            job.speed = job.eta = ""
            return True
        if line.startswith(INFO_MARK):
            try:
                info = json.loads(line[len(INFO_MARK):])
            except ValueError:
                return False
            job.status = RUNNING
            job.title = info.get("title") or job.title
            job.uploader = info.get("uploader") or ""
            fmt = str(info.get("format_id") or "")
            job.parts = fmt.count("+") + 1 if fmt else 1
            job.part_index = 0
            job.progress = 0.0
            idx, cnt = info.get("playlist_index"), info.get("n_entries")
            if job.playlist and isinstance(idx, int) and isinstance(cnt, int) and cnt > 1:
                job.item_index, job.item_count = idx, cnt
            vid = str(info.get("id") or "")
            thumb = info.get("thumbnail") or ""
            if vid and vid != job.video_id:
                job.video_id = vid
                self._load_thumb(job, vid, thumb)
            job.stage = "ダウンロード中"
            return True
        if line.startswith(FILE_MARK):
            try:
                path = json.loads(line[len(FILE_MARK):])
                if isinstance(path, str):
                    job.files.append(path)
            except ValueError:
                pass
            return True
        if line.startswith("[download] Downloading item "):
            # 例: [download] Downloading item 2 of 10
            try:
                nums = line.split("item ", 1)[1].split(" of ")
                job.item_index, job.item_count = int(nums[0]), int(nums[1])
                return True
            except (IndexError, ValueError):
                return False
        return False

    def _load_thumb(self, job: Job, vid: str, thumb: str) -> None:
        if "youtube" in job.url or "youtu.be" in job.url:
            candidates = [f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"]
        else:
            candidates = []
        if thumb and thumb.startswith("http"):
            candidates.append(thumb)
        job.thumb_url = candidates[0] if candidates else ""

        def run():
            for url in candidates:
                try:
                    data = http_get(url, timeout=10, limit=3_000_000)
                    if data:
                        self.thumb_loaded.emit(job.id, data)
                        return
                except Exception:
                    continue
        if candidates:
            threading.Thread(target=run, daemon=True).start()


def probe_post(url: str, s, tools, timeout: float = 20.0) -> dict:
    """X の投稿に動画が何本あるかを yt-dlp に調べさせる（ダウンロードはしない）。"""
    if not tools.ready:
        return {"ok": False, "error": "yt-dlp を用意できていません"}
    cmd = [str(tools.ytdlp.path), "--ignore-config", "--no-colors", "--encoding", "utf-8",
           "--cache-dir", str(CACHE_DIR / "yt-dlp"), "--flat-playlist", "--yes-playlist", "-J"]
    if s.cookies_browser:
        cmd += ["--cookies-from-browser", s.cookies_browser]
    cmd += ["--", url]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL,
                           env=env, creationflags=CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "動画の本数を確認できませんでした（時間切れ）"}
    except OSError as e:
        return {"ok": False, "error": f"yt-dlp を起動できません（{e}）"}
    out = r.stdout.decode("utf-8", "replace").strip()
    if r.returncode != 0 or not out.startswith("{"):
        err = r.stderr.decode("utf-8", "replace")
        last = next((ln[6:].strip() for ln in reversed(err.splitlines()) if ln.startswith("ERROR:")), "")
        return {"ok": False, "error": error_hint(last) or last or "動画の本数を確認できませんでした"}
    try:
        info = json.loads(out)
    except ValueError:
        return {"ok": False, "error": "動画の本数を確認できませんでした"}
    if info.get("_type") == "playlist":
        count = len(info.get("entries") or [])
    else:
        count = 1 if info.get("formats") or info.get("url") else 0
    if count == 0:
        return {"ok": False, "error": "この投稿には動画がありません。"}
    return {"ok": True, "count": count}


def _kill_tree(pid: int) -> None:
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True,
                       timeout=15, creationflags=CREATE_NO_WINDOW)
    except Exception:
        log.exception("プロセスを止められません: %s", pid)
