import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, QTabWidget,
                               QVBoxLayout, QWidget)

from ytdl import EXTENSION_ID, SERVER_HOST, SERVER_PORT
from ytdl.paths import LOG_DIR, extension_dir, is_frozen
from ytdl.settings import CHOICES, LABELS


def _combo(key: str, current: str) -> QComboBox:
    c = QComboBox()
    for value in CHOICES[key]:
        c.addItem(LABELS[key].get(value, value), value)
    idx = c.findData(current)
    c.setCurrentIndex(max(0, idx))
    return c


def _form() -> tuple[QWidget, QFormLayout]:
    w = QWidget()
    f = QFormLayout(w)
    f.setContentsMargins(24, 24, 24, 24)
    f.setHorizontalSpacing(16)
    f.setVerticalSpacing(12)
    f.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return w, f


def _note(text: str) -> QLabel:
    lb = QLabel(text)
    lb.setObjectName("muted")
    lb.setWordWrap(True)
    return lb


class SettingsDialog(QDialog):
    def __init__(self, settings, tools, server, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.tools = tools
        self.server = server
        self.setWindowTitle("設定")
        self.setMinimumWidth(620)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(16)
        tabs = QTabWidget()
        root.addWidget(tabs)
        s = settings

        # ---- 一般 ----
        w, f = _form()
        row = QHBoxLayout()
        self.save_dir = QLineEdit(s.save_dir)
        browse = QPushButton("選択…")
        browse.clicked.connect(self._browse)
        row.addWidget(self.save_dir, 1)
        row.addWidget(browse)
        f.addRow("保存先", row)
        self.default_mode = _combo("default_mode", s.default_mode)
        f.addRow("既定のモード", self.default_mode)
        self.filename = _combo("filename", s.filename)
        f.addRow("ファイル名", self.filename)
        self.concurrency = QComboBox()
        for n in range(1, 6):
            self.concurrency.addItem(f"{n} 件", n)
        self.concurrency.setCurrentIndex(max(0, min(4, s.concurrency - 1)))
        f.addRow("同時ダウンロード数", self.concurrency)
        self.autostart = QCheckBox("Windows へのログイン時に自動で起動する（通知領域に常駐）")
        self.autostart.setChecked(s.autostart)
        f.addRow("", self.autostart)
        if not is_frozen():
            f.addRow("", _note("※ 開発版で起動中です。自動起動は exe 版で使うことをおすすめします。"))
        self.notify = QCheckBox("完了・失敗を通知で知らせる")
        self.notify.setChecked(s.notify)
        f.addRow("", self.notify)
        self.sound = QCheckBox("完了したら音を鳴らす")
        self.sound.setChecked(s.sound)
        f.addRow("", self.sound)
        tabs.addTab(w, "一般")

        # ---- 動画 ----
        w, f = _form()
        self.video_quality = _combo("video_quality", s.video_quality)
        f.addRow("画質", self.video_quality)
        self.video_container = _combo("video_container", s.video_container)
        f.addRow("形式", self.video_container)
        self.video_codec = _combo("video_codec", s.video_codec)
        f.addRow("コーデック", self.video_codec)
        f.addRow("", _note("動画編集ソフトや古いプレーヤーで開けないときは「H.264 優先」にしてください。"
                           "選んだ画質がない場合は、それ以下で一番良いものになります。"))
        tabs.addTab(w, "動画")

        # ---- 音声 ----
        w, f = _form()
        self.audio_format = _combo("audio_format", s.audio_format)
        f.addRow("形式", self.audio_format)
        self.audio_quality = _combo("audio_quality", s.audio_quality)
        f.addRow("音質", self.audio_quality)
        f.addRow("", _note("音質は MP3 / M4A / Opus のときに使います。YouTube の元の音声は最大でも "
                           "約 160kbps 相当なので、320kbps にしても元より良くはなりません。"))
        self.audio_format.currentIndexChanged.connect(self._sync_audio)
        self._sync_audio()
        tabs.addTab(w, "音声")

        # ---- 詳細 ----
        w, f = _form()
        self.playlist = QCheckBox("URL がプレイリストのときは全曲をダウンロードする")
        self.playlist.setChecked(s.playlist)
        f.addRow("プレイリスト", self.playlist)
        self.embed_metadata = QCheckBox("タイトル・投稿者・チャプターを書き込む")
        self.embed_metadata.setChecked(s.embed_metadata)
        f.addRow("メタデータ", self.embed_metadata)
        self.embed_thumbnail = QCheckBox("サムネイル（カバー画像）を埋め込む")
        self.embed_thumbnail.setChecked(s.embed_thumbnail)
        f.addRow("", self.embed_thumbnail)
        self.sponsorblock = QCheckBox("スポンサー・宣伝区間を削除する（音声では曲以外の区間も）")
        self.sponsorblock.setChecked(s.sponsorblock)
        f.addRow("SponsorBlock", self.sponsorblock)
        self.cookies = _combo("cookies_browser", s.cookies_browser)
        f.addRow("ブラウザの Cookie", self.cookies)
        f.addRow("", _note("年齢制限・メンバー限定の動画や、ボット判定されたときに使います。"
                           "Chrome 系ブラウザは起動中だと読めないことがあります。"))
        tabs.addTab(w, "詳細")

        # ---- ツール・連携 ----
        w, f = _form()
        self.auto_update = QCheckBox("起動時と 1 日 1 回、新しい版を自動で入れる")
        self.auto_update.setChecked(s.auto_update)
        f.addRow("自動更新", self.auto_update)
        self.update_channel = _combo("update_channel", s.update_channel)
        f.addRow("yt-dlp の更新チャンネル", self.update_channel)
        self.tool_labels = {}
        for key, st in (("yt-dlp", tools.ytdlp), ("FFmpeg", tools.ffmpeg), ("Deno", tools.deno)):
            lb = QLabel(st.describe())
            lb.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.tool_labels[key] = lb
            f.addRow(key, lb)
        self.tool_status = _note(tools.last_status)
        f.addRow("", self.tool_status)
        btns = QHBoxLayout()
        self.update_btn = QPushButton("今すぐ更新を確認")
        self.update_btn.clicked.connect(self._update_now)
        logs = QPushButton("ログフォルダを開く")
        logs.clicked.connect(lambda: os.startfile(str(LOG_DIR)))  # type: ignore[attr-defined]
        btns.addWidget(self.update_btn)
        btns.addWidget(logs)
        btns.addStretch(1)
        f.addRow("", btns)

        state = (f"待ち受け中（{SERVER_HOST}:{SERVER_PORT}）" if server.running
                 else f"停止中：{server.error}")
        f.addRow("拡張機能との連携", QLabel(state))
        ext = QHBoxLayout()
        open_ext = QPushButton("拡張機能のフォルダを開く")
        open_ext.clicked.connect(self._open_extension)
        ext.addWidget(open_ext)
        ext.addStretch(1)
        f.addRow("", ext)
        f.addRow("", _note("Chrome で chrome://extensions を開き、右上の「デベロッパー モード」をオンにして、"
                           "「パッケージ化されていない拡張機能を読み込む」でこのフォルダを選びます。"
                           f"拡張機能 ID：{EXTENSION_ID}"))
        tabs.addTab(w, "ツール・連携")

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("保存")
        bb.button(QDialogButtonBox.Ok).setObjectName("primary")
        bb.button(QDialogButtonBox.Cancel).setText("キャンセル")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

        tools.status_changed.connect(self._on_tool_status)
        tools.update_finished.connect(self._on_tool_finished)
        self.update_btn.setEnabled(not tools.updating)

    # ---------- 動作 ----------
    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "保存先を選択", self.save_dir.text())
        if d:
            self.save_dir.setText(os.path.normpath(d))

    def _sync_audio(self):
        self.audio_quality.setEnabled(self.audio_format.currentData() in ("mp3", "m4a", "opus"))

    def _open_extension(self):
        d = extension_dir()
        if d.exists():
            os.startfile(str(d))  # type: ignore[attr-defined]

    def _update_now(self):
        # チャンネルの変更はすぐ反映してから更新する
        self.settings.update_channel = self.update_channel.currentData()
        if self.tools.start_update(force=False):
            self.update_btn.setEnabled(False)

    def _on_tool_status(self, text, frac):
        self.tool_status.setText(text)

    def _on_tool_finished(self, ok):
        self.update_btn.setEnabled(True)
        for key, st in (("yt-dlp", self.tools.ytdlp), ("FFmpeg", self.tools.ffmpeg), ("Deno", self.tools.deno)):
            self.tool_labels[key].setText(st.describe())

    def done(self, result):  # noqa: D401 - 閉じるときにシグナルを外す
        try:
            self.tools.status_changed.disconnect(self._on_tool_status)
            self.tools.update_finished.disconnect(self._on_tool_finished)
        except (RuntimeError, TypeError):
            pass
        super().done(result)

    def apply(self) -> None:
        s = self.settings
        path = self.save_dir.text().strip()
        if path:
            s.save_dir = os.path.normpath(path)
        s.default_mode = self.default_mode.currentData()
        s.filename = self.filename.currentData()
        s.concurrency = int(self.concurrency.currentData())
        s.autostart = self.autostart.isChecked()
        s.notify = self.notify.isChecked()
        s.sound = self.sound.isChecked()
        s.video_quality = self.video_quality.currentData()
        s.video_container = self.video_container.currentData()
        s.video_codec = self.video_codec.currentData()
        s.audio_format = self.audio_format.currentData()
        s.audio_quality = self.audio_quality.currentData()
        s.playlist = self.playlist.isChecked()
        s.embed_metadata = self.embed_metadata.isChecked()
        s.embed_thumbnail = self.embed_thumbnail.isChecked()
        s.sponsorblock = self.sponsorblock.isChecked()
        s.cookies_browser = self.cookies.currentData()
        s.auto_update = self.auto_update.isChecked()
        s.update_channel = self.update_channel.currentData()
        s.save()
