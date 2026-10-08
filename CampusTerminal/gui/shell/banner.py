# SPDX-License-Identifier: GPL-3.0-or-later
from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QPainter, QPainterPath

from gui import theme as T
from gui.widgets.paint import draw_baseline, draw_glyphs, prepare


def paint_chrome(painter, scale, family, width, height):
    prepare(painter)
    outer = QPainterPath()
    outer.addRoundedRect(QRectF(0, 0, width, height), T.OUTER_R * scale, T.OUTER_R * scale)
    painter.fillPath(outer, T.C_OUTER)
    ix, iy, iw, ih, ir = T.INNER
    inner = QPainterPath()
    inner.addRoundedRect(QRectF(ix * scale, iy * scale, iw * scale, ih * scale), ir * scale, ir * scale)
    painter.fillPath(inner, T.C_INNER)
    bx, by, bw, bh, br = T.BANNER
    banner = QPainterPath()
    banner.addRoundedRect(QRectF(bx * scale, by * scale, bw * scale, bh * scale), br * scale, br * scale)
    painter.fillPath(banner, T.C_CARD)
    draw_glyphs(painter, T.G_BANNER, (0, 0), scale, T.ui_font(45.675, scale, family), T.C_MUTED)
    draw_baseline(painter, T.VERSION, scale, "V" + T.APP_VERSION, T.ui_font(41.058, scale, family), T.C_MUTED)
    draw_baseline(
        painter,
        T.DISCLAIMER,
        scale,
        "开源软件·仅供学习研究使用·作者不承担由此软件带来的任何法律责任",
        T.ui_font(29.80, scale, family),
        T.C_MUTED,
    )
