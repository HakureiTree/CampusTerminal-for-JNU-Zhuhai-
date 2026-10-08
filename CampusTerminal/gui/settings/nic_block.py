# SPDX-License-Identifier: GPL-3.0-or-later
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import QComboBox, QWidget, QStyle, QStyleOptionComboBox, QStylePainter

from gui import theme as T
from gui.widgets.paint import draw_glyphs, draw_pixmap, fill_round, prepare, stroke_round


class ElidedComboBox(QComboBox):
    def __init__(self, scale, parent):
        super().__init__(parent)
        self.scale = scale

    def paintEvent(self, event):
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        option.currentText = self.fontMetrics().elidedText(option.currentText, Qt.ElideRight,
                                                          max(1, self.width() - round(140 * self.scale)))
        painter = QStylePainter(self)
        painter.drawComplexControl(QStyle.CC_ComboBox, option)
        painter.drawControl(QStyle.CE_ComboBoxLabel, option)


class NicBlock(QWidget):
    adapter_changed = pyqtSignal(str)

    def __init__(self, scale, family, origin, parent=None):
        super().__init__(parent)
        self.scale = scale
        self.family = family
        self.origin = origin
        x, y, w, h, _r = T.SET_NIC_BOX
        self.setGeometry(round(x * scale), round(y * scale), round(w * scale), round(h * scale))
        field = T.SET_NIC_FIELD
        self.combo = ElidedComboBox(scale, self)
        self.combo.setCursor(Qt.PointingHandCursor)
        self.combo.setStyleSheet(
            "QComboBox { background: transparent; border: none; color: #c6c6c6; padding-right: "
            + str(round(120 * scale)) + "px; }"
            "QComboBox::drop-down { border: none; width: 0px; }"
            "QComboBox QAbstractItemView { background: #181818; color: #c6c6c6; selection-background-color: #444; }"
        )
        self.combo.setFont(T.ui_font(44.70, scale, family))
        self.combo.setGeometry(
            round((field[0] - x + 24) * scale),
            round((field[1] - y) * scale),
            round((field[2] - 48) * scale),
            round(field[3] * scale),
        )
        self.combo.currentTextChanged.connect(self.adapter_changed)
        self.combo.currentTextChanged.connect(self.combo.setToolTip)

    def set_adapters(self, names, current):
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItems(names or ["以太网:未发现适配器"])
        if current and current in names:
            self.combo.setCurrentText(current)
        self.combo.blockSignals(False)
        self.combo.setToolTip(self.combo.currentText())
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        prepare(painter)
        ox, oy = T.SET_NIC_BOX[0], T.SET_NIC_BOX[1]
        stroke_round(painter, (0, 0, T.SET_NIC_BOX[2], T.SET_NIC_BOX[3], T.SET_NIC_BOX[4]), self.scale, T.C_LINE, 4.17)
        field = (
            T.SET_NIC_FIELD[0] - ox,
            T.SET_NIC_FIELD[1] - oy,
            T.SET_NIC_FIELD[2],
            T.SET_NIC_FIELD[3],
            T.SET_NIC_FIELD[4],
        )
        fill_round(painter, field, self.scale, T.C_CARD)
        draw_glyphs(
            painter, T.G_SET_NIC, (ox, oy), self.scale,
            T.ui_font(70.24, self.scale, self.family), T.C_TEXT,
        )
        caret = T.SET_CARET
        draw_pixmap(painter, (caret[0] - ox, caret[1] - oy, caret[2], caret[3]), self.scale, "setting/caret.png")
