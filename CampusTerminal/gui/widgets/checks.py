# SPDX-License-Identifier: GPL-3.0-or-later
from PyQt5.QtCore import QEvent, QRect, QRectF, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QPainter, QPainterPath, QPen, QPixmap
from PyQt5.QtWidgets import QAbstractButton

from gui import theme as T
from gui.widgets.paint import prepare


class IconToggle(QAbstractButton):
    changed = pyqtSignal(bool)

    def __init__(self, on_rel, off_rel, scale, box, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.on_rel = on_rel
        self.off_rel = off_rel
        self.scale = scale
        x, y, w, h = box[:4]
        self.setGeometry(round(x * scale), round(y * scale), round(w * scale), round(h * scale))
        self.toggled.connect(self.changed)

    def sizeHint(self):
        return QSize(self.width(), self.height())

    def paintEvent(self, _event):
        painter = QPainter(self)
        prepare(painter)
        rel = self.on_rel if self.isChecked() else self.off_rel
        pix = QPixmap(str(T.ICONS / rel))
        if pix.isNull():
            return
        painter.drawPixmap(self.rect(), pix)


class BoxToggle(QAbstractButton):
    """Checkbox whose hit area is its whole widget rect.

    The box and visual_box arguments are widget-pixel rectangles (already
    scaled). The compact glyph is drawn inside visual_box with QPainterPath so
    it is independent of pixmaps and stays crisp on every device pixel ratio.
    """

    changed = pyqtSignal(bool)
    RADIUS = 4.0
    BORDER_WIDTH = 1.6
    CHECK_WIDTH = 2.0

    def __init__(self, scale, box, parent=None, visual_box=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.scale = scale
        self._visual = QRect()
        self._screen_handle = None
        self.setGeometry(self._pixel_rect(box))
        self.set_visual_rect(visual_box if visual_box is not None else box)
        self.toggled.connect(self.changed)

    @staticmethod
    def _pixel_rect(box):
        if isinstance(box, QRect):
            return QRect(box)
        if isinstance(box, QRectF):
            return QRect(round(box.x()), round(box.y()),
                         max(1, round(box.width())), max(1, round(box.height())))
        x, y, w, h = box[:4]
        return QRect(round(x), round(y), max(1, round(w)), max(1, round(h)))

    def set_visual_rect(self, box):
        self._visual = self._pixel_rect(box)
        self.update()

    def visual_rect(self):
        return QRect(self._visual)

    def sizeHint(self):
        return QSize(self.width(), self.height())

    def showEvent(self, event):
        super().showEvent(event)
        self._bind_screen()

    def _bind_screen(self):
        handle = self.window().windowHandle()
        if handle is None or handle is self._screen_handle:
            return
        if self._screen_handle is not None:
            try:
                self._screen_handle.screenChanged.disconnect(self._screen_changed)
            except (TypeError, RuntimeError):
                pass
        self._screen_handle = handle
        handle.screenChanged.connect(self._screen_changed)

    def _screen_changed(self, *_args):
        self.update()

    def event(self, event):
        screen_change = getattr(QEvent, "ScreenChangeInternal", None)
        if screen_change is not None and event.type() == screen_change:
            self.update()
        return super().event(event)

    def device_snapped(self, value):
        """Snap a logical pixel value onto the current device pixel grid."""
        dpr = self.devicePixelRatioF() or 1.0
        return round(value * dpr) / dpr

    def _device_rect(self):
        dpr = self.devicePixelRatioF() or 1.0
        rect = QRectF(self._visual)
        left = round(rect.left() * dpr) / dpr
        top = round(rect.top() * dpr) / dpr
        right = round(rect.right() * dpr) / dpr
        bottom = round(rect.bottom() * dpr) / dpr
        if right - left < 2 or bottom - top < 2:
            return QRectF(rect)
        return QRectF(left, top, right - left, bottom - top)

    def paintEvent(self, _event):
        painter = QPainter(self)
        prepare(painter)
        if not self.isEnabled():
            painter.setOpacity(.4)
        rect = self._device_rect()
        if rect.width() <= 1 or rect.height() <= 1:
            return
        border = self.device_snapped(self.BORDER_WIDTH)
        pad = border / 2
        inner = rect.adjusted(pad, pad, -pad, -pad)
        radius = min(self.RADIUS, inner.width() / 4, inner.height() / 4)
        outline = QPainterPath()
        outline.addRoundedRect(inner, radius, radius)
        pen = QPen(T.C_LINE, border)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(outline)
        if not self.isChecked():
            return
        x, y, w, h = inner.x(), inner.y(), inner.width(), inner.height()
        mark = QPainterPath()
        mark.moveTo(x + .24 * w, y + .52 * h)
        mark.lineTo(x + .43 * w, y + .72 * h)
        mark.lineTo(x + .76 * w, y + .30 * h)
        pen = QPen(T.C_SOFT, self.device_snapped(self.CHECK_WIDTH))
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(mark)
