"""アプリが使うフォルダの場所をまとめる。

カレントフォルダに依存しないよう、すべて絶対パスで決める。
- 設定:        %APPDATA%\\YTDownloader\\settings.json
- ツール類:    %LOCALAPPDATA%\\YTDownloader\\bin  (yt-dlp.exe / ffmpeg.exe / ffprobe.exe / deno.exe)
- キャッシュ:  %LOCALAPPDATA%\\YTDownloader\\cache
- ログ:        %LOCALAPPDATA%\\YTDownloader\\logs
"""
import os
import sys
from pathlib import Path

from ytdl import APP_ID


def _env_dir(var: str, fallback: Path) -> Path:
    value = os.environ.get(var)
    return Path(value) if value else fallback


ROAMING_DIR = _env_dir("APPDATA", Path.home() / "AppData" / "Roaming") / APP_ID
if os.environ.get("YTDL_SETTINGS_DIR"):  # テスト用：設定だけ別の場所を使う
    ROAMING_DIR = Path(os.environ["YTDL_SETTINGS_DIR"])
LOCAL_DIR = _env_dir("LOCALAPPDATA", Path.home() / "AppData" / "Local") / APP_ID

SETTINGS_FILE = ROAMING_DIR / "settings.json"
BIN_DIR = LOCAL_DIR / "bin"
CACHE_DIR = LOCAL_DIR / "cache"
LOG_DIR = LOCAL_DIR / "logs"
VERSIONS_FILE = BIN_DIR / "versions.json"

ASSETS_DIR = Path(__file__).resolve().parent / "assets"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_root() -> Path:
    """exe 版なら exe のあるフォルダ、開発版ならプロジェクトのルート。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent.parent


def extension_dir() -> Path:
    return app_root() / "extension"


def default_download_dir() -> Path:
    """Windows の「ダウンロード」フォルダ（場所を変えている場合も追従）。"""
    try:
        import ctypes
        from ctypes import wintypes
        import uuid

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                        ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

        u = uuid.UUID("{374DE290-123F-4565-9164-39C4925E467B}")  # FOLDERID_Downloads
        guid = GUID(u.fields[0], u.fields[1], u.fields[2],
                    (ctypes.c_ubyte * 8).from_buffer_copy(u.bytes[8:]))
        out = ctypes.c_wchar_p()
        shell32 = ctypes.windll.shell32
        shell32.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(GUID), wintypes.DWORD,
                                                 wintypes.HANDLE, ctypes.POINTER(ctypes.c_wchar_p)]
        if shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(out)) == 0:
            path = Path(out.value)
            ctypes.windll.ole32.CoTaskMemFree(out)
            return path
    except Exception:
        pass
    return Path.home() / "Downloads"


def ensure_dirs() -> None:
    for d in (ROAMING_DIR, BIN_DIR, CACHE_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)
