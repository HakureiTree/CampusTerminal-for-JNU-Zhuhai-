# SPDX-License-Identifier: GPL-3.0-or-later
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFontMetrics, QPainter
from PyQt5.QtWidgets import QLabel, QPushButton, QWidget

from gui import theme as T
from gui.widgets.paint import prepare, stroke_round

TITLES = {"check": "检查更新", "log": "更新日志"}
ACTIONS = {"check": "检查更新", "log": "查看更新日志"}
TOOLTIPS = {
    "check": "检查主仓库的最新正式版本；安装前会提示，更新到当前目录。",
    "log": "查看当前版本与最近一次新版本的更新说明。",
}
TITLE_PX = 70.24
BUTTON_PX = 60
TITLE_MIN = 15
BUTTON_MIN = 13


class UpdateBlock(QWidget):
    check_requested = pyqtSignal()
    log_requested = pyqtSignal()

    def __init__(self, scale, family, parent=None, kind="check"):
        super().__init__(parent)
        self.scale = scale
        self.family = family
        self.kind = kind
        self.box = T.SET_LOG_BOX if kind == "log" else T.SET_UPDATE_BOX
        x, y, w, h, _r = self.box
        self.setGeometry(round(x * scale), round(y * scale), round(w * scale), round(h * scale))
        self.title = QLabel(TITLES[kind], self)
        self.title.setFont(T.ui_font(TITLE_PX, scale, family, TITLE_MIN))
        self.title.setStyleSheet("color: #c7c7c7; background: transparent;")
        self.button = QPushButton(ACTIONS[kind], self)
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.setAccessibleName(TITLES[kind])
        self.button.setStyleSheet("QPushButton { color: #c7c7c7; background: #242424; border: 1px solid #444; border-radius: 5px; } QPushButton:hover { background: #333; } QPushButton:disabled { color: #818181; }")
        self.button.setToolTip(TOOLTIPS[kind])
        self.button.clicked.connect(self.log_requested if kind == "log" else self.check_requested)
        self.relayout(scale)

    def set_status(self, text="检查更新", busy=False):
        self.button.setText(text)
        self.button.setToolTip(text)
        self.button.setEnabled(not busy)

    def set_busy(self, busy=True):
        self.button.setEnabled(not busy)

    def _compute(self, scale):
        _x, _y, w, h, _r = self.box
        title_font = T.ui_font(TITLE_PX, scale, self.family, TITLE_MIN)
        button_font = T.ui_font(BUTTON_PX, scale, self.family, BUTTON_MIN)
        title_metrics = QFontMetrics(title_font)
        button_metrics = QFontMetrics(button_font)
        vpad = max(4, round(8 * scale))
        side_pad = round(52 * scale)
        title_y = round(36 * scale)
        title_h = max(round(88 * scale), title_metrics.height())
        button_x = side_pad
        button_w = max(1, round((w - 104) * scale))
        button_y = max(round(157 * scale), title_y + title_h + vpad)
        button_pad = max(6, round(16 * scale))
        button_h = max(round(120 * scale), button_metrics.height() + 2 * button_pad)
        bottom_pad = max(4, round(16 * scale))
        height = max(round(h * scale), button_y + button_h + bottom_pad)
        return {
            "title_font": title_font,
            "button_font": button_font,
            "title_y": title_y,
            "title_h": title_h,
            "button_x": button_x,
            "button_y": button_y,
            "button_w": button_w,
            "button_h": button_h,
            "width": round(w * scale),
            "height": height,
        }

    def required_height(self, scale):
        return self._compute(scale)["height"]

    def relayout(self, scale):
        data = self._compute(scale)
        self.scale = scale
        self.setGeometry(self.x(), self.y(), data["width"], data["height"])
        self.title.setFont(data["title_font"])
        self.title.setGeometry(data["button_x"], data["title_y"], data["button_w"], data["title_h"])
        self.button.setFont(data["button_font"])
        self.button.setGeometry(data["button_x"], data["button_y"], data["button_w"], data["button_h"])

    def paintEvent(self, _event):
        painter = QPainter(self)
        prepare(painter)
        scale = max(self.scale, 1e-6)
        stroke_round(
            painter,
            (0, 0, max(1.0, self.width() / scale), max(1.0, self.height() / scale), self.box[4]),
            scale,
            T.C_LINE,
            4.17,
        )
