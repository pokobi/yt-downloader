from PySide6.QtCore import QByteArray, QSize, Qt, Signal
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPushButton,
                               QScrollArea, QToolButton, QVBoxLayout, QWidget)

from ytdl import APP_NAME
from ytdl.jobs import FINAL_STATES, extract_urls
from ytdl.ui import style
from ytdl.ui.icons import app_icon, icon
from ytdl.ui.job_card import JobCard, reveal_in_explorer
from ytdl.ui.widgets import IconButton, RecDot


class MainWindow(QMainWindow):
    settings_requested = Signal()
    hidden_to_tray = Signal()

    def __init__(self, settings, manager, tools):
        super().__init__()
        self.settings = settings
        self.manager = manager
        self.tools = tools
        self.cards: dict[str, JobCard] = {}
        self.really_quit = False

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.setMinimumSize(640, 480)
        self.resize(860, 640)
        self.setAcceptDrops(True)

        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(24, 20, 24, 24)
        root.setSpacing(0)

        # ---- ヘッダー ----
        header = QHBoxLayout()
        header.setSpacing(12)
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(QSize(24, 24)))
        header.addWidget(logo)
        title = QLabel(APP_NAME)
        title.setObjectName("appTitle")
        header.addWidget(title)
        header.addStretch(1)
        status = QHBoxLayout()
        status.setSpacing(8)
        self.rec = RecDot()
        status.addWidget(self.rec, 0, Qt.AlignVCenter)
        self.tool_status = QLabel("準備中")
        self.tool_status.setObjectName("status")
        status.addWidget(self.tool_status)
        header.addLayout(status)
        header.addSpacing(4)
        gear = QToolButton()
        gear.setIcon(icon("settings", style.TEXT_2, 18))
        gear.setIconSize(QSize(18, 18))
        gear.setFixedSize(32, 32)
        gear.setToolTip("設定  (Ctrl+,)")
        gear.setCursor(Qt.PointingHandCursor)
        gear.clicked.connect(self.settings_requested.emit)
        header.addWidget(gear)
        root.addLayout(header)
        root.addSpacing(20)

        # ---- 入力カード ----
        card = QFrame()
        card.setObjectName("card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 16, 16, 12)
        cl.setSpacing(12)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.url = QLineEdit()
        self.url.setObjectName("urlInput")
        self.url.setPlaceholderText("URL を貼り付け")
        self.url.setClearButtonEnabled(True)
        self.url.returnPressed.connect(lambda: self._submit(None))
        row.addWidget(self.url, 1)
        paste = QPushButton()
        paste.setIcon(icon("paste", style.TEXT_2, 16))
        paste.setIconSize(QSize(16, 16))
        paste.setFixedSize(40, 40)
        paste.setStyleSheet("padding: 0px;")
        paste.setToolTip("クリップボードから貼り付け")
        paste.setCursor(Qt.PointingHandCursor)
        paste.clicked.connect(self._paste)
        row.addWidget(paste)
        self.btn_video = IconButton("video", "動画")
        self.btn_video.setFixedHeight(40)
        self.btn_video.clicked.connect(lambda: self._submit("video"))
        row.addWidget(self.btn_video)
        self.btn_audio = IconButton("music", "音声")
        self.btn_audio.setFixedHeight(40)
        self.btn_audio.clicked.connect(lambda: self._submit("audio"))
        row.addWidget(self.btn_audio)
        cl.addLayout(row)

        self.info_label = QLabel()
        self.info_label.setObjectName("muted")
        self.info_label.setTextFormat(Qt.RichText)
        self.info_label.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
        self.info_label.linkActivated.connect(self._info_link)
        cl.addWidget(self.info_label)
        root.addWidget(card)
        root.addSpacing(24)

        # ---- キュー ----
        qh = QHBoxLayout()
        qh.setSpacing(8)
        qt = QLabel("ダウンロード")
        qt.setObjectName("sectionTitle")
        qh.addWidget(qt)
        self.count_label = QLabel("")
        self.count_label.setObjectName("count")
        qh.addWidget(self.count_label)
        qh.addStretch(1)
        self.clear_btn = QPushButton("完了したものを消す")
        self.clear_btn.setObjectName("flat")
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.clicked.connect(self.manager.clear_finished)
        qh.addWidget(self.clear_btn)
        root.addLayout(qh)
        root.addSpacing(8)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        holder = QWidget()
        self.list_layout = QVBoxLayout(holder)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(8)
        self.empty = QWidget()
        el = QVBoxLayout(self.empty)
        el.setContentsMargins(0, 64, 0, 64)
        el.setSpacing(8)
        et = QLabel("ダウンロードはまだありません")
        et.setObjectName("emptyTitle")
        et.setAlignment(Qt.AlignCenter)
        ed = QLabel("URL を貼り付けて「動画」か「音声」を押すか、YouTube の再生画面や X の投稿のダウンロードボタンから追加します\n"
                    "このウィンドウに URL をドラッグしても追加できます")
        ed.setObjectName("muted")
        ed.setAlignment(Qt.AlignCenter)
        el.addWidget(et)
        el.addWidget(ed)
        self.list_layout.addWidget(self.empty)
        self.list_layout.addStretch(1)
        self.scroll.setWidget(holder)
        root.addWidget(self.scroll, 1)

        QShortcut(QKeySequence.Paste, self, activated=self._paste_shortcut)
        QShortcut(QKeySequence("Ctrl+,"), self, activated=self.settings_requested.emit)

        manager.job_added.connect(self._on_added)
        manager.job_changed.connect(self._on_changed)
        manager.job_removed.connect(self._on_removed)
        manager.thumb_loaded.connect(self._on_thumb)
        manager.counts_changed.connect(self._update_counts)
        manager.counts_changed.connect(self._refresh_status)
        tools.status_changed.connect(lambda t, f: self._refresh_status())
        tools.update_finished.connect(lambda ok: self._refresh_status())

        self.refresh_info()
        self._update_counts()
        self._refresh_status()
        self._restore_geometry()

    # ---------- 表示 ----------
    def refresh_info(self) -> None:
        s = self.settings
        folder = s.save_dir
        if len(folder) > 44:
            folder = folder[:18] + "…" + folder[-24:]
        link = f"color:{style.TEXT_2};text-decoration:none"
        self.info_label.setText(
            f'保存先 <a href="open" style="{link}">{folder}</a>'
            f'　·　動画 {s.summary("video")}　·　音声 {s.summary("audio")}'
            f'　·　<a href="settings" style="{link}">変更</a>')
        default_audio = s.default_mode == "audio"
        self.btn_video.set_primary(not default_audio)
        self.btn_audio.set_primary(default_audio)
        enter = "音声" if default_audio else "動画"
        self.url.setToolTip(f"Enter で{enter}としてダウンロード")

    def _info_link(self, href: str) -> None:
        if href == "open":
            reveal_in_explorer(self.settings.save_dir)
        else:
            self.settings_requested.emit()

    def _refresh_status(self) -> None:
        """右上の状態。ダウンロード中だけ REC ランプが点く。"""
        active = self.manager.running_count()
        waiting = self.manager.active_count() - active
        color = style.MUTED
        if active:
            text = f"{active} 件ダウンロード中" + (f"・{waiting} 件待ち" if waiting else "")
            color = style.TEXT_2
        elif self.tools.updating:
            text = self.tools.last_status
        elif not self.tools.ready:
            text = "yt-dlp がありません"
            color = style.ERROR
        elif self.tools.last_status not in ("準備完了", "準備中"):
            text = self.tools.last_status
            color = style.WARNING
        else:
            text = "準備完了"
        self.rec.setVisible(bool(active))
        self.tool_status.setText(text)
        self.tool_status.setStyleSheet(f"color: {color};")
        self.tool_status.setToolTip(
            f"yt-dlp: {self.tools.ytdlp.describe()}\nFFmpeg: {self.tools.ffmpeg.describe()}\n"
            f"Deno: {self.tools.deno.describe()}")

    # 互換用（main.py から呼ばれる）
    def _on_tool_status(self, text: str, frac: float) -> None:
        self._refresh_status()

    def _update_counts(self) -> None:
        jobs = self.manager.all_jobs()
        done = sum(1 for j in jobs if j.status in FINAL_STATES)
        self.count_label.setText(f"{len(jobs)}" if jobs else "")
        self.clear_btn.setVisible(done > 0)
        self.empty.setVisible(not jobs)

    # ---------- 追加 ----------
    def _submit(self, mode) -> None:
        urls = extract_urls(self.url.text())
        if not urls:
            self.url.setFocus()
            self.url.selectAll()
            return
        for u in urls:
            self.manager.add(u, mode)
        self.url.clear()

    def _paste(self) -> None:
        text = QGuiApplication.clipboard().text()
        if text:
            self.url.setText(" ".join(extract_urls(text)) or text.strip())
            self.url.setFocus()

    def _paste_shortcut(self) -> None:
        if self.url.hasFocus():
            self.url.paste()
        else:
            self._paste()

    def dragEnterEvent(self, e):  # noqa: N802
        if e.mimeData().hasUrls() or e.mimeData().hasText():
            e.acceptProposedAction()

    def dropEvent(self, e):  # noqa: N802
        md = e.mimeData()
        text = "\n".join(u.toString() for u in md.urls()) if md.hasUrls() else md.text()
        for u in extract_urls(text):
            self.manager.add(u, None)

    # ---------- カード ----------
    def _on_added(self, job) -> None:
        card = JobCard(job)
        card.cancel_clicked.connect(self.manager.cancel)
        card.retry_clicked.connect(self.manager.retry)
        card.remove_clicked.connect(self.manager.remove)
        self.cards[job.id] = card
        self.list_layout.insertWidget(1, card)  # 新しいものを上に
        self.scroll.verticalScrollBar().setValue(0)

    def _on_changed(self, job) -> None:
        card = self.cards.get(job.id)
        if card:
            card.refresh()

    def _on_removed(self, job_id: str) -> None:
        card = self.cards.pop(job_id, None)
        if card:
            if card.log_dialog:
                card.log_dialog.close()
            card.setParent(None)
            card.deleteLater()

    def _on_thumb(self, job_id: str, data: bytes) -> None:
        card = self.cards.get(job_id)
        if card:
            card.set_thumbnail(data)

    # ---------- ウィンドウ ----------
    def show_and_raise(self) -> None:
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    def _restore_geometry(self) -> None:
        if self.settings.window_geometry:
            try:
                self.restoreGeometry(QByteArray.fromBase64(self.settings.window_geometry.encode()))
            except Exception:
                pass

    def save_geometry(self) -> None:
        self.settings.window_geometry = bytes(self.saveGeometry().toBase64()).decode()
        self.settings.save()

    def closeEvent(self, e):  # noqa: N802
        self.save_geometry()
        if self.really_quit:
            e.accept()
            return
        e.ignore()
        self.hide()
        self.hidden_to_tray.emit()
