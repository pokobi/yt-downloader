"""設定の読み書き。壊れたファイルや未知の値があっても既定値で起動できるようにする。"""
import json
import logging
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from ytdl.paths import SETTINGS_FILE, default_download_dir

log = logging.getLogger(__name__)

CHOICES = {
    "default_mode": ["video", "audio"],
    "video_quality": ["best", "2160", "1440", "1080", "720", "480"],
    "video_container": ["mp4", "mkv", "webm"],
    "video_codec": ["auto", "h264"],
    "audio_format": ["mp3", "m4a", "opus", "flac", "wav", "best"],
    "audio_quality": ["320", "256", "192", "128"],
    "filename": ["title", "title_id", "uploader_title"],
    "cookies_browser": ["", "vivaldi", "chrome", "edge", "firefox", "brave"],
    "update_channel": ["stable", "nightly"],
}

LABELS = {
    "default_mode": {"video": "動画", "audio": "音声"},
    "video_quality": {"best": "最高画質", "2160": "2160p (4K)", "1440": "1440p", "1080": "1080p",
                      "720": "720p", "480": "480p"},
    "video_container": {"mp4": "MP4", "mkv": "MKV", "webm": "WebM"},
    "video_codec": {"auto": "自動（画質優先・AV1/VP9 になることあり）",
                    "h264": "H.264 優先（互換性重視・最大 1080p 程度）"},
    "audio_format": {"mp3": "MP3", "m4a": "M4A (AAC)", "opus": "Opus", "flac": "FLAC (可逆)",
                     "wav": "WAV (非圧縮)", "best": "変換しない (元の音声)"},
    "audio_quality": {"320": "320 kbps", "256": "256 kbps", "192": "192 kbps", "128": "128 kbps"},
    "filename": {"title": "タイトル", "title_id": "タイトル [ID]", "uploader_title": "投稿者 - タイトル"},
    "cookies_browser": {"": "使わない", "vivaldi": "Vivaldi", "chrome": "Chrome", "edge": "Edge",
                        "firefox": "Firefox", "brave": "Brave"},
    "update_channel": {"stable": "安定版 (おすすめ)", "nightly": "ナイトリー (最新の修正をすぐ反映)"},
}

# 以前のアプリ（customtkinter 版）の設定ファイル。初回起動時だけ引き継ぐ。
OLD_SETTINGS_CANDIDATES = [Path(r"A:\ダウンロード\ytdownload\ytdlp_pro_settings.json")]


@dataclass
class Settings:
    save_dir: str = ""
    default_mode: str = "video"
    video_quality: str = "best"
    video_container: str = "mp4"
    video_codec: str = "auto"
    audio_format: str = "mp3"
    audio_quality: str = "320"
    filename: str = "title"
    playlist: bool = False
    embed_metadata: bool = True
    embed_thumbnail: bool = True
    sponsorblock: bool = False
    cookies_browser: str = ""
    concurrency: int = 2
    notify: bool = True
    sound: bool = True
    autostart: bool = True
    auto_update: bool = True
    update_channel: str = "stable"
    window_geometry: str = ""
    tray_hint_shown: bool = False

    # ---------- 読み込み / 保存 ----------
    @classmethod
    def load(cls) -> "Settings":
        s = cls()
        data = None
        if SETTINGS_FILE.exists():
            try:
                # utf-8-sig: メモ帳などで保存して BOM が付いても読めるようにする
                data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8-sig"))
            except Exception:
                log.exception("設定ファイルが壊れているため既定値で起動します")
                try:
                    SETTINGS_FILE.replace(SETTINGS_FILE.with_suffix(".broken.json"))
                except OSError:
                    pass
        if isinstance(data, dict):
            s._apply_dict(data)
        else:
            s._migrate_old()
        if not s.save_dir or not Path(s.save_dir).is_dir():
            s.save_dir = str(default_download_dir())
        s.save()
        return s

    def _apply_dict(self, data: dict) -> None:
        for f in fields(self):
            if f.name not in data:
                continue
            value = data[f.name]
            default = getattr(self, f.name)
            if isinstance(default, bool):
                if isinstance(value, bool):
                    setattr(self, f.name, value)
            elif isinstance(default, int):
                if isinstance(value, int) and not isinstance(value, bool):
                    setattr(self, f.name, value)
            elif isinstance(value, str):
                if f.name in CHOICES and value not in CHOICES[f.name]:
                    continue
                setattr(self, f.name, value)
        self.concurrency = max(1, min(5, self.concurrency))

    def _migrate_old(self) -> None:
        for path in OLD_SETTINGS_CANDIDATES:
            try:
                if not path.exists():
                    continue
                old = json.loads(path.read_text(encoding="utf-8-sig"))
            except Exception:
                continue
            log.info("以前の設定を引き継ぎます: %s", path)
            if isinstance(old.get("save_dir"), str):
                self.save_dir = old["save_dir"]
            is_audio = old.get("mode") == "音声抽出"
            self.default_mode = "audio" if is_audio else "video"
            fmt = str(old.get("format", "")).lower()
            if is_audio and fmt in CHOICES["audio_format"]:
                self.audio_format = fmt
            if not is_audio and fmt in CHOICES["video_container"]:
                self.video_container = fmt
            q = str(old.get("audio_quality", "")).replace("kbps", "")
            if q in CHOICES["audio_quality"]:
                self.audio_quality = q
            res = str(old.get("resolution", "")).replace("p", "")
            if res in CHOICES["video_quality"]:
                self.video_quality = res
            self.filename = {"タイトル+ID": "title_id", "投稿者-タイトル": "uploader_title"}.get(
                old.get("filename_tmpl"), "title")
            for new, key in (("playlist", "playlist"), ("sponsorblock", "sponsorblock"),
                             ("embed_metadata", "embed_meta"), ("sound", "play_sound")):
                if isinstance(old.get(key), bool):
                    setattr(self, new, old[key])
            cookie = old.get("browser_cookie")
            if cookie in CHOICES["cookies_browser"]:
                self.cookies_browser = cookie
            try:
                self.concurrency = max(1, min(5, int(old.get("workers", 2))))
            except (TypeError, ValueError):
                pass
            return

    def save(self) -> None:
        try:
            SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = SETTINGS_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, SETTINGS_FILE)
        except Exception:
            log.exception("設定の保存に失敗しました")

    # ---------- 表示用 ----------
    def label(self, key: str, value=None) -> str:
        v = getattr(self, key) if value is None else value
        return LABELS.get(key, {}).get(v, str(v))

    def summary(self, mode: str) -> str:
        if mode == "audio":
            if self.audio_format in ("flac", "wav", "best"):
                return self.label("audio_format")
            return f"{self.label('audio_format')} {self.audio_quality}kbps"
        codec = " H.264" if self.video_codec == "h264" else ""
        return f"{self.label('video_quality')} {self.label('video_container')}{codec}"
