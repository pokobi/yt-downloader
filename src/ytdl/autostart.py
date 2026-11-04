"""Windows ログイン時の自動起動（HKCU\\...\\Run に登録。管理者権限は不要）。"""
import logging
import sys
import winreg
from pathlib import Path

from ytdl import APP_ID
from ytdl.paths import app_root, is_frozen

log = logging.getLogger(__name__)
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def command_line() -> str:
    if is_frozen():
        return f'"{sys.executable}" --tray'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{exe}" "{app_root() / "run.pyw"}" --tray'


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            value, _ = winreg.QueryValueEx(k, APP_ID)
            return bool(value)
    except OSError:
        return False


def set_enabled(enabled: bool) -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if enabled:
                winreg.SetValueEx(k, APP_ID, 0, winreg.REG_SZ, command_line())
            else:
                try:
                    winreg.DeleteValue(k, APP_ID)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        log.exception("自動起動の設定に失敗しました")
        return False
