# SPDX-License-Identifier: GPL-3.0-or-later
from PyQt5.QtCore import QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPainterPath
from PyQt5.QtWidgets import QLabel, QPushButton, QScrollArea, QStyle, QWidget

from gui import theme as T
from gui.bridge.update import EMPTY_NOTES
from gui.widgets.paint import prepare
from gui.widgets.release_notes import ReleaseNotes


def _button(text, parent, color):
    button = QPushButton(text, parent)
    button.setCursor(Qt.PointingHandCursor)
    button.setStyleSheet("QPushButton { background: transparent; border: none; color: " + color + "; }")
    return button


class _Card(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self._box = QRectF()
        self.hide()
        self.setGeometry(parent.rect())

    def present(self):
        self.setGeometry(self.parent().rect())
        self._layout_card()
        self.raise_()
        self.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.isVisible():
            self.setGeometry(self.parent().rect())
            self._layout_card()

    def paintEvent(self, _event):
        painter = QPainter(self)
        prepare(painter)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 140))
        if self._box.isEmpty():
            return
        scale, _family = self._metrics()
        x, y, w, h = self._box.x(), self._box.y(), self._box.width(), self._box.height()
        radius = min(48 * scale, h / 4, w / 8)
        card = QPainterPath()
        card.addRoundedRect(QRectF(x, y, w, h), radius, radius)
        painter.fillPath(card, T.C_INNER)
        painter.setPen(T.C_GREEN)
        painter.drawPath(card)

    def _metrics(self):
        parent = self.parent()
        return getattr(parent, "scale", 0.2), getattr(parent, "family", self.font().family())


class UpdateChoice(_Card):
    cancelled = pyqtSignal()
    ignore_requested = pyqtSignal()
    update_requested = pyqtSignal()

    def __init__(self, parent):
        super().__init__(parent)
        self.version_text = ""
        self.title = QLabel(self)
        self.title.setWordWrap(True)
        self.body = ReleaseNotes()
        self.scroll = QScrollArea(self)
        self.scroll.setWidget(self.body)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea, QLabel { background: transparent; border: none; }")
        self.cancel_btn = _button("取消", self, "#818181")
        self.ignore_btn = _button("忽略该版本", self, "#c7c7c7")
        self.update_btn = _button("更新", self, "#16c60c")
        self.cancel_btn.clicked.connect(self._cancel)
        self.ignore_btn.clicked.connect(self.ignore_requested.emit)
        self.update_btn.clicked.connect(self._update)

    def show_offer(self, version, notes):
        self.version_text = str(version or "")
        self.title.setText("发现新版本 V" + self.version_text)
        text = (notes or "").strip()
        self.body.set_notes((text or EMPTY_NOTES)[:16000])
        self.present()
        self.scroll.verticalScrollBar().setValue(0)

    def _cancel(self):
        self.hide()
        self.cancelled.emit()

    def _update(self):
        self.hide()
        self.update_requested.emit()

    def _layout_card(self):
        scale, family = self._metrics()
        pad = max(10, round(36 * scale))
        gap = max(6, round(16 * scale))
        self.title.setFont(T.ui_font(58, scale, family))
        body_font = T.ui_font(40, scale, family)
        body_font.setBold(False)
        self.body.set_presentation(body_font, T.ui_font(48, scale, family))
        for button in (self.cancel_btn, self.ignore_btn, self.update_btn):
            button.setFont(T.ui_font(42, scale, family))
        self.title.setStyleSheet("color: #c7c7c7; background: transparent;")
        self.body.setStyleSheet("color: #c6c6c6; background: transparent;")
        self.body.setMinimumSize(0, 0)
        btn_h = max(28, round(64 * scale))
        buttons = (self.cancel_btn, self.ignore_btn, self.update_btn)
        widths = [max(72, button.fontMetrics().horizontalAdvance(button.text()) + round(24 * scale))
                  for button in buttons]
        margin = max(12, round(48 * scale))
        available_w = max(1, self.width() - 2 * margin)
        available_h = max(1, self.height() - 2 * margin)
        row_w = sum(widths) + 2 * gap
        natural_w = max(self.title.fontMetrics().horizontalAdvance(self.title.text()),
                        self.body.natural_width())
        max_w = min(available_w, max(row_w + 2 * pad, round(1800 * scale)))
        w = min(max_w, max(row_w + 2 * pad, natural_w + 2 * pad))
        text_w = max(1, w - 2 * pad)
        stacked = row_w > text_w
        buttons_h = len(buttons) * btn_h + 2 * gap if stacked else btn_h
        title_h = max(self.title.fontMetrics().height(), self.title.heightForWidth(text_w))
        natural_h = max(self.body.fontMetrics().height() * 2, self.body.heightForWidth(text_w))
        fixed_h = 2 * pad + title_h + 2 * gap + buttons_h
        body_h = min(natural_h, max(1, available_h - fixed_h))
        h = fixed_h + body_h
        x, y = (self.width() - w) // 2, (self.height() - h) // 2
        self._box = QRectF(x, y, w, h)
        self.title.setGeometry(x + pad, y + pad, text_w, title_h)
        self.scroll.setGeometry(x + pad, y + pad + title_h + gap, text_w, body_h)
        self.scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarAsNeeded if natural_h > body_h else Qt.ScrollBarAlwaysOff)
        if natural_h > body_h:
            text_w = max(1, text_w - self.scroll.style().pixelMetric(QStyle.PM_ScrollBarExtent))
        self.body.setMinimumHeight(max(self.body.fontMetrics().height() * 2, self.body.heightForWidth(text_w)))
        buttons_y = y + pad + title_h + 2 * gap + body_h
        if stacked:
            for index, button in enumerate(buttons):
                button.setGeometry(x + pad, buttons_y + index * (btn_h + gap), w - 2 * pad, btn_h)
        else:
            cursor = x + w - pad
            for button, width in zip(reversed(buttons), reversed(widths)):
                cursor -= width
                button.setGeometry(cursor, buttons_y, width, btn_h)
                cursor -= gap


class IgnoreConfirm(_Card):
    cancelled = pyqtSignal()
    confirmed = pyqtSignal()

    def __init__(self, parent):
        super().__init__(parent)
        self.body = QLabel("确认忽略该版本更新？", self)
        self.body.setWordWrap(True)
        self.body.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.cancel_btn = _button("取消", self, "#818181")
        self.confirm_btn = _button("确认忽略", self, "#16c60c")
        self.cancel_btn.clicked.connect(self._cancel)
        self.confirm_btn.clicked.connect(self._confirm)

    def ask(self):
        self.body.setText("确认忽略该版本更新？")
        self.present()

    def _cancel(self):
        self.hide()
        self.cancelled.emit()

    def _confirm(self):
        self.hide()
        self.confirmed.emit()

    def _layout_card(self):
        scale, family = self._metrics()
        pad = max(10, round(36 * scale))
        gap = max(6, round(16 * scale))
        self.body.setFont(T.ui_font(48, scale, family))
        self.cancel_btn.setFont(T.ui_font(42, scale, family))
        self.confirm_btn.setFont(T.ui_font(42, scale, family))
        self.body.setStyleSheet("color: #c7c7c7; background: transparent;")
        text_w = min(max(220, round(860 * scale)), max(180, self.width() - 2 * pad))
        body_h = max(self.body.fontMetrics().height(), self.body.heightForWidth(text_w))
        btn_h = max(28, round(64 * scale))
        cancel_w = max(72, self.cancel_btn.fontMetrics().horizontalAdvance("取消") + round(28 * scale))
        confirm_w = max(96, self.confirm_btn.fontMetrics().horizontalAdvance("确认忽略") + round(28 * scale))
        w = min(max(text_w + 2 * pad, cancel_w + confirm_w + 3 * pad), max(220, self.width() - 24))
        h = min(pad + body_h + gap + btn_h + pad, max(120, self.height() - 24))
        x, y = (self.width() - w) // 2, (self.height() - h) // 2
        self._box = QRectF(x, y, w, h)
        self.body.setGeometry(x + pad, y + pad, w - 2 * pad, body_h)
        self.confirm_btn.setGeometry(x + w - pad - confirm_w, y + h - pad - btn_h, confirm_w, btn_h)
        self.cancel_btn.setGeometry(x + w - pad - confirm_w - pad - cancel_w, y + h - pad - btn_h, cancel_w, btn_h)
