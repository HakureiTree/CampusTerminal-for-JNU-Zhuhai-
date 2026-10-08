# SPDX-License-Identifier: GPL-3.0-or-later
from PyQt5.QtCore import Qt, QSize, pyqtSignal
from PyQt5.QtGui import QPainter, QIcon
from PyQt5.QtWidgets import QPushButton, QWidget

from gui import theme as T
from gui.settings.auto_block import AutoBlock
from gui.settings.nic_block import NicBlock
from gui.settings.type_block import TypeBlock
from gui.widgets.paint import draw_glyphs, fill_round, prepare


class BackHit(QPushButton):
    def __init__(self, scale, family, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFlat(True)
        self.setStyleSheet("QPushButton { background: transparent; border: none; }")
        self.setGeometry(round(40 * scale), round(80 * scale), round(280 * scale), round(120 * scale))


class SettingsPage(QWidget):
    back = pyqtSignal()
    adapter_changed = pyqtSignal(str)
    type_changed = pyqtSignal(str)
    option_changed = pyqtSignal(str, bool)

    def __init__(self, scale, family, parent=None):
        super().__init__(parent)
        self.scale = scale
        self.family = family
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowTitle("设置 · 校园网终端")
        self.setFixedSize(round(T.SET_W * scale), round(T.SET_H * scale))
        self.nic = NicBlock(scale, family, (0, 0), self)
        self.types = TypeBlock(scale, family, self)
        self.autos = AutoBlock(scale, family, self)
        self.back_hit = BackHit(scale, family, self)
        self.back_hit.clicked.connect(self.back)
        self.nic.adapter_changed.connect(self.adapter_changed)
        self.types.type_changed.connect(self.type_changed)
        self.autos.option_changed.connect(self.option_changed)
        self.close_button = QPushButton(self)
        self.close_button.setIcon(QIcon(str(T.ICONS / "chrome/close.png")))
        side = max(24, round(105 * scale))
        margin = max(8, round(45 * scale))
        self.close_button.setGeometry(self.width() - side - margin, margin, side, side)
        self.close_button.setIconSize(QSize(round(side * .6), round(side * .6)))
        self.close_button.setStyleSheet("QPushButton { background: transparent; border: none; } QPushButton:hover { background: #444; border-radius: 4px; }")
        self.close_button.setToolTip("收起设置")
        self.close_button.setAccessibleName("收起设置")
        self.close_button.clicked.connect(self.back)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.back.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        self.back.emit()
        event.accept()

    def paintEvent(self, _event):
        painter = QPainter(self)
        prepare(painter)
        fill_round(painter, (0, 0, T.SET_W, T.SET_H, T.SET_R), self.scale, T.C_INNER)
        draw_glyphs(
            painter, T.G_SET_TITLE, (0, 0), self.scale,
            T.ui_font(103.808, self.scale, self.family), T.C_TEXT,
        )
