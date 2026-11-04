"""アプリの起動と、トレイ常駐・各部品のつなぎ込み。"""
import argparse
import logging
import os
import sys

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from ytdl import APP_ID, APP_NAME, VERSION
from ytdl import autostart
from ytdl.jobs import DONE, ERROR, error_hint, extract_urls
from ytdl.logsetup import setup_logging
from ytdl.paths import ensure_dirs, is_frozen
from ytdl.server import LocalServer
from ytdl.settings import Settings
from ytdl.tools import ToolManager
from ytdl.jobs import DownloadManager
from ytdl.ui import style
from ytdl.ui.icons import app_icon
from ytdl.ui.job_card import reveal_in_explorer
from ytdl.ui.main_window import MainWindow
from ytdl.ui.settings_dialog import SettingsDialog
from ytdl.ui.titlebar import TitleBarStyler

log = logging.getLogger("ytdl")
INSTANCE_NAME = f"{APP_ID}-{os.environ.get('USERNAME', 'user')}"
DAILY = 24 * 3600


class Controller(QObject):
    def __init__(self, app: QApplication, start_hidden: bool):
        super().__init__()
        self.app = app
        self.settings = Settings.load()
        self.tools = ToolManager(self.settings)
        self.manager = DownloadManager(self.settings, self.tools)
        self.server = LocalServer(self.manager)
        self.window = MainWindow(self.settings, self.manager, self.tools)
        self.settings_dialog = None

        # ---- トレイ ----
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip(APP_NAME)
        menu = QMenu()
        menu.addAction("開く", self.window.show_and_raise)
        menu.addSeparator()
        menu.addAction("クリップボードの URL を動画でダウンロード", lambda: self.add_from_clipboard("video"))
        menu.addAction("クリップボードの URL を音声でダウンロード", lambda: self.add_from_clipboard("audio"))
        menu.addSeparator()
        menu.addAction("保存先を開く", lambda: reveal_in_explorer(self.settings.save_dir))
        menu.addAction("ツールの更新を確認", lambda: self.tools.start_update())
        menu.addAction("設定…", self.open_settings)
        menu.addSeparator()
        menu.addAction("終了", self.quit)
        self.tray_menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.messageClicked.connect(self.window.show_and_raise)
        self.tray.show()

        # ---- つなぎ込み ----
        self.window.settings_requested.connect(self.open_settings)
        self.window.hidden_to_tray.connect(self._hint_tray)
        self.manager.job_finished.connect(self._on_job_finished)
        self.manager.counts_changed.connect(self._update_tray_tooltip)
        self.tools.update_finished.connect(self._on_tools_ready)
        self.tools.status_changed.connect(lambda t, f: self._update_tray_tooltip())
        self.server.bridge.download_requested.connect(self._on_remote_download)
        self.server.bridge.show_requested.connect(self.window.show_and_raise)

        if not self.server.start():
            self.tray.showMessage(APP_NAME, f"ブラウザ拡張機能と連携できません: {self.server.error}",
                                  QSystemTrayIcon.Warning, 8000)

        # 自動起動（exe 版のみ設定に合わせる。開発版では設定画面で変えたときだけ反映）
        if is_frozen():
            autostart.set_enabled(self.settings.autostart)

        # 起動時の更新（自動更新オフでも、ツールが無いときは取得する）
        if self.settings.auto_update or not self.tools.ready:
            self.tools.start_update()
        else:
            self.window._on_tool_status("準備完了" if self.tools.ready else "yt-dlp がありません", 1)

        # 1時間ごとに「最後の確認から 24 時間経っていて、何もダウンロードしていなければ」更新
        self.daily = QTimer(self)
        self.daily.setInterval(3600 * 1000)
        self.daily.timeout.connect(self._daily_check)
        self.daily.start()

        # 待機中は使っていないメモリを Windows に返す（タスクマネージャーの値が小さくなる）
        self.trim_timer = QTimer(self)
        self.trim_timer.setSingleShot(True)
        self.trim_timer.setInterval(15000)
        self.trim_timer.timeout.connect(self._trim_memory)
        self.window.hidden_to_tray.connect(self.trim_timer.start)
        self.tools.update_finished.connect(lambda ok: self.trim_timer.start())
        self.manager.counts_changed.connect(lambda: self.trim_timer.start() if not self.manager.active_count() else None)

        if not start_hidden:
            self.window.show_and_raise()
        log.info("%s %s 起動 (frozen=%s)", APP_NAME, VERSION, is_frozen())

    def _trim_memory(self) -> None:
        if self.window.isVisible() or self.manager.active_count() or self.tools.updating:
            return
        try:
            import ctypes
            import gc
            from ctypes import wintypes
            gc.collect()
            k32 = ctypes.windll.kernel32
            k32.GetCurrentProcess.restype = wintypes.HANDLE  # 64bit では型指定しないと壊れる
            k32.K32EmptyWorkingSet.argtypes = [wintypes.HANDLE]
            k32.K32EmptyWorkingSet(k32.GetCurrentProcess())
        except Exception:
            pass

    # ---------- トレイ ----------
    def _tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            if self.window.isVisible() and not self.window.isMinimized() and reason == QSystemTrayIcon.Trigger \
                    and self.window.isActiveWindow():
                self.window.hide()
            else:
                self.window.show_and_raise()

    def _hint_tray(self) -> None:
        if not self.settings.tray_hint_shown:
            self.settings.tray_hint_shown = True
            self.settings.save()
            self.tray.showMessage(APP_NAME, "通知領域で動作中です。終了するときはアイコンを右クリック →「終了」。",
                                  QSystemTrayIcon.Information, 5000)

    def _update_tray_tooltip(self) -> None:
        active = self.manager.active_count()
        tip = APP_NAME
        if self.tools.updating:
            tip += f"\n{self.tools.last_status}"
        if active:
            tip += f"\n{active} 件ダウンロード中"
        self.tray.setToolTip(tip)

    # ---------- ジョブ ----------
    def add_from_clipboard(self, mode: str) -> None:
        urls = extract_urls(QGuiApplication.clipboard().text() or "")
        if not urls:
            self.tray.showMessage(APP_NAME, "クリップボードに URL がありません。", QSystemTrayIcon.Information, 3000)
            return
        for u in urls:
            self.manager.add(u, mode)
        self.tray.showMessage(APP_NAME, f"{len(urls)} 件を追加しました。", QSystemTrayIcon.Information, 2500)

    def _on_remote_download(self, url: str, mode: str, playlist) -> None:
        job = self.manager.add(url, None if mode == "default" else mode, playlist)
        if self.settings.notify and not self.window.isVisible():
            kind = "音声" if job.mode == "audio" else "動画"
            self.tray.showMessage(APP_NAME, f"{kind}のダウンロードを開始します。", QSystemTrayIcon.Information, 2000)

    def _on_job_finished(self, job) -> None:
        if job.status == DONE:
            if self.settings.notify:
                self.tray.showMessage("ダウンロード完了", job.display_title, QSystemTrayIcon.Information, 4000)
            if self.settings.sound:
                try:
                    import winsound
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                except Exception:
                    pass
        elif job.status == ERROR and self.settings.notify:
            msg = error_hint(job.error) or job.error or "不明なエラー"
            self.tray.showMessage("ダウンロード失敗", f"{job.display_title}\n{msg[:160]}",
                                  QSystemTrayIcon.Warning, 6000)

    def _on_tools_ready(self, ok: bool) -> None:
        self.manager.schedule_pump()
        self._update_tray_tooltip()
        if not ok:
            self.tray.showMessage(APP_NAME, "yt-dlp を用意できませんでした。ネット接続を確認してください。",
                                  QSystemTrayIcon.Warning, 6000)

    def _daily_check(self) -> None:
        if (self.settings.auto_update and self.manager.active_count() == 0
                and self.tools.last_check_age() > DAILY):
            self.tools.start_update()

    # ---------- 設定 ----------
    def open_settings(self) -> None:
        if self.settings_dialog and self.settings_dialog.isVisible():
            self.settings_dialog.raise_()
            self.settings_dialog.activateWindow()
            return
        self.window.show_and_raise()
        old_channel = self.settings.update_channel
        dlg = SettingsDialog(self.settings, self.tools, self.server, self.window)
        self.settings_dialog = dlg
        if dlg.exec():
            before_autostart = autostart.is_enabled()
            dlg.apply()
            if self.settings.autostart != before_autostart:
                autostart.set_enabled(self.settings.autostart)
            self.window.refresh_info()
            self.manager.schedule_pump()
            if self.settings.update_channel != old_channel and self.manager.active_count() == 0:
                self.tools.start_update()
        else:
            self.settings.update_channel = old_channel
        self.settings_dialog = None

    # ---------- 終了 ----------
    def quit(self) -> None:
        active = self.manager.active_count()
        if active:
            self.window.show_and_raise()
            r = QMessageBox.question(self.window, APP_NAME,
                                     f"{active} 件のダウンロードが終わっていません。中止して終了しますか？")
            if r != QMessageBox.Yes:
                return
            self.manager.cancel_all()
        self.tools.cancel_event.set()
        self.window.really_quit = True
        self.window.save_geometry()
        self.window.close()
        self.server.stop()
        self.tray.hide()
        self.app.quit()


def _notify_running_instance() -> bool:
    """すでに起動していれば、そちらのウィンドウを表示させて True を返す。"""
    sock = QLocalSocket()
    sock.connectToServer(INSTANCE_NAME)
    if sock.waitForConnected(500):
        sock.write(b"show")
        sock.flush()
        sock.waitForBytesWritten(500)
        sock.disconnectFromServer()
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--tray", action="store_true", help="ウィンドウを出さずに常駐だけする")
    args, _ = parser.parse_known_args()

    ensure_dirs()
    setup_logging()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(VERSION)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(app_icon())
    style.apply_palette(app)
    titlebar_styler = TitleBarStyler(app)
    app.installEventFilter(titlebar_styler)

    if _notify_running_instance():
        return 0
    instance = QLocalServer()
    QLocalServer.removeServer(INSTANCE_NAME)
    if not instance.listen(INSTANCE_NAME):
        log.warning("多重起動防止の待ち受けに失敗: %s", instance.errorString())

    try:
        controller = Controller(app, start_hidden=args.tray)
    except Exception:
        log.exception("起動に失敗しました")
        QMessageBox.critical(None, APP_NAME, "起動に失敗しました。ログフォルダを確認してください。")
        return 1

    def on_new_connection():
        conn = instance.nextPendingConnection()
        if conn:
            conn.readyRead.connect(lambda c=conn: (c.readAll(), controller.window.show_and_raise()))
            conn.disconnected.connect(conn.deleteLater)
    instance.newConnection.connect(on_new_connection)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        controller.window.show_and_raise()

    return app.exec()
