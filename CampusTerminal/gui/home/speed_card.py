# SPDX-License-Identifier: GPL-3.0-or-later
from PyQt5.QtGui import QPainter

from gui import theme as T
from gui.widgets.paint import ScaledWidget, draw_baseline, draw_glyphs, draw_pixmap, fill_round, prepare
from gui.widgets.sparkline import paint_spark


def format_rate(nbytes):
    value = max(0.0, float(nbytes))
    if value < 1000:
        return f"{value:.0f}B/s"
    if value < 1000_000:
        return f"{value / 1000:.0f}K/s" if value >= 10_000 else f"{value / 1000:.1f}K/s"
    if value < 1000_000_000:
        return f"{value / 1_000_000:.1f}M/s"
    return f"{value / 1_000_000_000:.1f}G/s"


class SpeedCard(ScaledWidget):
    def __init__(self, scale, family, parent=None):
        super().__init__(scale, family, parent)
        x, y, w, h, _r = T.SPEED
        self.origin = (x, y)
        self.setGeometry(round(x * scale), round(y * scale), round(w * scale), round(h * scale))
        self.up = 0.0
        self.down = 0.0
        self.samples = []

    def set_rates(self, up, down, samples):
        self.up = up
        self.down = down
        self.samples = list(samples[-60:])
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        prepare(painter)
        ox, oy = self.origin
        fill_round(painter, (0, 0, T.SPEED[2], T.SPEED[3], T.SPEED[4]), self.scale, T.C_CARD)
        painter.setClipRect(self.rect())
        draw_glyphs(painter, T.G_SPEED, self.origin, self.scale, self.font(88.555), T.C_TEXT)
        draw_pixmap(painter, (T.UP_ICON[0] - ox, T.UP_ICON[1] - oy, 60, 60), self.scale, "speed/up.png")
        draw_pixmap(painter, (T.DOWN_ICON[0] - ox, T.DOWN_ICON[1] - oy, 60, 60), self.scale, "speed/down.png")
        draw_baseline(painter, (T.UP_L[0] - ox, T.UP_L[1] - oy), self.scale,
                      format_rate(self.up), self.font(54.83), T.C_MUTED)
        draw_baseline(painter, (T.DOWN_L[0] - ox, T.DOWN_L[1] - oy), self.scale,
                      format_rate(self.down), self.font(54.83), T.C_MUTED)
        paint_spark(painter, self.scale, self.origin, self.samples)
