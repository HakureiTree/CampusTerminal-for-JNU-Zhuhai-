# SPDX-License-Identifier: GPL-3.0-or-later
from PyQt5.QtCore import QRect, Qt, pyqtSignal
from PyQt5.QtGui import QFontMetrics, QPainter
from PyQt5.QtWidgets import QWidget

from gui import theme as T
from gui.widgets.checks import BoxToggle
from gui.widgets.paint import prepare, stroke_round

TITLE_PX = 70.24
BODY_PX = 63.85
TITLE_MIN = 15
BODY_MIN = 14


class AutoBlock(QWidget):
    """Automatic-action card with metric-sized, wrapped, full-row toggles.

    The design canvas keeps its width/x/y; the height is computed from the
    actual font metrics so the settings page can reflow (and scroll) around it.
    """

    option_changed = pyqtSignal(str, bool)

    def __init__(self, scale, family, parent=None):
        super().__init__(parent)
        self.scale = scale
        self.family = family
        x, y, w, h, _r = T.SET_AUTO_BOX
        self.origin = (x, y)
        self.design_width = w
        self.toggles = {}
        self.rows = []
        self.title_font = T.ui_font(TITLE_PX, scale, family, TITLE_MIN)
        self.body_font = T.ui_font(BODY_PX, scale, family, BODY_MIN)
        self.title_origin = (x, y)
        self.setGeometry(round(x * scale), round(y * scale), max(1, round(w * scale)), 1)
        for _ix, _iy, label, key in T.SET_AUTOS:
            toggle = BoxToggle(scale, (0, 0, 1, 1), self)
            toggle.changed.connect(lambda on, k=key: self.option_changed.emit(k, on))
            self.toggles[key] = toggle
            toggle.setToolTip(label)
            if key == "inode_fallback":
                toggle.setToolTip("默认关闭。开启后，恢复失败或退出程序时停止自身认证，交还学校官方客户端和原自动重连监控；手动断连不会交还。")
            if key == "seamless":
                toggle.setEnabled(False)
                toggle.setToolTip("不伪造网络特征。自动重连会保留网卡、IP、路由和代理配置；不保证应用会话存活。")
            if key == "auto_update":
                toggle.setToolTip("默认关闭。开启后，每次启动若发现高于当前版本和已忽略版本的正式版，将自动增量更新并重启，只用通知提示，不再询问。")
        self.toggles["auto_start"].setChecked(True)
        self.toggles["auto_connect"].setChecked(True)
        self.toggles["auto_reconnect"].setChecked(True)
        self.relayout(scale)

    def set_options(self, values):
        for key, toggle in self.toggles.items():
            if key in values:
                toggle.blockSignals(True)
                toggle.setChecked(bool(values[key]) if key != "seamless" else False)
                toggle.blockSignals(False)
        self.update()

    def _compute(self, scale):
        title_font = T.ui_font(TITLE_PX, scale, self.family, TITLE_MIN)
        body_font = T.ui_font(BODY_PX, scale, self.family, BODY_MIN)
        title_metrics = QFontMetrics(title_font)
        body_metrics = QFontMetrics(body_font)
        vpad = max(4, round(8 * scale))
        pad = max(8, round(48 * scale))
        gap = max(8, round(24 * scale))
        visual_size = max(14, round(min(T.SET_AUTO_ICON) * scale))
        width = max(1, round(self.design_width * scale))
        text_w = max(1, width - pad - visual_size - gap)
        title_h = title_metrics.height() + 2 * vpad
        rows = []
        y = title_h
        for _ix, _iy, label, key in T.SET_AUTOS:
            text_height = body_metrics.boundingRect(
                QRect(0, 0, text_w, 10000), int(Qt.TextWordWrap), label).height()
            row_h = max(visual_size, text_height) + 2 * vpad
            row_rect = QRect(0, y, width, row_h)
            text_rect = QRect(pad + visual_size + gap, y, text_w, row_h)
            visual_rect = QRect(pad, y + max(0, (row_h - visual_size) // 2), visual_size, visual_size)
            rows.append((key, label, row_rect, text_rect, visual_rect))
            y += row_h
        height = y + vpad
        baseline = vpad + title_metrics.ascent()
        title_origin = (T.SET_AUTO_BOX[0], T.G_SET_AUTO[0][2] - baseline / max(scale, 1e-6))
        return {
            "title_font": title_font,
            "body_font": body_font,
            "width": width,
            "height": height,
            "rows": rows,
            "title_origin": title_origin,
            "title_height": title_h,
            "vpad": vpad,
            "pad": pad,
            "gap": gap,
            "visual_size": visual_size,
        }

    def required_height(self, scale):
        return self._compute(scale)["height"]

    def relayout(self, scale):
        data = self._compute(scale)
        self.scale = scale
        self.title_font = data["title_font"]
        self.body_font = data["body_font"]
        self.title_origin = data["title_origin"]
        self.rows = data["rows"]
        self.visual_size = data["visual_size"]
        self.title_height = data["title_height"]
        self.vpad = data["vpad"]
        self.pad = data["pad"]
        self.gap = data["gap"]
        self.setGeometry(self.x(), self.y(), data["width"], data["height"])
        for key, _label, row_rect, _text_rect, visual_rect in self.rows:
            toggle = self.toggles[key]
            toggle.setGeometry(row_rect)
            local = QRect(visual_rect.x() - row_rect.x(), visual_rect.y() - row_rect.y(),
                          visual_rect.width(), visual_rect.height())
            toggle.set_visual_rect(local)
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        prepare(painter)
        scale = max(self.scale, 1e-6)
        stroke_round(
            painter,
            (0, 0, max(1.0, self.width() / scale), max(1.0, self.height() / scale), T.SET_AUTO_BOX[4]),
            scale,
            T.C_LINE,
            4.17,
        )
        # A minimum 15 px title cannot use the SVG per-glyph spacing; draw it as
        # one string so the characters never overlap at small window sizes.
        painter.setFont(self.title_font)
        painter.setPen(T.C_TEXT)
        painter.drawText(self.pad, self.vpad + QFontMetrics(self.title_font).ascent(), "自动操作")
        painter.setFont(self.body_font)
        for key, label, _row_rect, text_rect, _visual_rect in self.rows:
            painter.setOpacity(.4 if key == "seamless" or not self.toggles[key].isEnabled() else 1.0)
            painter.setPen(T.C_SOFT)
            painter.drawText(text_rect, int(Qt.AlignVCenter | Qt.AlignLeft | Qt.TextWordWrap), label)
        painter.setOpacity(1.0)
