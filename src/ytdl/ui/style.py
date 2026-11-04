"""配色とスタイル。

方向性（unslop by @heydamir の手順で決めたもの）
- 世界観：夜の録音ブース。背景は無彩色のグラファイト、色は「録音中の赤」1色だけ。
- 色を使うのは、一覧のサムネイル（動画そのものの色）と進捗バー、REC ランプの赤い点だけ。
- 余白は 4 の倍数。文字の太さは 400 と 600 だけで、階層は大きさと色で付ける。
"""
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QPalette

from ytdl.paths import CACHE_DIR

# グラファイトの段階（暗い順）
DEEP = "#0f0f10"
BG = "#141415"
SURFACE = "#19191b"
RAISED = "#232325"
RAISED_HOVER = "#2a2a2d"
HAIRLINE = "#2a2a2c"  # 文字色 8% 相当
HAIRLINE_STRONG = "#3a3a3d"

TEXT = "#ededed"
TEXT_2 = "#a1a1a6"
MUTED = "#85858b"

# 強調色：録音中の赤（白文字で 4.81:1）
ACCENT = "#d2364a"
ACCENT_HOVER = "#c42f43"
ACCENT_PRESSED = "#b42a3d"

# 意味を持つ色だけ
SUCCESS = "#4cc38a"
ERROR = "#e5484d"
WARNING = "#d9a441"

FONT_FAMILY = "Yu Gothic UI"

# 後方互換（他のモジュールから参照している名前）
SURFACE_2 = RAISED
SURFACE_3 = RAISED_HOVER
BORDER = HAIRLINE
ACCENT_2 = TEXT_2


def _check_image() -> str:
    """チェックボックスのチェックマーク画像を用意して、そのパスを返す。"""
    from ytdl.ui.icons import icon
    path = CACHE_DIR / "check.png"
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        icon("check", "#ffffff", 12).pixmap(QSize(12, 12), 2.0).save(str(path))
    except Exception:
        return ""
    return path.as_posix()


def build_qss() -> str:
    check = _check_image()
    check_rule = f"image: url({check});" if check else ""
    return f"""
* {{
    font-family: "{FONT_FAMILY}", "Segoe UI", sans-serif;
    font-size: 14px;
    color: {TEXT};
}}
QMainWindow, QDialog {{ background: {BG}; }}
QWidget#central {{ background: {BG}; }}
QToolTip {{ background: {RAISED}; color: {TEXT}; border: 1px solid {HAIRLINE_STRONG}; padding: 4px 8px; }}

QLabel#appTitle {{ font-size: 16px; font-weight: 600; }}
QLabel#muted {{ color: {MUTED}; font-size: 13px; }}
QLabel#secondary {{ color: {TEXT_2}; font-size: 13px; }}
QLabel#sectionTitle {{ font-size: 13px; color: {TEXT_2}; }}
QLabel#count {{ font-size: 13px; color: {MUTED}; }}
QLabel#emptyTitle {{ font-size: 16px; color: {TEXT_2}; }}
QLabel#status {{ font-size: 13px; color: {MUTED}; }}
QLabel#jobTitle {{ font-size: 14px; font-weight: 600; }}

QFrame#card {{ background: {SURFACE}; border: 1px solid {HAIRLINE}; border-radius: 12px; }}
QFrame#job {{ background: {SURFACE}; border: 1px solid {HAIRLINE}; border-radius: 12px; }}
QFrame#job:hover {{ background: #1c1c1e; border-color: {HAIRLINE_STRONG}; }}

QLineEdit, QComboBox {{
    background: {RAISED}; border: 1px solid {HAIRLINE}; border-radius: 8px;
    padding: 0px 12px; min-height: 34px; selection-background-color: {ACCENT};
}}
QLineEdit:focus, QComboBox:focus {{ border-color: {HAIRLINE_STRONG}; background: {RAISED_HOVER}; }}
QLineEdit#urlInput {{ min-height: 38px; font-size: 14px; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background: {RAISED}; border: 1px solid {HAIRLINE_STRONG}; selection-background-color: {RAISED_HOVER};
    outline: none; padding: 4px;
}}

QPushButton {{
    background: {RAISED}; border: 1px solid {HAIRLINE}; border-radius: 8px;
    padding: 0px 16px; min-height: 36px; color: {TEXT};
}}
QPushButton:hover {{ background: {RAISED_HOVER}; border-color: {HAIRLINE_STRONG}; }}
QPushButton:pressed {{ background: {SURFACE}; }}
QPushButton:disabled {{ color: {MUTED}; background: {SURFACE}; }}
QPushButton:focus {{ border-color: {TEXT_2}; }}
QPushButton#primary {{ background: {ACCENT}; border: 1px solid {ACCENT}; color: #ffffff; font-weight: 600; }}
QPushButton#primary:hover {{ background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; }}
QPushButton#primary:pressed {{ background: {ACCENT_PRESSED}; }}
QPushButton#primary:focus {{ border-color: #ffffff; }}
QPushButton#flat {{ background: transparent; border: none; color: {MUTED}; padding: 0px 8px; min-height: 28px; font-size: 13px; }}
QPushButton#flat:hover {{ color: {TEXT}; background: {RAISED}; }}

QToolButton {{
    background: transparent; border: none; border-radius: 6px; padding: 4px; color: {MUTED};
}}
QToolButton:hover {{ background: {RAISED}; }}
QToolButton:pressed {{ background: {RAISED_HOVER}; }}

QProgressBar {{ background: {RAISED}; border: none; border-radius: 2px; max-height: 4px; min-height: 4px; }}
QProgressBar::chunk {{ border-radius: 2px; background: {ACCENT}; }}
QProgressBar[state="done"]::chunk {{ background: {HAIRLINE_STRONG}; }}
QProgressBar[state="error"]::chunk {{ background: {ERROR}; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0px; }}
QScrollBar::handle:vertical {{ background: {RAISED_HOVER}; border-radius: 4px; min-height: 32px; }}
QScrollBar::handle:vertical:hover {{ background: {HAIRLINE_STRONG}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QTabWidget::pane {{ border: 1px solid {HAIRLINE}; border-radius: 12px; background: {SURFACE}; top: -1px; }}
QTabBar::tab {{
    background: transparent; color: {MUTED}; padding: 8px 16px; margin-right: 4px;
    border-top-left-radius: 8px; border-top-right-radius: 8px;
}}
QTabBar::tab:selected {{ color: {TEXT}; background: {SURFACE}; border: 1px solid {HAIRLINE}; border-bottom: none; }}
QTabBar::tab:hover:!selected {{ color: {TEXT_2}; }}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border-radius: 4px; border: 1px solid {HAIRLINE_STRONG}; background: {RAISED};
}}
QCheckBox::indicator:hover {{ border-color: {TEXT_2}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; {check_rule} }}

QPlainTextEdit {{
    background: {DEEP}; border: 1px solid {HAIRLINE}; border-radius: 8px;
    font-family: Consolas, "{FONT_FAMILY}"; font-size: 12px; color: {TEXT_2};
}}
QMenu {{ background: {RAISED}; border: 1px solid {HAIRLINE_STRONG}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 8px 24px 8px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: {RAISED_HOVER}; }}
QMenu::item:disabled {{ color: {MUTED}; }}
QMenu::separator {{ height: 1px; background: {HAIRLINE_STRONG}; margin: 4px 8px; }}
QMessageBox QLabel {{ color: {TEXT}; }}
QDialogButtonBox QPushButton {{ min-width: 88px; }}
"""


def apply_palette(app) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    for role, color in [
        (QPalette.Window, BG), (QPalette.WindowText, TEXT), (QPalette.Base, RAISED),
        (QPalette.AlternateBase, SURFACE), (QPalette.Text, TEXT), (QPalette.Button, RAISED),
        (QPalette.ButtonText, TEXT), (QPalette.Highlight, ACCENT), (QPalette.HighlightedText, "#ffffff"),
        (QPalette.ToolTipBase, RAISED), (QPalette.ToolTipText, TEXT), (QPalette.PlaceholderText, MUTED),
        (QPalette.Link, TEXT),
    ]:
        pal.setColor(role, QColor(color))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(MUTED))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(MUTED))
    app.setPalette(pal)
    app.setStyleSheet(build_qss())
