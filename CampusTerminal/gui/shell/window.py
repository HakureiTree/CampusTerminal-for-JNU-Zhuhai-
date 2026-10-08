# SPDX-License-Identifier: GPL-3.0-or-later
import os

from PyQt5.QtCore import QRectF, QPoint, Qt, pyqtSignal, QEvent
from PyQt5.QtGui import QPainter, QPainterPath
from gui import theme as T
from gui.home.page import HomePage
from gui.settings.page import SettingsPage
from gui.shell.banner import paint_chrome
from gui.shell.close_btn import CloseButton
from gui.shell.notice_dialog import NoticeOverlay
from gui.shell.resizable import DesignLayout, ResizableWindow


def settings_position(main, panel_size, available, gap):
    """Prefer the SVG's right/bottom alignment, then keep both windows visible."""
    width, height = panel_size.width(), panel_size.height()
    x = main.right() + 1 + gap
    if x + width > available.right() + 1:
        x = main.left() - gap - width
    x = max(available.left(), min(x, available.right() + 1 - width))
    y = max(available.top(), min(main.bottom() + 1 - height, available.bottom() + 1 - height))
    return QPoint(x, y)


class MainWindow(ResizableWindow):
    exit_requested = pyqtSignal()
    revealed = pyqtSignal()
    concealed = pyqtSignal()
    taskbar_created = pyqtSignal()

    def __init__(self, scale, family):
        super().__init__()
        self.scale = scale
        self.family = family
        self._drag = None
        self.tray_available = False
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.resize(round(T.WIN_W * scale), round(T.WIN_H * scale))
        self.setWindowTitle("开源暨珠有线网络终端")
        self.setWindowIcon(T.app_icon())
        self.home = HomePage(scale, family, self)
        self.home.setGeometry(0, 0, self.width(), self.height())
        self.settings = SettingsPage(scale, family, self)
        self.settings.hide()
        self._force_close = False
        self.close_btn = CloseButton(scale, self)
        self.close_btn.closed.connect(self.close)
        self.notice = NoticeOverlay(self)
        self.close_btn.raise_()
        self.home.open_settings.connect(self.show_settings)
        self.settings.back.connect(self.show_home)
        self.settings.back_hit.setToolTip("收起设置")
        self._layout = DesignLayout(self.home, scale)
        self.enable_resize(self.width(), self.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, "_layout"):
            return
        self.scale = min(self.width() / T.WIN_W, self.height() / T.WIN_H)
        w, h = round(T.WIN_W * self.scale), round(T.WIN_H * self.scale)
        self.home.setGeometry((self.width() - w) // 2, (self.height() - h) // 2, w, h)
        self._layout.apply(self.scale)
        self.close_btn.scale = self.scale
        cx, cy, r = T.CLOSE_C
        self.close_btn.setGeometry(self.width() - round(2 * r * self.scale),
                                   round((cy - r) * self.scale),
                                   round(2 * r * self.scale), round(2 * r * self.scale))
        self.notice.setGeometry(self.rect())
        if self.settings.isVisible():
            self._position_settings()
        self._place_grips()
        self.update()

    def present(self):
        self.showNormal()
        screen = self.screen()
        if screen:
            area = screen.availableGeometry()
            self.move(max(area.left(), min(self.x(), area.right() - self.width() + 1)),
                      max(area.top(), min(self.y(), area.bottom() - self.height() + 1)))
        self.raise_()
        self.activateWindow()
        self.revealed.emit()

    def show_settings(self):
        if self.settings.isVisible():
            self.show_home()
            return
        self._position_settings()
        self.settings.show()
        self.settings.raise_()
        self.settings.activateWindow()

    def show_home(self):
        self.settings.hide()
        self.activateWindow()

    def _available_geometry(self):
        return self.screen().availableGeometry()

    def _position_settings(self):
        self.settings.move(settings_position(self.frameGeometry(), self.settings.size(),
                                             self._available_geometry(), max(8, round(49 * self.scale))))

    def moveEvent(self, event):
        super().moveEvent(event)
        if hasattr(self, "settings") and self.settings.isVisible():
            self._position_settings()

    def hideEvent(self, event):
        if hasattr(self, "settings"):
            self.settings.hide()
        super().hideEvent(event)
        self.concealed.emit()

    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange and self.isMinimized():
            self.settings.hide()
        super().changeEvent(event)

    def nativeEvent(self, eventType, message):
        handled = super().nativeEvent(eventType, message)
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            return handled
        try:
            addr = int(message) if message else 0
            if addr and bytes(eventType) == b"windows_generic_MSG":
                from ctypes import wintypes
                from gui.shell.tray import TASKBAR_CREATED
                msg = wintypes.MSG.from_address(addr)
                if msg.message == TASKBAR_CREATED:
                    self.taskbar_created.emit()
        except (TypeError, ValueError, OSError, OverflowError):
            pass
        return handled

    def paintEvent(self, _event):
        painter = QPainter(self)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), T.OUTER_R * self.scale, T.OUTER_R * self.scale)
        painter.setClipPath(path)
        paint_chrome(painter, self.scale, self.family, self.width(), self.height(), self.home.pos())

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.y() < 90 * self.scale:
            self._drag = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPos() - self._drag)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag = None

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape and self.settings.isVisible():
            self.show_home()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        if self._force_close:
            event.accept()
            return
        if self.tray_available:
            self.hide()
        else:
            self.exit_requested.emit()
        event.ignore()

    def quit_app(self):
        self.settings.hide()
        self._force_close = True
        self.close()
