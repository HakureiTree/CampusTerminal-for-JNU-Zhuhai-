# SPDX-License-Identifier: GPL-3.0-or-later
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import QAbstractButton

from gui import theme as T
from gui.widgets.paint import draw_glyphs, draw_pixmap, fill_round, prepare


class SettingsBar(QAbstractButton):
    opened = pyqtSignal()

    def __init__(self, scale, family, parent=None):
        super().__init__(parent)
        self.scale = scale
        self.family = family
        self.setCursor(Qt.PointingHandCursor)
        x, y, w, h, _r = T.SETTINGS_BAR
        self.setGeometry(round(x * scale), round(y * scale), round(w * scale), round(h * scale))
        self.clicked.connect(self.opened)

    def paintEvent(self, _event):
        painter = QPainter(self)
        prepare(painter)
        x, y, w, h, r = T.SETTINGS_BAR
        fill_round(painter, (0, 0, w, h, r), self.scale, T.C_CARD)
        draw_glyphs(
            painter, T.G_SETTINGS_BAR, (x, y), self.scale,
            T.ui_font(103.808, self.scale, self.family), T.C_TEXT,
        )
        ix, iy, iw, ih = T.SETTINGS_CHEV
        draw_pixmap(painter, (ix - x, iy - y, iw, ih), self.scale, "chrome/chevron.png")
