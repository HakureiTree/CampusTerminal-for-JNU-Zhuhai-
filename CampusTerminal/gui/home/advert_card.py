# SPDX-License-Identifier: GPL-3.0-or-later
from PyQt5.QtCore import QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QFontMetrics, QPainter, QPen, QPixmap
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import QPushButton

from gui import theme as T
from gui.widgets.paint import ScaledWidget, draw_baseline, fill_round, prepare


class AdvertCard(ScaledWidget):
    opened = pyqtSignal()

    def __init__(self, scale, family, parent=None):
        super().__init__(scale, family, parent)
        x, y, w, h, _r = T.AD
        self.origin = (x, y)
        self.setGeometry(round(x * scale), round(y * scale), round(w * scale), round(h * scale))
        self.logo = QSvgRenderer(str(T.ASSETS / "logo.svg"), self)
        self.logo.setViewBox(QRectF(1265.32, 2826.216, 445.922, 153.066))
        self.setCursor(Qt.PointingHandCursor)
        self.hit = QPushButton(self)
        self.hit.setCursor(Qt.PointingHandCursor)
        self.hit.setFlat(True)
        self.hit.setGeometry(0, 0, self.width(), self.height())
        self.hit.setStyleSheet("QPushButton { background: transparent; border: none; }")
        self.hit.clicked.connect(self.opened)

    def resizeEvent(self, event):
        self.hit.setGeometry(0, 0, self.width(), self.height())
        super().resizeEvent(event)

    def paintEvent(self, _event):
        painter = QPainter(self)
        prepare(painter)
        ox, oy = self.origin
        fill_round(painter, (0, 0, T.AD[2], T.AD[3], T.AD[4]), self.scale, T.C_CARD)
        dpr = max(1.0, self.devicePixelRatioF())
        lw = max(1, round(T.AD_LOGO[2] * self.scale))
        lh = max(1, round(T.AD_LOGO[3] * self.scale))
        pix = QPixmap(round(lw * dpr), round(lh * dpr))
        pix.setDevicePixelRatio(dpr)
        pix.fill(Qt.transparent)
        svg = QPainter(pix)
        svg.setRenderHint(QPainter.Antialiasing)
        self.logo.render(svg, QRectF(0, 0, lw, lh))
        svg.end()
        painter.drawPixmap(round((T.AD_LOGO[0] - ox) * self.scale), round((T.AD_LOGO[1] - oy) * self.scale), pix)
        draw_baseline(painter, (T.AD_GO[0] - ox, T.AD_GO[1] - oy), self.scale, "点击前往>", self.font(44.70), T.C_SOFT)
        head = self.font(T.AD_HEAD_SIZE)
        metrics = QFontMetrics(head)
        cursor = T.AD_HEAD[0]
        hy = T.AD_HEAD[1]
        for text, color, underline in (
            (T.AD_HEAD_PREFIX, T.C_DIM, False),
            (T.AD_HEAD_LINK, T.C_SOFT, True),
            (T.AD_HEAD_SUFFIX, T.C_DIM, False),
        ):
            draw_baseline(painter, (cursor - ox, hy - oy), self.scale, text, head, color)
            width = metrics.horizontalAdvance(text) / self.scale
            if underline:
                x0 = (cursor - ox) * self.scale
                y0 = (hy - oy) * self.scale + max(2, metrics.underlinePos())
                painter.setPen(QPen(color, max(1, round(2.4 * self.scale))))
                painter.drawLine(round(x0), round(y0), round(x0 + width * self.scale), round(y0))
            cursor += width
        bullet = self.font(38.31)
        for x, y, text in T.AD_BULLETS:
            draw_baseline(painter, (x - ox, y - oy), self.scale, text, bullet, T.C_TEXT)
        draw_baseline(painter, (T.AD_THANKS[0] - ox, T.AD_THANKS[1] - oy), self.scale,
                      "真的很好用，感谢支持！", self.font(35.24), T.C_THANKS)
