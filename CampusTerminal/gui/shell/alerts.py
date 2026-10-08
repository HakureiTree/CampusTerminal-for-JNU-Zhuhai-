# SPDX-License-Identifier: GPL-3.0-or-later
"""Exclusive routing: visible window -> in-app dialog; hidden -> tray toast."""
from PyQt5.QtCore import QTimer

from gui.shell.notifications import Notice, is_confirm, remind_ms


class AlertRouter:
    def __init__(self, visible):
        self.visible = visible
        self.pending = None
        self.dialog = None
        self.toast = None
        self.flashing = False
        self.toast_armed = False

    def deliver(self, notice):
        self.pending = notice
        if self.visible():
            self.dialog = notice
            self.toast = None
            self.toast_armed = False
        else:
            self.dialog = None
            self.toast = notice
            self.toast_armed = is_confirm(notice)

    def toast_ignored(self):
        if self.toast_armed and self.pending is not None and is_confirm(self.pending) and not self.visible():
            self.flashing = True
            self.toast_armed = False

    def revealed(self):
        self.toast_armed = False
        self.toast = None
        if self.pending is not None and is_confirm(self.pending):
            self.dialog = self.pending
        else:
            self.pending = None
            self.dialog = None

    def concealed(self):
        if self.pending is not None and self.dialog is not None and is_confirm(self.pending):
            self.flashing = True
        self.dialog = None

    def dismiss(self):
        self.pending = None
        self.dialog = None
        self.toast = None
        self.toast_armed = False
        self.flashing = False


def window_is_visible(window):
    return window.isVisible() and not window.isMinimized() and window.isActiveWindow()


class AlertHost:
    def __init__(self, window, tray=None, toast_ms=8000):
        self.window = window
        self.tray = tray
        self.router = AlertRouter(lambda: window_is_visible(window))
        self._ignore = QTimer(window)
        self._ignore.setSingleShot(True)
        self._ignore.setInterval(toast_ms + 400)
        self._ignore.timeout.connect(self._toast_ignored)
        window.notice.dismissed.connect(self._dismissed)
        window.revealed.connect(self._revealed)
        window.concealed.connect(self._concealed)

    def deliver(self, notice):
        self.router.deliver(notice)
        self._apply()

    def warn(self, title, body, severity="warning", kind="confirm"):
        self.deliver(Notice(title, body, severity, kind))

    def _apply(self):
        route = self.router
        if route.dialog is not None:
            self._ignore.stop()
            self.window.notice.show_notice(route.dialog)
        else:
            self.window.notice.hide()
        if self.tray:
            if route.toast is not None:
                confirm = is_confirm(route.toast)
                self.tray.notify(route.toast, raise_main=confirm,
                                 timeout_ms=8000 if confirm else remind_ms(route.toast))
                if confirm:
                    self._ignore.start()
                else:
                    self._ignore.stop()
            else:
                self._ignore.stop()
            if route.flashing:
                self.tray.start_flash()
            else:
                self.tray.stop_flash()

    def _toast_ignored(self):
        self.router.toast_ignored()
        self._apply()

    def _revealed(self):
        self.router.revealed()
        self._apply()

    def _concealed(self):
        self.router.concealed()
        self._apply()

    def _dismissed(self):
        self.router.dismiss()
        self._ignore.stop()
        if self.tray:
            self.tray.stop_flash()
