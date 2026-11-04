"""Windows のタイトルバー（ウィンドウ上部の枠）をアプリの配色に合わせる。

- Windows 11: DWM でタイトルバーの背景色・文字色・枠線色を直接指定する
- Windows 10 (1809 以降): ダークモードのタイトルバーに切り替える（色は黒系で固定）
すべてのトップレベルウィンドウ（メイン・設定・ログ・確認ダイアログ）に自動で適用する。
"""
import ctypes
from ctypes import wintypes

from PySide6.QtCore import QEvent, QObject

from ytdl.ui import style

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19  # Windows 10 1809〜1909
DWMWA_BORDER_COLOR = 34
DWMWA_CAPTION_COLOR = 35
DWMWA_TEXT_COLOR = 36


def _colorref(hex_color: str) -> int:
    """'#RRGGBB' → Windows の COLORREF (0x00BBGGRR)。"""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (b << 16) | (g << 8) | r


try:
    _dwm = ctypes.windll.dwmapi
    _dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    _dwm.DwmSetWindowAttribute.restype = ctypes.c_long
except (AttributeError, OSError):
    _dwm = None


def _set(hwnd: int, attr: int, value: int) -> bool:
    v = wintypes.DWORD(value)
    return _dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v)) == 0


def apply_titlebar(widget) -> None:
    if _dwm is None:
        return
    try:
        hwnd = int(widget.winId())
    except Exception:
        return
    if not _set(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, 1):
        _set(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE_OLD, 1)
    # 以下は Windows 11 だけで効く（10 では失敗するが問題なし）
    _set(hwnd, DWMWA_CAPTION_COLOR, _colorref(style.BG))
    _set(hwnd, DWMWA_TEXT_COLOR, _colorref(style.TEXT))
    _set(hwnd, DWMWA_BORDER_COLOR, _colorref(style.BORDER))


class TitleBarStyler(QObject):
    """アプリ全体のイベントを見て、新しく表示されたウィンドウに配色を当てる。"""

    def eventFilter(self, obj, event):  # noqa: N802
        if event.type() == QEvent.Type.Show and getattr(obj, "isWindow", None) and obj.isWindow():
            if not obj.property("_ytdl_titlebar"):
                obj.setProperty("_ytdl_titlebar", True)
                apply_titlebar(obj)
        return False
