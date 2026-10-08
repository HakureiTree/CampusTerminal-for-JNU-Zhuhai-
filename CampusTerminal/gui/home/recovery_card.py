# SPDX-License-Identifier: GPL-3.0-or-later
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter, QFontMetrics

from gui import theme as T
from gui.widgets.paint import ScaledWidget, draw_baseline, draw_glyphs, draw_pixmap, fill_round, prepare
from gui.widgets.timeline import paint_events, paint_rules


class RecoveryCard(ScaledWidget):
    def __init__(self, scale, family, parent=None):
        super().__init__(scale, family, parent)
        x, y, w, h, _r = T.RECOVERY
        self.origin = (x, y)
        self.setGeometry(round(x * scale), round(y * scale), round(w * scale), round(h * scale))
        self.state = "idle"
        self.events = []
        self.detail = ""

    def set_state(self, state, events, detail=None):
        self.state = state
        self.events = list(events[-3:])
        self.detail = detail or ""
        self.setToolTip(self.detail or "最近三次自动重连：日期、时间、结果。成功显示勾。不保证游戏会话存活。")
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        prepare(painter)
        ox, oy = self.origin
        fill_round(painter, (0, 0, T.RECOVERY[2], T.RECOVERY[3], T.RECOVERY[4]), self.scale, T.C_CARD)
        shield = {"ok": "recover/ok.png", "wait": "recover/wait.png"}.get(self.state, "recover/off.png")
        draw_pixmap(
            painter,
            (T.RECOVERY_SHIELD[0] - ox, T.RECOVERY_SHIELD[1] - oy, T.RECOVERY_SHIELD[2], T.RECOVERY_SHIELD[3]),
            self.scale,
            shield,
        )
        labels = {
            "ok": "状态：工作中",
            "wait": "状态：等待网络",
            "error": "状态：" + (self.detail or "失败"),
        }
        status = labels.get(self.state, "状态：未工作")
        metrics = QFontMetrics(self.font(42.52))
        status = metrics.elidedText(status, Qt.ElideRight, round((T.RECOVERY[2] - (T.RECOVERY_STATUS[0] - ox) - 18) * self.scale))
        draw_glyphs(painter, T.G_RECOVERY, self.origin, self.scale, self.font(88.555), T.C_TEXT)
        draw_baseline(
            painter,
            (T.RECOVERY_STATUS[0] - ox, T.RECOVERY_STATUS[1] - oy),
            self.scale,
            status,
            self.font(42.52),
            T.C_TEXT,
        )
        paint_rules(painter, self.scale, self.origin)
        paint_events(painter, self.scale, self.family, self.origin, self.events)
