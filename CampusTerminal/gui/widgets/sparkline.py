# SPDX-License-Identifier: GPL-3.0-or-later
from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QLinearGradient, QPainter, QPainterPath, QPen

from gui import theme as T
from gui.widgets.paint import prepare, rounded_path


def _design_path(scale, origin):
    ox, oy = origin
    path = QPainterPath()
    pts = T.SPARK_LINE
    path.moveTo((pts[0][0] - ox) * scale, (pts[0][1] - oy) * scale)
    for x, y in pts[1:]:
        path.lineTo((x - ox) * scale, (y - oy) * scale)
    return path


def _live_path(scale, origin, samples, clip):
    if len(samples) < 2:
        return None
    ox, oy = origin
    x, y, w, h = clip[:4]
    peak = max(1.0, max(samples))
    path = QPainterPath()
    n = len(samples)
    for i, value in enumerate(samples):
        px = (x - ox + w * i / (n - 1)) * scale
        py = (y - oy + h * (1.0 - value / peak)) * scale
        if i == 0:
            path.moveTo(px, py)
        else:
            path.lineTo(px, py)
    return path


def paint_spark(painter, scale, origin, samples):
    prepare(painter)
    ox, oy = origin
    clip = T.SPARK
    rect = QRectF((clip[0] - ox) * scale, (clip[1] - oy) * scale, clip[2] * scale, clip[3] * scale)
    painter.save()
    painter.setClipPath(rounded_path(rect, clip[4] * scale))
    line = _live_path(scale, origin, samples or [0, 0], clip)
    if line is None:
        painter.restore()
        return
    fill = QPainterPath(line)
    bottom = (clip[1] - oy + clip[3]) * scale
    fill.lineTo(rect.right(), bottom)
    fill.lineTo(rect.left(), bottom)
    fill.closeSubpath()
    gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    gradient.setColorAt(0.0, T.C_LINE)
    gradient.setColorAt(1.0, T.C_CARD)
    painter.fillPath(fill, gradient)
    pen = QPen(T.C_SPARK, max(1.5, 8.33 * scale))
    pen.setJoinStyle(Qt.RoundJoin)
    pen.setCapStyle(Qt.RoundCap)
    painter.strokePath(line, pen)
    painter.restore()
