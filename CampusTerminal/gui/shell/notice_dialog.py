# SPDX-License-Identifier: GPL-3.0-or-later
from time import monotonic

from PyQt5.QtCore import QEasingCurve, QPropertyAnimation, QRectF, QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPainterPath
from PyQt5.QtWidgets import QGraphicsOpacityEffect, QLabel, QPushButton, QWidget

from gui import theme as T
from gui.shell.notifications import is_confirm, remind_ms
from gui.widgets.paint import prepare


_ACCENT = {
    "information": T.C_GREEN,
    "warning": QColor("#c9a227"),
    "critical": QColor("#e81123"),
}


class NoticeOverlay(QWidget):
    dismissed = pyqtSignal()
    action_requested = pyqtSignal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.notice = None
        self.accent = _ACCENT["information"]
        self._box = QRectF()
        self._progress = 0.0
        self._started = 0.0
        self._duration = 1.0
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.hide()
        self.title = QLabel(self)
        self.title.setWordWrap(True)
        self.body = QLabel(self)
        self.body.setWordWrap(True)
        self.body.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.ok = QPushButton("知道了", self)
        self.ok.setCursor(Qt.PointingHandCursor)
        self.ok.clicked.connect(self._dismiss)
        self.ok.setStyleSheet("QPushButton { background: transparent; border: none; color: #c7c7c7; }")
        self.extra = QPushButton("安装学校官方客户端", self)
        self.extra.setCursor(Qt.PointingHandCursor)
        self.extra.clicked.connect(self._action)
        self.extra.setStyleSheet("QPushButton { background: transparent; border: none; color: #c6c6c6; }")
        self.extra.hide()
        self._life = QTimer(self)
        self._life.timeout.connect(self._tick)
        self._fx = QGraphicsOpacityEffect(self)
        self._fx.setOpacity(0)
        self.setGraphicsEffect(self._fx)
        self._anim = QPropertyAnimation(self._fx, b"opacity", self)
        self._anim.setEasingCurve(QEasingCurve.InOutQuad)
        self._anim.finished.connect(self._anim_done)
        self._fading_out = False

    def show_notice(self, notice):
        self.notice = notice
        self.accent = _ACCENT.get(notice.severity, _ACCENT["information"])
        self.title.setText(notice.title)
        self.body.setText(notice.body)
        self._progress = 0.0
        self._life.stop()
        self._fading_out = False
        self.setGeometry(self.parent().rect())
        self._layout_card()
        self.raise_()
        appearing = not self.isVisible() or self._fx.opacity() < 0.05
        self.show()
        self._anim.stop()
        self._anim.setDuration(220)
        self._anim.setStartValue(0.0 if appearing else max(0.15, self._fx.opacity()))
        self._anim.setEndValue(1.0)
        self._anim.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.isVisible():
            self.setGeometry(self.parent().rect())
            self._layout_card()

    def mousePressEvent(self, event):
        if self.notice is not None and not is_confirm(self.notice):
            self._dismiss()
            event.accept()
            return
        super().mousePressEvent(event)

    def _metrics(self):
        scale = getattr(self.parent(), "scale", 0.2)
        family = getattr(self.parent(), "family", self.font().family())
        return scale, family

    def _layout_card(self):
        scale, family = self._metrics()
        pad = max(10, round(40 * scale))
        gap = max(6, round(18 * scale))
        bar = max(4, round(12 * scale))
        inset = max(7, round(22 * scale))
        confirm = self.notice is None or is_confirm(self.notice)
        self.title.setFont(T.ui_font(64, scale, family))
        self.body.setFont(T.ui_font(44, scale, family))
        self.ok.setFont(T.ui_font(48, scale, family))
        self.title.setStyleSheet("color: #c7c7c7; background: transparent;")
        self.body.setStyleSheet("color: #818181; background: transparent;")
        text_w = min(max(200, round(980 * scale)), max(160, self.width() - 2 * pad - 48))
        title_h = max(self.title.fontMetrics().height(), self.title.heightForWidth(text_w))
        body_h = max(self.body.fontMetrics().height(), self.body.heightForWidth(text_w))
        btn_w, btn_h = max(72, round(200 * scale)), max(28, round(64 * scale))
        extra = bool(self.notice and self.notice.action)
        extra_w = max(btn_w, round(420 * scale)) if extra else 0
        inner_left = inset + bar + max(8, round(18 * scale))
        w = inner_left + text_w + pad
        h = pad + title_h + gap + body_h + pad
        if confirm:
            h += gap + btn_h
        w = min(max(w, inner_left + extra_w + btn_w + pad), max(180, self.width() - 32))
        h = min(h, max(120, self.height() - 32))
        x = (self.width() - w) // 2
        y = (self.height() - h) // 2
        self._box = QRectF(x, y, w, h)
        self.title.setGeometry(x + inner_left, y + pad, text_w, title_h)
        self.body.setGeometry(x + inner_left, y + pad + title_h + gap, text_w, body_h)
        self.ok.setVisible(confirm)
        self.extra.setVisible(confirm and extra)
        if confirm:
            self.ok.setGeometry(x + w - pad - btn_w, y + h - pad - btn_h, btn_w, btn_h)
            if extra:
                self.extra.setGeometry(x + inner_left, y + h - pad - btn_h, extra_w, btn_h)

    def paintEvent(self, _event):
        painter = QPainter(self)
        prepare(painter)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 140))
        if self._box.isEmpty():
            return
        scale, _family = self._metrics()
        x, y, w, h = self._box.x(), self._box.y(), self._box.width(), self._box.height()
        r = min(48 * scale, h / 4, w / 8)
        card = QPainterPath()
        card.addRoundedRect(QRectF(x, y, w, h), r, r)
        painter.fillPath(card, T.C_INNER)
        painter.setPen(T.C_OUTER)
        painter.drawPath(card)
        inset = max(7, round(22 * scale))
        bw = max(4, round(12 * scale))
        full = QRectF(x + inset, y + inset, bw, h - 2 * inset)
        remain = max(0.0, 1.0 - self._progress)
        bar_h = full.height() * remain
        bar = QRectF(full.x(), full.center().y() - bar_h / 2, full.width(), bar_h)
        if bar.height() > bw:
            painter.setPen(Qt.NoPen)
            painter.setBrush(self.accent)
            painter.setClipPath(card)
            painter.drawRoundedRect(bar, bw / 2, bw / 2)

    def _tick(self):
        t = (monotonic() - self._started) / self._duration
        self._progress = min(1.0, t)
        self.update()
        if t >= 1:
            self._life.stop()
            self._dismiss()

    def _action(self):
        act = self.notice.action if self.notice else ""
        self._dismiss()
        if act:
            self.action_requested.emit(act)

    def _dismiss(self):
        if self._fading_out:
            return
        self._life.stop()
        self._fading_out = True
        self.dismissed.emit()
        self._anim.stop()
        self._anim.setDuration(180)
        self._anim.setStartValue(self._fx.opacity())
        self._anim.setEndValue(0.0)
        self._anim.start()

    def _anim_done(self):
        if self._fading_out:
            self.hide()
            self.notice = None
            self._fading_out = False
            self._fx.setOpacity(0)
            return
        if self.notice is not None and not is_confirm(self.notice) and not self._life.isActive():
            self._duration = max(0.2, remind_ms(self.notice) / 1000)
            self._started = monotonic()
            self._life.start(16)
