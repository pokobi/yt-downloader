"""小さな共通部品。"""
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from ytdl.ui import style
from ytdl.ui.icons import icon


class RecDot(QWidget):
    """REC ランプ。ダウンロード中のものにだけ付ける、小さな赤い点（点滅はしない）。"""

    def __init__(self, parent=None, size: int = 8):
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)

    def paintEvent(self, e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(style.ACCENT))
        p.drawEllipse(0, 0, self._size, self._size)
        p.end()


class IconButton(QPushButton):
    """アイコンと文字の間隔を 8px に固定したボタン。"""

    def __init__(self, icon_name: str, text: str, primary: bool = False, parent=None):
        super().__init__(parent)
        self._icon_name = icon_name
        self.setCursor(Qt.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(8)
        self._icon = QLabel()
        self._icon.setFixedSize(16, 16)
        self._text = QLabel(text)
        for w in (self._icon, self._text):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
            w.setStyleSheet("background: transparent;")
        lay.addStretch(1)
        lay.addWidget(self._icon)
        lay.addWidget(self._text)
        lay.addStretch(1)
        self.set_primary(primary)

    def set_primary(self, primary: bool) -> None:
        self.setObjectName("primary" if primary else "")
        color = "#ffffff" if primary else style.TEXT_2
        self._icon.setPixmap(icon(self._icon_name, color, 16).pixmap(QSize(16, 16)))
        weight = 600 if primary else 400
        self._text.setStyleSheet(f"background: transparent; color: {'#ffffff' if primary else style.TEXT};"
                                 f" font-weight: {weight};")
        self.style().unpolish(self)
        self.style().polish(self)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.layout().sizeHint().expandedTo(QSize(0, 36))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.sizeHint()
