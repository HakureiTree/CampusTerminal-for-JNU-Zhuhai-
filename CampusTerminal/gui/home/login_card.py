# SPDX-License-Identifier: GPL-3.0-or-later
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QPainter

from gui import theme as T
from gui.widgets.checks import IconToggle
from gui.widgets.fields import GhostEdit, place_edit
from gui.widgets.paint import ScaledWidget, draw_glyphs, fill_round, prepare, stroke_round


class LoginCard(ScaledWidget):
    save_account_changed = pyqtSignal(bool)
    save_password_changed = pyqtSignal(bool)

    def __init__(self, scale, family, parent=None):
        super().__init__(scale, family, parent)
        x, y, w, h, _r = T.LOGIN
        self.origin = (x, y)
        self.setGeometry(round(x * scale), round(y * scale), round(w * scale), round(h * scale))
        acc = self._local(T.ACCOUNT_BOX)
        pwd = self._local(T.PASSWORD_BOX)
        self.account = GhostEdit(scale, family, "在此键入你的学号", self)
        place_edit(self.account, acc, scale, 52, 36)
        self.password = GhostEdit(scale, family, "在此键入你的密码", self)
        self.password.setEchoMode(GhostEdit.Password)
        place_edit(self.password, pwd, scale, 52, 120)
        eye_box = self._local(T.EYE)
        self.eye = IconToggle("form/eye_off.png", "form/eye_off.png", scale, eye_box, self)
        self.eye.setCheckable(True)
        self.eye.setToolTip("显示或隐藏密码")
        self.account.setAccessibleName("学号")
        self.password.setAccessibleName("密码")
        self.eye.toggled.connect(self._toggle_echo)
        self.save_account = IconToggle(
            "form/check_green.png", "form/check_gray.png", scale, self._local(T.SAVE_ACC_ICON), self
        )
        self.save_password = IconToggle(
            "form/check_green.png", "form/check_gray.png", scale, self._local(T.SAVE_PWD_ICON), self
        )
        self.save_account.setChecked(True)
        self.save_account.setToolTip("保存学号")
        self.save_password.setToolTip("使用当前 Windows 用户的 DPAPI 保存密码")
        self.save_account.changed.connect(self.save_account_changed)
        self.save_password.changed.connect(self.save_password_changed)

    def _local(self, box):
        ox, oy = self.origin
        return (box[0] - ox, box[1] - oy) + tuple(box[2:])

    def _toggle_echo(self, on):
        self.password.setEchoMode(GhostEdit.Normal if on else GhostEdit.Password)

    def paintEvent(self, _event):
        painter = QPainter(self)
        prepare(painter)
        ox, oy = self.origin
        fill_round(painter, (0, 0, T.LOGIN[2], T.LOGIN[3], T.LOGIN[4]), self.scale, T.C_CARD)
        acc = self._local(T.ACCOUNT_BOX)
        pwd = self._local(T.PASSWORD_BOX)
        fill_round(painter, acc, self.scale, T.C_FIELD)
        stroke_round(painter, acc, self.scale, T.C_STROKE, 4.17)
        fill_round(painter, pwd, self.scale, T.C_FIELD)
        stroke_round(painter, pwd, self.scale, T.C_STROKE, 4.17)
        draw_glyphs(painter, T.G_LOGIN_TITLE, self.origin, self.scale, self.font(103.808), T.C_TEXT)
        draw_glyphs(painter, T.G_LOGIN_BADGE, self.origin, self.scale, self.font(54.83), T.C_MUTED)
        draw_glyphs(painter, T.G_ACCOUNT, self.origin, self.scale, self.font(88.884), T.C_TEXT)
        draw_glyphs(painter, T.G_PASSWORD, self.origin, self.scale, self.font(88.555), T.C_TEXT)
        draw_glyphs(painter, T.G_SAVE_ACC, self.origin, self.scale, self.font(63.852), T.C_TEXT)
        draw_glyphs(painter, T.G_SAVE_PWD, self.origin, self.scale, self.font(63.852), T.C_TEXT)
