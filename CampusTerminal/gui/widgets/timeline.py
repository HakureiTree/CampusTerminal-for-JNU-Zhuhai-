# SPDX-License-Identifier: GPL-3.0-or-later
from PyQt5.QtCore import QRectF
from PyQt5.QtGui import QLinearGradient, QPen

from gui import theme as T
from gui.widgets.paint import draw_baseline, draw_pixmap


def paint_rules(painter, scale, origin):
    ox, oy = origin
    gradient = QLinearGradient(T.TIME_RULE_X * scale, 0, (T.TIME_RULE_X + T.TIME_RULE_W) * scale, 0)
    gradient.setColorAt(0.0, T.C_TEXT)
    gradient.setColorAt(0.0, T.C_TEXT)
    gradient.setColorAt(0.34, T.C_SOFT)
    gradient.setColorAt(0.71, T.C_LINE)
    gradient.setColorAt(1.0, T.C_LINE)
    pen = QPen()
    pen.setWidthF(max(1.0, 4.17 * scale))
    pen.setBrush(gradient)
    painter.setPen(pen)
    x1 = (T.TIME_RULE_X - ox) * scale
    x2 = (T.TIME_RULE_X + T.TIME_RULE_W - ox) * scale
    for y in T.TIME_RULES:
        py = (y - oy) * scale
        painter.drawLine(round(x1), round(py), round(x2), round(py))


def paint_events(painter, scale, family, origin, events):
    font = T.ui_font(42.52, scale, family)
    ox, oy = origin
    rows = events[:3]
    for slot, item in zip(T.TIMELINE, rows):
        date_xy, time_xy, tick_xy = slot
        draw_baseline(painter, (date_xy[0] - ox, date_xy[1] - oy), scale, item[0], font, T.C_TEXT)
        draw_baseline(painter, (time_xy[0] - ox, time_xy[1] - oy), scale, item[1], font, T.C_TEXT)
        result = item[2] if len(item) > 2 else ""
        if result == "成功":
            draw_pixmap(painter, (tick_xy[0] - ox, tick_xy[1] - oy, 50, 36), scale, "recover/tick.png")
        elif result:
            draw_baseline(painter, (tick_xy[0] - ox, time_xy[1] - oy), scale, result, font, T.C_TEXT)
