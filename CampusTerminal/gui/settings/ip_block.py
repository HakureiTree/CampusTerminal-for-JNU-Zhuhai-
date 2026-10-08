# SPDX-License-Identifier: GPL-3.0-or-later
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import QLabel, QWidget

from gui import theme as T
from gui.widgets.paint import prepare, stroke_round


class IpBlock(QWidget):
    def __init__(self, scale, family, parent=None):
        super().__init__(parent)
        self.scale = scale
        x, y, w, h, _r = T.SET_IP_BOX
        self.setGeometry(round(x * scale), round(y * scale), round(w * scale), round(h * scale))
        self.title = QLabel("当前 IPv4", self)
        self.value = QLabel("尚未分配 IPv4", self)
        for label, top, height, font_size in [(self.title, 36, 88, 70.24),
                                             (self.value, 143, 132, 58)]:
            label.setGeometry(round(52 * scale), round(top * scale),
                              round((w - 104) * scale), round(height * scale))
            label.setFont(T.ui_font(font_size, scale, family))
            label.setStyleSheet("color: #c7c7c7; background: transparent;")
        self.value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.value.setWordWrap(True)
        self.setToolTip("显示所选网卡的本机 IPv4 地址；每次连接或重连成功后更新。")

    def set_address(self, text):
        self.value.setText(text)
        self.value.setToolTip(text)

    def paintEvent(self, _event):
        painter = QPainter(self)
        prepare(painter)
        stroke_round(painter, (0, 0, T.SET_IP_BOX[2], T.SET_IP_BOX[3], T.SET_IP_BOX[4]),
                     self.scale, T.C_LINE, 4.17)
