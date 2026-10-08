# SPDX-License-Identifier: GPL-3.0-or-later
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import QAbstractButton, QWidget

from gui import theme as T
from gui.widgets.paint import draw_glyphs, fill_round, prepare, stroke_round


class TypeButton(QAbstractButton):
    def __init__(self, box, label, scale, family, parent=None):
        super().__init__(parent)
        self.box = box
        self.label = label
        self.scale = scale
        self.family = family
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        x, y, w, h, _r, _n = box
        self.setGeometry(round(x * scale), round(y * scale), round(w * scale), round(h * scale))

    def paintEvent(self, _event):
        painter = QPainter(self)
        prepare(painter)
        if not self.isEnabled():
            painter.setOpacity(.4)
        local = (0, 0, self.box[2], self.box[3], self.box[4])
        if self.isChecked():
            fill_round(painter, local, self.scale, T.C_CARD)
        stroke_round(painter, local, self.scale, T.C_LINE, 4.17)
        painter.setFont(T.ui_font(51.08, self.scale, self.family))
        painter.setPen(T.C_SOFT)
        painter.drawText(self.rect(), Qt.AlignCenter, self.label)


class TypeBlock(QWidget):
    type_changed = pyqtSignal(str)

    def __init__(self, scale, family, parent=None):
        super().__init__(parent)
        self.scale = scale
        self.family = family
        x, y, w, h, _r = T.SET_TYPE_BOX
        self.origin = (x, y)
        self.setGeometry(round(x * scale), round(y * scale), round(w * scale), round(h * scale))
        self.buttons = []
        keys = ["normal", "fast", "sso"]
        for spec, key in zip(T.SET_TYPE_BTNS, keys):
            lx = spec[0] - x
            ly = spec[1] - y
            btn = TypeButton((lx, ly, spec[2], spec[3], spec[4], spec[5]), spec[5], scale, family, self)
            btn.clicked.connect(lambda _=False, k=key: self._pick(k))
            btn.setToolTip("普通 802.1X 认证" if key == "normal" else "尚无学校侧协议支持，当前不可用")
            btn.setEnabled(key == "normal")
            self.buttons.append((key, btn))
        self._pick("normal")

    def _pick(self, key):
        key = "normal"
        for item, btn in self.buttons:
            btn.setChecked(item == key)
        self.type_changed.emit(key)

    def set_type(self, key):
        self._pick(key)

    def paintEvent(self, _event):
        painter = QPainter(self)
        prepare(painter)
        stroke_round(
            painter,
            (0, 0, T.SET_TYPE_BOX[2], T.SET_TYPE_BOX[3], T.SET_TYPE_BOX[4]),
            self.scale,
            T.C_LINE,
            4.17,
        )
        draw_glyphs(
            painter, T.G_SET_TYPE, self.origin, self.scale,
            T.ui_font(70.24, self.scale, self.family), T.C_TEXT,
        )
