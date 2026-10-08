# SPDX-License-Identifier: GPL-3.0-or-later
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPainter, QPixmap
from PyQt5.QtWidgets import QAbstractButton

from gui import theme as T
from gui.widgets.paint import fill_round, prepare


class ActionButton(QAbstractButton):
    clicked_kind = pyqtSignal(str)

    def __init__(self, kind, folder, box, scale, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.folder = folder
        self.box = box
        self.scale = scale
        self.tone = "idle"
        self.setToolTip({"led": "连接状态", "login": "登入并连接", "logout": "正常登出"}.get(kind, kind))
        self.setCursor(Qt.PointingHandCursor)
        x, y, w, h = box[:4]
        self.setGeometry(round(x * scale), round(y * scale), round(w * scale), round(h * scale))
        self.clicked.connect(lambda: self.clicked_kind.emit(self.kind))

    def set_tone(self, tone):
        if tone != self.tone:
            self.tone = tone
            self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        prepare(painter)
        if not self.isEnabled():
            painter.setOpacity(.5)
        local = (0, 0, self.box[2], self.box[3], self.box[4])
        fill_round(painter, local, self.scale, T.C_CARD)
        pix = QPixmap(str(T.ICONS / self.folder / f"{self.tone}.png"))
        if pix.isNull():
            return
        pw, ph = pix.width(), pix.height()
        side = min(self.width(), self.height()) * 0.64
        dw = side * pw / max(pw, ph)
        dh = side * ph / max(pw, ph)
        painter.drawPixmap(
            round((self.width() - dw) / 2),
            round((self.height() - dh) / 2),
            round(dw),
            round(dh),
            pix,
        )


class GhostButton(QAbstractButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, _event):
        return
