# SPDX-License-Identifier: GPL-3.0-or-later
"""Changelog card opened from the settings page: newest release first."""
from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QPainter, QPainterPath
from PyQt5.QtWidgets import QLabel, QPushButton, QScrollArea, QWidget

from gui import theme as T
from gui.widgets.paint import prepare
from gui.widgets.release_notes import ReleaseNotes

EMPTY_NOTES = "该版本未提供更新说明。"


class UpdateLog(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._box = QRectF()
        self.hide()
        self.setGeometry(parent.rect())
        self.title = QLabel("更新日志", self)
        self.title.setWordWrap(True)
        self.body = ReleaseNotes(self)
        self.scroll = QScrollArea(self)
        self.scroll.setWidget(self.body)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(
            "QScrollArea, QScrollArea > QWidget, QScrollArea > QWidget > QWidget "
            "{ background: transparent; border: none; }")
        self.body.setStyleSheet("background: transparent;")
        self.close_btn = QPushButton("关闭", self)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #16c60c; }")
        self.close_btn.clicked.connect(self.hide)

    def show_log(self, sections):
        """sections is a sequence of (heading, markdown) pairs, newest first."""
        body = []
        for heading, notes in sections:
            text = (notes or "").strip() or EMPTY_NOTES
            body.append("## " + heading)
            body.append("")
            body.append(text)
            body.append("")
        self.body.set_notes("\n".join(body).strip())
        self.setGeometry(self.parent().rect())
        self._layout_card()
        self.raise_()
        self.show()
        self.scroll.verticalScrollBar().setValue(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.isVisible():
            self.setGeometry(self.parent().rect())
            self._layout_card()

    def _metrics(self):
        parent = self.parent()
        return getattr(parent, "scale", 0.2), getattr(parent, "family", self.font().family())

    def _layout_card(self):
        scale, family = self._metrics()
        pad = max(10, round(48 * scale))
        gap = max(6, round(20 * scale))
        self.title.setFont(T.ui_font(70.24, scale, family))
        body_font = T.ui_font(45, scale, family)
        body_font.setBold(False)
        self.body.set_presentation(body_font, T.ui_font(54, scale, family))
        self.close_btn.setFont(T.ui_font(52, scale, family))
        self.title.setStyleSheet("color: #c7c7c7; background: transparent;")
        btn_h = max(28, round(96 * scale))
        margin = max(12, round(60 * scale))
        width = min(max(320, round(1200 * scale)), max(200, self.width() - 2 * margin))
        w = min(width + 2 * pad, max(220, self.width() - 24))
        available_h = max(120, self.height() - 24)
        text_w = max(1, w - 2 * pad)
        title_h = max(self.title.fontMetrics().height(), self.title.heightForWidth(text_w))
        natural_h = max(self.body.fontMetrics().height() * 2, self.body.heightForWidth(text_w))
        fixed = 2 * pad + title_h + 2 * gap + btn_h
        body_h = min(natural_h, max(self.body.fontMetrics().height() * 2, available_h - fixed))
        h = min(fixed + body_h, available_h)
        x, y = (self.width() - w) // 2, (self.height() - h) // 2
        self._box = QRectF(x, y, w, h)
        self.title.setGeometry(x + pad, y + pad, text_w, title_h)
        self.scroll.setGeometry(x + pad, y + pad + title_h + gap, text_w, body_h)
        self.scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarAsNeeded if natural_h > body_h else Qt.ScrollBarAlwaysOff)
        close_w = max(72, self.close_btn.fontMetrics().horizontalAdvance("关闭") + round(28 * scale))
        self.close_btn.setGeometry(x + w - pad - close_w, y + h - pad - btn_h, close_w, btn_h)

    def paintEvent(self, _event):
        painter = QPainter(self)
        prepare(painter)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 140))
        if self._box.isEmpty():
            return
        scale, _family = self._metrics()
        radius = min(48 * scale, self._box.height() / 4, self._box.width() / 8)
        card = QPainterPath()
        card.addRoundedRect(self._box, radius, radius)
        painter.fillPath(card, T.C_INNER)
        painter.setPen(T.C_GREEN)
        painter.drawPath(card)
