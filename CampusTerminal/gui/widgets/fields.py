# SPDX-License-Identifier: GPL-3.0-or-later
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLineEdit

from gui import theme as T
from gui.widgets.paint import ScaledWidget


class GhostEdit(QLineEdit):
    def __init__(self, scale, family, placeholder, parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setFrame(False)
        self.setAttribute(Qt.WA_MacShowFocusRect, False)
        font = T.ui_font(55.55, scale, family)
        self.setFont(font)
        self.setStyleSheet(
            "QLineEdit { background: transparent; border: none; color: #c7c7c7; selection-background-color: #444; }"
            "QLineEdit::placeholder { color: #c7c7c7; }"
        )


def place_edit(edit, box, scale, pad_l, pad_r):
    x, y, w, h = box[:4]
    edit.setGeometry(
        round((x + pad_l) * scale),
        round(y * scale),
        max(8, round((w - pad_l - pad_r) * scale)),
        round(h * scale),
    )


class CardHost(ScaledWidget):
    """Child widgets use the card's local design coordinates."""

    def __init__(self, origin, scale, family, parent=None):
        super().__init__(scale, family, parent)
        self.origin = origin

    def local_box(self, box):
        ox, oy = self.origin
        return (box[0] - ox, box[1] - oy) + box[2:]
