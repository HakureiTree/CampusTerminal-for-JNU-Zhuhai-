# SPDX-License-Identifier: GPL-3.0-or-later
from PyQt5.QtCore import QPoint, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QIcon, QPainter
from PyQt5.QtWidgets import QFrame, QPushButton, QScrollArea, QWidget

from gui import theme as T
from gui.settings.auto_block import AutoBlock
from gui.settings.nic_block import NicBlock
from gui.settings.ip_block import IpBlock
from gui.settings.type_block import TypeBlock
from gui.settings.update_block import UpdateBlock
from gui.shell.resizable import DesignLayout, ResizableWindow
from gui.shell.update_log import UpdateLog
from gui.widgets.paint import draw_glyphs, fill_round, prepare

SCROLL_QSS = (
    "QScrollArea { background: transparent; border: none; }"
    "QScrollArea > QWidget { background: transparent; }"
    "QScrollArea > QWidget > QWidget { background: transparent; }"
    "QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }"
    "QScrollBar::handle:vertical { background: #444444; border-radius: 4px; min-height: 24px; }"
    "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
    "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
)


class BackHit(QPushButton):
    def __init__(self, scale, family, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFlat(True)
        self.setStyleSheet("QPushButton { background: transparent; border: none; }")
        self.setGeometry(round(40 * scale), round(80 * scale), round(280 * scale), round(120 * scale))


class SettingsPage(ResizableWindow):
    back = pyqtSignal()
    adapter_changed = pyqtSignal(str)
    type_changed = pyqtSignal(str)
    option_changed = pyqtSignal(str, bool)
    check_update = pyqtSignal()
    log_requested = pyqtSignal()

    def __init__(self, scale, family, parent=None):
        super().__init__(parent)
        self.scale = scale
        self.family = family
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowTitle("设置 · 校园网终端")
        self.resize(round(T.SET_W * scale), round(T.SET_H * scale))
        self.scroll = QScrollArea(self)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setWidgetResizable(False)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.scroll.setStyleSheet(SCROLL_QSS)
        self.scroll.viewport().setAutoFillBackground(False)
        self.content = QWidget()
        self.content.setAutoFillBackground(False)
        self.scroll.setWidget(self.content)
        self.content.setGeometry(0, 0, round(T.SET_W * scale), round(T.SET_H * scale))
        self.nic = NicBlock(scale, family, (0, 0), self.content)
        self.ip = IpBlock(scale, family, self.content)
        self.types = TypeBlock(scale, family, self.content)
        self.updates = UpdateBlock(scale, family, self.content)
        self.update_log = UpdateBlock(scale, family, self.content, kind="log")
        self.autos = AutoBlock(scale, family, self.content)
        for block in (self.types, self.autos):
            block.move(block.x(), block.y() + round(T.SET_IP_SHIFT * scale))
        self.autos.move(self.autos.x(),
                        self.autos.y() + round((T.SET_UPDATE_SHIFT + T.SET_LOG_SHIFT) * scale))
        self.back_hit = BackHit(scale, family, self.content)
        self.back_hit.clicked.connect(self.back)
        self.nic.adapter_changed.connect(self.adapter_changed)
        self.types.type_changed.connect(self.type_changed)
        self.autos.option_changed.connect(self.option_changed)
        self.updates.check_requested.connect(self.check_update)
        self.update_log.log_requested.connect(self.log_requested)
        self.log_card = UpdateLog(self)
        self.log_card.setGeometry(self.rect())
        self.close_button = QPushButton(self)
        self.close_button.setIcon(QIcon(str(T.ICONS / "chrome/close.png")))
        self.close_button.setStyleSheet("QPushButton { background: transparent; border: none; } QPushButton:hover { background: #444; border-radius: 4px; }")
        self.close_button.setToolTip("收起设置")
        self.close_button.setAccessibleName("收起设置")
        self.close_button.clicked.connect(self.back)
        self._blocks = (self.nic, self.ip, self.types, self.updates, self.update_log, self.autos)
        self._layout = DesignLayout(self.content, scale)
        self.enable_resize(self.width(), self.height())
        self._apply_layout()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, "_layout"):
            return
        self._apply_layout()

    def _apply_layout(self):
        self.scale = min(self.width() / T.SET_W, self.height() / T.SET_H)
        if self.scale <= 0:
            return
        self.scroll.setGeometry(self.rect())
        self._layout.apply(self.scale)
        shift = 0
        for block in self._blocks:
            if shift:
                block.move(block.x(), block.y() + shift)
            if hasattr(block, "relayout"):
                before = block.height()
                block.relayout(self.scale)
                shift += block.height() - before
        last_bottom = max(block.geometry().bottom() + 1 for block in self._blocks)
        margin = max(8, round(48 * self.scale))
        width = round(T.SET_W * self.scale)
        height = max(round(T.SET_H * self.scale), last_bottom + margin)
        self.content.setFixedSize(width, height)
        self.log_card.setGeometry(self.rect())
        side = max(24, round(105 * self.scale))
        edge = max(8, round(45 * self.scale))
        self.close_button.setGeometry(self.width() - side - edge, edge, side, side)
        self.close_button.setIconSize(QSize(round(side * .6), round(side * .6)))
        self._place_grips()
        self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.back.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def show_update_log(self, sections):
        self.log_card.show_log(sections)

    def closeEvent(self, event):
        self.back.emit()
        event.accept()

    def paintEvent(self, _event):
        painter = QPainter(self)
        prepare(painter)
        scale = max(self.scale, 1e-6)
        fill_round(
            painter,
            (0, 0, max(1.0, self.width() / scale), max(1.0, self.height() / scale), T.SET_R),
            scale,
            T.C_INNER,
        )
        origin = self.content.mapTo(self, QPoint(0, 0))
        painter.translate(origin)
        draw_glyphs(
            painter, T.G_SET_TITLE, (0, 0), scale,
            T.ui_font(103.808, scale, self.family), T.C_TEXT,
        )
