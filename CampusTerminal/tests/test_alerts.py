# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gui.shell.alerts import AlertRouter
from gui.shell.notifications import Notice


class AlertRouterTests(unittest.TestCase):
    def setUp(self):
        self.shown = True
        self.router = AlertRouter(lambda: self.shown)
        self.notice = Notice("校园网终端错误", "示例", "critical")

    def test_unfocused_window_uses_toast_like_hidden(self):
        self.shown = False
        self.router.deliver(self.notice)
        self.assertIsNone(self.router.dialog)
        self.assertIs(self.router.toast, self.notice)

    def test_visible_window_gets_dialog_only(self):
        self.router.deliver(self.notice)
        self.assertIs(self.router.dialog, self.notice)
        self.assertIsNone(self.router.toast)
        self.assertFalse(self.router.toast_armed)
        self.assertFalse(self.router.flashing)

    def test_hidden_window_gets_toast_only(self):
        self.shown = False
        self.router.deliver(self.notice)
        self.assertIsNone(self.router.dialog)
        self.assertIs(self.router.toast, self.notice)
        self.assertTrue(self.router.toast_armed)
        self.assertFalse(self.router.flashing)

    def test_ignored_toast_starts_flash_until_dialog_closed(self):
        self.shown = False
        self.router.deliver(self.notice)
        self.router.toast_ignored()
        self.assertTrue(self.router.flashing)
        self.assertIsNone(self.router.dialog)
        self.shown = True
        self.router.revealed()
        self.assertIs(self.router.dialog, self.notice)
        self.assertIsNone(self.router.toast)
        self.assertTrue(self.router.flashing)
        self.router.dismiss()
        self.assertFalse(self.router.flashing)
        self.assertIsNone(self.router.pending)

    def test_opening_main_does_not_keep_toast(self):
        self.shown = False
        self.router.deliver(self.notice)
        self.shown = True
        self.router.revealed()
        self.assertIs(self.router.dialog, self.notice)
        self.assertIsNone(self.router.toast)
        self.assertFalse(self.router.flashing)

    def test_hiding_unacked_dialog_flashes_without_toast(self):
        self.router.deliver(self.notice)
        self.shown = False
        self.router.concealed()
        self.assertTrue(self.router.flashing)
        self.assertIsNone(self.router.dialog)
        self.assertIsNone(self.router.toast)

    def test_remind_toast_does_not_flash_or_reopen_on_reveal(self):
        remind = Notice("校园网已连接", "连通性验证已通过。", "information", "remind")
        self.shown = False
        self.router.deliver(remind)
        self.assertIs(self.router.toast, remind)
        self.assertFalse(self.router.toast_armed)
        self.router.toast_ignored()
        self.assertFalse(self.router.flashing)
        self.shown = True
        self.router.revealed()
        self.assertIsNone(self.router.dialog)
        self.assertIsNone(self.router.pending)


if __name__ == "__main__":
    unittest.main(verbosity=2)
