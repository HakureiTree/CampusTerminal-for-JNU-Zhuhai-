# SPDX-License-Identifier: GPL-3.0-or-later
from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QPainter, QPixmap
from PyQt5.QtWidgets import QAbstractButton

from gui import theme as T
from gui.widgets.paint import prepare


class IconToggle(QAbstractButton):
    changed = pyqtSignal(bool)

    def __init__(self, on_rel, off_rel, scale, box, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.on_rel = on_rel
        self.off_rel = off_rel
        self.scale = scale
        x, y, w, h = box[:4]
        self.setGeometry(round(x * scale), round(y * scale), round(w * scale), round(h * scale))
        self.toggled.connect(self.changed)

    def sizeHint(self):
        return QSize(self.width(), self.height())

    def paintEvent(self, _event):
        painter = QPainter(self)
        prepare(painter)
        rel = self.on_rel if self.isChecked() else self.off_rel
        pix = QPixmap(str(T.ICONS / rel))
        if pix.isNull():
            return
        painter.drawPixmap(self.rect(), pix)


class BoxToggle(QAbstractButton):
    changed = pyqtSignal(bool)

    def __init__(self, scale, box, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.scale = scale
        x, y, w, h = box[:4]
        self.setGeometry(round(x * scale), round(y * scale), round(w * scale), round(h * scale))
        self.toggled.connect(self.changed)

    def paintEvent(self, _event):
        painter = QPainter(self)
        prepare(painter)
        if self.isChecked():
            pix = QPixmap(str(T.ICONS / "setting/box_on.png"))
            if not pix.isNull():
                painter.drawPixmap(self.rect(), pix)
            return
        painter.setPen(T.C_LINE)
        painter.setBrush(Qt.NoBrush)
        r = 8 * self.scale
        painter.drawRoundedRect(self.rect().adjusted(2, 2, -2, -2), r, r)
