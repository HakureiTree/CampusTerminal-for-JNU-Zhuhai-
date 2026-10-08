# SPDX-License-Identifier: GPL-3.0-or-later
from PyQt5.QtCore import QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QPainter, QPainterPath, QPixmap
from PyQt5.QtWidgets import QAbstractButton

from gui import theme as T
from gui.widgets.paint import prepare


class CloseButton(QAbstractButton):
    closed = pyqtSignal()

    def __init__(self, scale, parent=None):
        super().__init__(parent)
        self.scale = scale
        cx, cy, r = T.CLOSE_C
        self.setGeometry(
            round((cx - r) * scale),
            round((cy - r) * scale),
            round(2 * r * scale),
            round(2 * r * scale),
        )
        self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(self.closed)

    def paintEvent(self, _event):
        painter = QPainter(self)
        prepare(painter)
        path = QPainterPath()
        path.addEllipse(QRectF(self.rect()))
        painter.fillPath(path, T.C_INNER)
        pix = QPixmap(str(T.ICONS / "chrome/close.png"))
        if pix.isNull():
            return
        ix, iy, iw, ih = T.CLOSE_ICON
        cx, cy, r = T.CLOSE_C
        target_x = (ix - (cx - r)) * self.scale
        target_y = (iy - (cy - r)) * self.scale
        painter.drawPixmap(
            round(target_x),
            round(target_y),
            round(iw * self.scale),
            round(ih * self.scale),
            pix,
        )
