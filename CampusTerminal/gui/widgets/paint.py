# SPDX-License-Identifier: GPL-3.0-or-later
from PyQt5.QtCore import QRectF, QSize, Qt
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PyQt5.QtWidgets import QWidget

from gui import theme as T


class ScaledWidget(QWidget):
    def __init__(self, scale, family, parent=None):
        super().__init__(parent)
        self.scale = scale
        self.family = family
        self.setAttribute(Qt.WA_StyledBackground, False)

    def px(self, value):
        return value * self.scale

    def pt(self, xy):
        return xy[0] * self.scale, xy[1] * self.scale

    def rectf(self, box):
        x, y, w, h = box[:4]
        return QRectF(x * self.scale, y * self.scale, w * self.scale, h * self.scale)

    def font(self, px):
        return T.ui_font(px, self.scale, self.family)


def rounded_path(rect, radius):
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


def fill_round(painter, box, scale, color):
    x, y, w, h, r = box
    rect = QRectF(x * scale, y * scale, w * scale, h * scale)
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    painter.drawRoundedRect(rect, r * scale, r * scale)
    return rect


def stroke_round(painter, box, scale, color, width):
    x, y, w, h, r = box
    rect = QRectF(x * scale, y * scale, w * scale, h * scale)
    pen = QPen(color, max(1.0, width * scale))
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawRoundedRect(rect, r * scale, r * scale)
    return rect


def draw_baseline(painter, xy, scale, text, font, color):
    painter.setFont(font)
    painter.setPen(color)
    painter.drawText(round(xy[0] * scale), round(xy[1] * scale), text)


def draw_glyphs(painter, glyphs, origin, scale, font, color):
    ox, oy = origin
    painter.setFont(font)
    painter.setPen(color)
    for ch, x, y in glyphs:
        painter.drawText(round((x - ox) * scale), round((y - oy) * scale), ch)


def load_icon(rel, size):
    pix = QPixmap(str(T.ICONS / rel))
    if pix.isNull():
        return pix
    return pix.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def draw_pixmap(painter, box, scale, rel):
    x, y, w, h = box
    pix = QPixmap(str(T.ICONS / rel))
    if pix.isNull():
        return
    target = QRectF(x * scale, y * scale, w * scale, h * scale)
    painter.drawPixmap(target, pix, QRectF(pix.rect()))


def prepare(painter):
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
