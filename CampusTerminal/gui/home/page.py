# SPDX-License-Identifier: GPL-3.0-or-later
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QWidget

from gui.home.action_col import ActionColumn
from gui.home.advert_card import AdvertCard
from gui.home.login_card import LoginCard
from gui.home.recovery_card import RecoveryCard
from gui.home.settings_bar import SettingsBar
from gui.home.speed_card import SpeedCard


class HomePage(QWidget):
    open_settings = pyqtSignal()
    connect_requested = pyqtSignal()
    disconnect_requested = pyqtSignal()
    open_ad = pyqtSignal()

    def __init__(self, scale, family, parent=None):
        super().__init__(parent)
        self.login = LoginCard(scale, family, self)
        self.settings_bar = SettingsBar(scale, family, self)
        self.speed = SpeedCard(scale, family, self)
        self.recovery = RecoveryCard(scale, family, self)
        self.advert = AdvertCard(scale, family, self)
        self.actions = ActionColumn(scale, self)
        self.settings_bar.opened.connect(self.open_settings)
        self.actions.connect_requested.connect(self.connect_requested)
        self.actions.disconnect_requested.connect(self.disconnect_requested)
        self.advert.opened.connect(self.open_ad)
        self.recovery.set_state("idle", [])
