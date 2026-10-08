# SPDX-License-Identifier: GPL-3.0-or-later
import ctypes

from PyQt5.QtCore import QTimer, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QAction, QMenu, QSystemTrayIcon

from gui import theme as T

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.RegisterWindowMessageW.argtypes = [ctypes.c_wchar_p]
_user32.RegisterWindowMessageW.restype = ctypes.c_uint
TASKBAR_CREATED = _user32.RegisterWindowMessageW("TaskbarCreated")


def allow_taskbar_created(hwnd):
    try:
        filt = _user32.ChangeWindowMessageFilterEx
        filt.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p]
        filt.restype = ctypes.c_int
        filt(hwnd, TASKBAR_CREATED, 1, None)
    except (AttributeError, OSError):
        pass


class AppTray(QSystemTrayIcon):
    show_main = pyqtSignal()
    connect_requested = pyqtSignal()
    disconnect_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(QIcon(str(T.ICONS / "led" / "idle.png")), parent)
        self.setToolTip("开源暨珠有线网络终端")
        menu = QMenu()
        show = QAction("显示主面板", menu)
        connect = QAction("登入并连接", menu)
        disconnect = QAction("登出并断连", menu)
        quit_act = QAction("退出程序", menu)
        show.triggered.connect(self.show_main.emit)
        connect.triggered.connect(self.connect_requested.emit)
        disconnect.triggered.connect(self.disconnect_requested.emit)
        quit_act.triggered.connect(self.quit_requested.emit)
        menu.addAction(show)
        menu.addAction(connect)
        menu.addAction(disconnect)
        menu.addSeparator()
        menu.addAction(quit_act)
        self.setContextMenu(menu)
        self.activated.connect(self._activated)
        self.messageClicked.connect(self._message_clicked)
        self._raise_on_click = True
        self._phase = "idle"
        self._flash_on = True
        self._flash = QTimer(self)
        self._flash.setInterval(450)
        self._flash.timeout.connect(self._blink)

    def notify(self, notice, raise_main=True, timeout_ms=8000):
        self._raise_on_click = raise_main
        icon = {"warning": QSystemTrayIcon.Warning, "critical": QSystemTrayIcon.Critical}.get(
            notice.severity, QSystemTrayIcon.Information)
        self.showMessage(notice.title, notice.body, icon, timeout_ms)

    def _message_clicked(self):
        if self._raise_on_click:
            self.show_main.emit()

    def _activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.show_main.emit()

    def set_phase(self, phase):
        self._phase = phase
        if self._flash.isActive() and not self._flash_on:
            return
        tone = {"online": "ok", "connecting": "wait", "verifying": "wait", "disconnecting": "wait", "recovering": "wait", "error": "err", "degraded": "err", "fallback": "wait", "fallback_active": "ok", "fallback_failed": "err"}.get(phase, "idle")
        self.setIcon(QIcon(str(T.ICONS / "led" / f"{tone}.png")))
        label = {"fallback": "正在交还学校官方客户端", "fallback_active": "学校官方客户端已接管", "fallback_failed": "交还学校官方客户端失败"}.get(phase, phase)
        self.setToolTip("开源暨珠有线网络终端 · " + label)

    def start_flash(self):
        if not self._flash.isActive():
            self._flash_on = True
            self._flash.start()

    def stop_flash(self):
        self._flash.stop()
        self._flash_on = True
        self.set_phase(self._phase)

    def restore(self):
        self.hide()
        self.show()
        self.set_phase(self._phase)

    def keep(self):
        if not self.isVisible():
            self.restore()

    def _blink(self):
        self._flash_on = not self._flash_on
        if self._flash_on:
            self.set_phase(self._phase)
        else:
            self.setIcon(QIcon(str(T.ICONS / "led" / "idle.png")))
