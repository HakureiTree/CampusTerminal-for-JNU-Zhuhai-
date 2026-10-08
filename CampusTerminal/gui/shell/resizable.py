# SPDX-License-Identifier: GPL-3.0-or-later
"""Frameless resize grips and state-preserving scaling of the SVG-based UI."""
import re

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QColor, QFont, QPainter
from PyQt5.QtWidgets import QAbstractButton, QWidget


class DesignLayout:
    def __init__(self, parent, scale):
        self.base_scale = scale
        self.items = []
        self._capture(parent)

    def _capture(self, parent):
        for child in parent.findChildren(QWidget, options=Qt.FindDirectChildrenOnly):
            if child.isWindow():
                continue
            self.items.append((child, child.geometry(), QWidget.font(child), child.styleSheet(),
                               child.iconSize() if isinstance(child, QAbstractButton) else None))
            self._capture(child)

    def apply(self, scale):
        ratio = scale / self.base_scale
        for child, rect, original_font, style, icon in self.items:
            if hasattr(child, "scale"):
                child.scale = scale
            child.setGeometry(round(rect.x() * ratio), round(rect.y() * ratio),
                              round(rect.width() * ratio), round(rect.height() * ratio))
            font = QFont(original_font)
            if font.pixelSize() > 0:
                font.setPixelSize(max(1, round(font.pixelSize() * ratio)))
            else:
                font.setPointSizeF(max(1, font.pointSizeF() * ratio))
            child.setFont(font)
            if style:
                child.setStyleSheet(re.sub(r"(\d+(?:\.\d+)?)px",
                                          lambda m: f"{round(float(m[1]) * ratio)}px", style))
            if icon is not None:
                child.setIconSize(QSize(round(icon.width() * ratio), round(icon.height() * ratio)))
            child.update()


class ResizeGrip(QWidget):
    def __init__(self, edges, cursor, parent):
        super().__init__(parent)
        self.edges = edges
        self._start = None
        self.setCursor(cursor)
        self.setToolTip("拖动边框调整窗口大小")

    def paintEvent(self, event):
        # Layered Windows windows pass clicks through fully transparent corners.
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 1))

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        window = self.window()
        handle = window.windowHandle()
        # Qt delegates to the OS, including mixed-DPI desktops and all eight edges.
        if handle is None or not handle.startSystemResize(self.edges):
            self._start = (event.globalPos(), window.geometry())
        event.accept()

    def mouseMoveEvent(self, event):
        if self._start is None or not event.buttons() & Qt.LeftButton:
            return super().mouseMoveEvent(event)
        origin, initial = self._start
        delta = event.globalPos() - origin
        rect = type(initial)(initial)
        window = self.window()
        if self.edges & Qt.LeftEdge:
            rect.setLeft(min(initial.left() + delta.x(), initial.right() + 1 - window.minimumWidth()))
        if self.edges & Qt.RightEdge:
            rect.setRight(max(initial.right() + delta.x(), initial.left() + window.minimumWidth() - 1))
        if self.edges & Qt.TopEdge:
            rect.setTop(min(initial.top() + delta.y(), initial.bottom() + 1 - window.minimumHeight()))
        if self.edges & Qt.BottomEdge:
            rect.setBottom(max(initial.bottom() + delta.y(), initial.top() + window.minimumHeight() - 1))
        window.setGeometry(rect)
        event.accept()

    def mouseReleaseEvent(self, event):
        self._start = None
        super().mouseReleaseEvent(event)


class ResizableWindow(QWidget):
    def enable_resize(self, width, height):
        self.setMinimumSize(round(width * .8), round(height * .8))
        self.resize(width, height)
        specs = [
            (Qt.LeftEdge, Qt.SizeHorCursor), (Qt.RightEdge, Qt.SizeHorCursor),
            (Qt.TopEdge, Qt.SizeVerCursor), (Qt.BottomEdge, Qt.SizeVerCursor),
            (Qt.LeftEdge | Qt.TopEdge, Qt.SizeFDiagCursor),
            (Qt.RightEdge | Qt.TopEdge, Qt.SizeBDiagCursor),
            (Qt.LeftEdge | Qt.BottomEdge, Qt.SizeBDiagCursor),
            (Qt.RightEdge | Qt.BottomEdge, Qt.SizeFDiagCursor),
        ]
        self.resize_grips = [ResizeGrip(edges, cursor, self) for edges, cursor in specs]
        self._place_grips()

    def _place_grips(self):
        if not hasattr(self, "resize_grips"):
            return
        w, h, edge = self.width(), self.height(), 6
        corner = 12
        boxes = [(0, corner, edge, h - 2 * corner), (w - edge, corner, edge, h - 2 * corner),
                 (corner, 0, w - 2 * corner, edge), (corner, h - edge, w - 2 * corner, edge),
                 (0, 0, corner, corner), (w - corner, 0, corner, corner),
                 (0, h - corner, corner, corner), (w - corner, h - corner, corner, corner)]
        for grip, box in zip(self.resize_grips, boxes):
            grip.setGeometry(*box)
            grip.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_grips()
