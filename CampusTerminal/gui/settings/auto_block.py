# SPDX-License-Identifier: GPL-3.0-or-later
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import QWidget

from gui import theme as T
from gui.widgets.checks import BoxToggle
from gui.widgets.paint import draw_baseline, draw_glyphs, prepare, stroke_round


class AutoBlock(QWidget):
    option_changed = pyqtSignal(str, bool)

    def __init__(self, scale, family, parent=None):
        super().__init__(parent)
        self.scale = scale
        self.family = family
        x, y, w, h, _r = T.SET_AUTO_BOX
        self.origin = (x, y)
        self.setGeometry(round(x * scale), round(y * scale), round(w * scale), round(h * scale))
        self.toggles = {}
        iw, ih = T.SET_AUTO_ICON
        for ix, iy, label, key in T.SET_AUTOS:
            box = (ix - x, iy - y, iw, ih)
            toggle = BoxToggle(scale, box, self)
            toggle.changed.connect(lambda on, k=key: self.option_changed.emit(k, on))
            self.toggles[key] = toggle
            toggle.setToolTip(label)
            if key == "inode_fallback":
                toggle.setToolTip("默认关闭。开启后，恢复失败或退出程序时停止自身认证，交还学校官方客户端和原自动重连监控；手动断连不会交还。")
            if key == "seamless":
                toggle.setEnabled(False)
                toggle.setToolTip("不伪造网络特征。自动重连会保留网卡、IP、路由和代理配置；不保证应用会话存活。")
        self.toggles["auto_start"].setChecked(True)
        self.toggles["auto_connect"].setChecked(True)
        self.toggles["auto_reconnect"].setChecked(True)

    def set_options(self, values):
        for key, toggle in self.toggles.items():
            if key in values:
                toggle.blockSignals(True)
                toggle.setChecked(bool(values[key]) if key != "seamless" else False)
                toggle.blockSignals(False)
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        prepare(painter)
        ox, oy = self.origin
        stroke_round(
            painter,
            (0, 0, T.SET_AUTO_BOX[2], T.SET_AUTO_BOX[3], T.SET_AUTO_BOX[4]),
            self.scale,
            T.C_LINE,
            4.17,
        )
        draw_glyphs(
            painter, T.G_SET_AUTO, (ox, oy), self.scale,
            T.ui_font(70.24, self.scale, self.family), T.C_TEXT,
        )
        font = T.ui_font(63.85, self.scale, self.family)
        for ix, iy, label, _key in T.SET_AUTOS:
            painter.setOpacity(.4 if _key in ("seamless",) or not self.toggles[_key].isEnabled() else 1.0)
            draw_baseline(
                painter,
                (ix - ox + T.SET_AUTO_TEXT_DX, iy - oy + T.SET_AUTO_TEXT_DY),
                self.scale,
                label,
                font,
                T.C_SOFT,
            )
        painter.setOpacity(1.0)
