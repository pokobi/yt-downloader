import os
import subprocess
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QMenu, QPlainTextEdit, QProgressBar,
                               QToolButton, QVBoxLayout, QWidget)

from ytdl.jobs import CANCELLED, DONE, ERROR, POST, QUEUED, RUNNING, Job, error_hint
from ytdl.ui import style
from ytdl.ui.icons import icon
from ytdl.ui.widgets import RecDot

THUMB_W, THUMB_H = 128, 72


class ElidedLabel(QLabel):
    """長い文字列を「…」で省略して1行に収めるラベル。"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._full = text
        self.setMinimumWidth(40)
        self.setSizePolicy(self.sizePolicy().horizontalPolicy().Ignored, self.sizePolicy().verticalPolicy())
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802
        self._full = text or ""
        self.setToolTip(self._full if len(self._full) > 30 else "")
        self._update()

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        self._update()

    def _update(self):
        fm = self.fontMetrics()
        super().setText(fm.elidedText(self._full, Qt.ElideRight, max(10, self.width())))


def rounded_pixmap(data: bytes) -> QPixmap | None:
    src = QPixmap()
    if not src.loadFromData(data):
        return None
    ratio = 2
    w, h = THUMB_W * ratio, THUMB_H * ratio
    scaled = src.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    x, y = (scaled.width() - w) // 2, (scaled.height() - h) // 2
    out = QPixmap(w, h)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, w, h), 4 * ratio, 4 * ratio)
    p.setClipPath(path)
    p.drawPixmap(-x, -y, scaled)
    p.end()
    out.setDevicePixelRatio(ratio)
    return out


def placeholder_pixmap(mode: str) -> QPixmap:
    ratio = 2
    out = QPixmap(THUMB_W * ratio, THUMB_H * ratio)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, out.width(), out.height()), 4 * ratio, 4 * ratio)
    p.fillPath(path, QColor(style.RAISED))
    ic = icon("music" if mode == "audio" else "video", style.MUTED, 28)
    pm = ic.pixmap(QSize(28, 28), 2.0)
    p.drawPixmap((out.width() - 56) // 2, (out.height() - 56) // 2, 56, 56, pm)
    p.end()
    out.setDevicePixelRatio(ratio)
    return out


def reveal_in_explorer(path: str) -> None:
    p = Path(path)
    if p.exists() and p.is_file():
        subprocess.Popen(["explorer", "/select,", str(p)])
    elif p.exists():
        os.startfile(str(p))  # type: ignore[attr-defined]


class LogDialog(QDialog):
    def __init__(self, job: Job, parent=None):
        super().__init__(parent)
        self.job = job
        self.setWindowTitle(f"ログ - {job.display_title}")
        self.resize(760, 460)
        lay = QVBoxLayout(self)
        self.text = QPlainTextEdit(readOnly=True)
        self.text.setLineWrapMode(QPlainTextEdit.NoWrap)
        lay.addWidget(self.text)
        self.refresh()

    def refresh(self):
        bar = self.text.verticalScrollBar()
        at_end = bar.value() >= bar.maximum() - 4
        self.text.setPlainText("\n".join(self.job.log))
        if at_end:
            bar.setValue(bar.maximum())


class JobCard(QFrame):
    cancel_clicked = Signal(str)
    retry_clicked = Signal(str)
    remove_clicked = Signal(str)

    def __init__(self, job: Job, parent: QWidget | None = None):
        super().__init__(parent)
        self.job = job
        self.log_dialog: LogDialog | None = None
        self.setObjectName("job")
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)

        # カード 12px 角丸・内側 12px → サムネイルは 12 − 12 = 下限の 4px 角丸
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(16)

        self.thumb = QLabel()
        self.thumb.setFixedSize(THUMB_W, THUMB_H)
        self.thumb.setPixmap(placeholder_pixmap(job.mode))
        root.addWidget(self.thumb)

        mid = QVBoxLayout()
        mid.setContentsMargins(0, 0, 0, 0)
        mid.setSpacing(4)
        self.title = ElidedLabel(job.display_title)
        self.title.setObjectName("jobTitle")
        mid.addWidget(self.title)

        self.sub = ElidedLabel("")
        self.sub.setObjectName("secondary")
        mid.addWidget(self.sub)
        mid.addStretch(1)

        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        mid.addWidget(self.bar)
        mid.addSpacing(4)

        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.setSpacing(8)
        self.rec = RecDot()
        status_row.addWidget(self.rec, 0, Qt.AlignVCenter)
        self.status = ElidedLabel("")
        self.status.setObjectName("status")
        status_row.addWidget(self.status, 1)
        mid.addLayout(status_row)
        root.addLayout(mid, 1)

        actions = QVBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(4)
        self.btn_cancel = self._tool("close", "キャンセル", lambda: self.cancel_clicked.emit(self.job.id), danger=True)
        self.btn_folder = self._tool("folder", "フォルダを開く", self._open_folder)
        self.btn_retry = self._tool("retry", "再試行", lambda: self.retry_clicked.emit(self.job.id))
        self.btn_remove = self._tool("trash", "一覧から消す", lambda: self.remove_clicked.emit(self.job.id), danger=True)
        self.btn_more = self._tool("more", "その他", lambda: self._menu(None))
        for b in (self.btn_cancel, self.btn_folder, self.btn_retry, self.btn_remove, self.btn_more):
            actions.addWidget(b)
        actions.addStretch(1)
        root.addLayout(actions)

        self.refresh()

    def _tool(self, name, tip, slot, danger=False) -> QToolButton:
        b = QToolButton()
        b.setIcon(icon(name, style.MUTED, 16))
        b.setIconSize(QSize(16, 16))
        b.setFixedSize(28, 28)
        b.setToolTip(tip)
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(slot)
        return b

    # ---------- 表示更新 ----------
    def set_thumbnail(self, data: bytes) -> None:
        pm = rounded_pixmap(data)
        if pm:
            self.thumb.setPixmap(pm)

    def refresh(self) -> None:
        j = self.job
        self.title.setText(j.display_title)
        kind = "音声" if j.mode == "audio" else "動画"
        sub = [j.uploader, f"{kind} {j.summary}"]
        if j.playlist:
            sub.append(f"プレイリスト {j.item_index}/{j.item_count}" if j.item_count else "プレイリスト")
        self.sub.setText("  ·  ".join(s for s in sub if s))

        state = {DONE: "done", ERROR: "error", CANCELLED: "error"}.get(j.status, "")
        if self.bar.property("state") != state:
            self.bar.setProperty("state", state)
            self.bar.style().unpolish(self.bar)
            self.bar.style().polish(self.bar)
        if j.status == QUEUED:
            self.bar.setRange(0, 1000)
            self.bar.setValue(0)
        elif j.status == POST or (j.status == RUNNING and j.progress == 0 and not j.speed):
            self.bar.setRange(0, 0)  # 動き続けるバー（所要時間が読めない処理中）
        elif j.status in (ERROR, CANCELLED):
            self.bar.setRange(0, 1000)
        else:
            self.bar.setRange(0, 1000)
            self.bar.setValue(int(j.progress * 1000))

        if j.status in (RUNNING,) and j.speed:
            text = f"{j.stage}  {j.progress * 100:.0f}%  ·  {j.speed}" + (f"  ·  {j.eta}" if j.eta else "")
        elif j.status == ERROR:
            hint = error_hint(j.error)
            # 1 行の表示なので、文末の句点は付けない
            text = f"{j.stage}：{(hint or j.error or '不明なエラー').rstrip('。')}"
        else:
            text = j.stage
        self.status.setText(text)
        recording = j.status in (RUNNING, POST)
        self.rec.setVisible(recording)
        color = {DONE: style.SUCCESS, ERROR: style.ERROR}.get(j.status, style.TEXT_2 if recording else style.MUTED)
        self.status.setStyleSheet(f"color: {color};")
        if j.status == ERROR and j.error:
            self.status.setToolTip(j.error)

        active = j.active
        self.btn_cancel.setVisible(active)
        self.btn_folder.setVisible(j.status == DONE)
        self.btn_retry.setVisible(j.status in (ERROR, CANCELLED))
        self.btn_remove.setVisible(not active)

        if self.log_dialog and self.log_dialog.isVisible():
            self.log_dialog.refresh()

    # ---------- 操作 ----------
    def _open_folder(self):
        if self.job.files:
            reveal_in_explorer(self.job.files[-1])
        else:
            from ytdl.ui.main_window import MainWindow  # 循環 import 回避
            win = self.window()
            if isinstance(win, MainWindow):
                reveal_in_explorer(win.settings.save_dir)

    def _show_log(self):
        if not self.log_dialog:
            self.log_dialog = LogDialog(self.job, self.window())
        self.log_dialog.refresh()
        self.log_dialog.show()
        self.log_dialog.raise_()

    def mouseDoubleClickEvent(self, e):  # noqa: N802
        if self.job.status == DONE and self.job.files and Path(self.job.files[-1]).exists():
            os.startfile(self.job.files[-1])  # type: ignore[attr-defined]
        else:
            self._show_log()

    def _menu(self, pos):
        m = QMenu(self)
        j = self.job
        if j.status == DONE and j.files:
            m.addAction("ファイルを開く", lambda: os.startfile(j.files[-1]) if Path(j.files[-1]).exists() else None)
            m.addAction("フォルダで表示", self._open_folder)
        m.addAction("URL をコピー", lambda: QGuiApplication.clipboard().setText(j.url))
        if j.error:
            m.addAction("エラー内容をコピー", lambda: QGuiApplication.clipboard().setText(j.error))
        m.addAction("ログを表示", self._show_log)
        m.addSeparator()
        if j.active:
            m.addAction("キャンセル", lambda: self.cancel_clicked.emit(j.id))
        else:
            m.addAction("もう一度ダウンロード", lambda: self.retry_clicked.emit(j.id))
            m.addAction("一覧から消す", lambda: self.remove_clicked.emit(j.id))
        if pos is None:
            m.exec(self.btn_more.mapToGlobal(self.btn_more.rect().bottomLeft()))
        else:
            m.exec(self.mapToGlobal(pos))
