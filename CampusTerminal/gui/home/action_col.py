# SPDX-License-Identifier: GPL-3.0-or-later
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QWidget

from gui import theme as T
from gui.widgets.iconbtn import ActionButton


class ActionColumn(QWidget):
    connect_requested = pyqtSignal()
    disconnect_requested = pyqtSignal()

    def __init__(self, scale, parent=None):
        super().__init__(parent)
        self.led = ActionButton("led", "led", T.LED_BTN, scale, parent)
        self.login = ActionButton("login", "login", T.IN_BTN, scale, parent)
        self.logout = ActionButton("logout", "logout", T.OUT_BTN, scale, parent)
        self.login.clicked_kind.connect(lambda _k: self.connect_requested.emit())
        self.logout.clicked_kind.connect(lambda _k: self.disconnect_requested.emit())

    def set_phase(self, phase):
        if phase in ("online", "authenticated", "fallback_active"):
            self.led.set_tone("ok")
            self.login.set_tone("ok")
            self.logout.set_tone("idle")
        elif phase in ("connecting", "verifying", "recovering", "disconnecting", "fallback"):
            self.led.set_tone("wait")
            self.login.set_tone("wait")
            self.logout.set_tone("idle")
        elif phase in ("error", "rejected", "degraded", "fallback_failed"):
            self.led.set_tone("err")
            self.login.set_tone("err")
            self.logout.set_tone("err")
        else:
            self.led.set_tone("idle")
            self.login.set_tone("idle")
            self.logout.set_tone("idle")
