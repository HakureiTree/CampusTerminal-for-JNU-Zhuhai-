# SPDX-License-Identifier: GPL-3.0-or-later
from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QPainter, QPainterPath
from PyQt5.QtWidgets import QPushButton

from gui import theme as T
from gui.widgets.paint import prepare


class UpdateChip(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scale = 1
        self.family = ""
        self.version_text = ""
        self.setCursor(Qt.PointingHandCursor)
        self.setFlat(True)
        self.setStyleSheet("QPushButton { background: transparent; border: none; }")
        self.hide()

    def set_version(self, version):
        self.version_text = str(version or "")
        self.setVisible(bool(self.version_text))
        if self.version_text and self.family:
            self.place(self.scale, self.family)
        if self.version_text:
            self.raise_()
        self.update()

    def label(self):
        if not self.version_text:
            return ""
        return "有新版本可用：V" + self.version_text

    def place(self, scale, family):
        self.scale = scale
        self.family = family
        text = self.label() or "有新版本可用：V0.0.0"
        self.setFont(T.ui_font(36, scale, family))
        width = self.fontMetrics().horizontalAdvance(text) + max(24, round(44 * scale))
        height = max(22, round(52 * scale))
        banner_x, _y, banner_w, _h, _r = T.BANNER
        x = round((banner_x + banner_w / 2) * scale - width / 2)
        y = round(96 * scale)
        self.setGeometry(x, y, width, height)
        self.setAccessibleName(self.label() or "有新版本可用")
        self.update()

    def paintEvent(self, _event):
        text = self.label()
        if not text:
            return
        painter = QPainter(self)
        prepare(painter)
        rect = QRectF(self.rect().adjusted(1, 1, -2, -2))
        radius = min(rect.height() / 2, 18 * self.scale)
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        painter.fillPath(path, QColor("#14210f"))
        painter.setPen(T.C_GREEN)
        painter.drawPath(path)
        painter.setFont(self.font())
        painter.drawText(self.rect(), Qt.AlignCenter, text)
