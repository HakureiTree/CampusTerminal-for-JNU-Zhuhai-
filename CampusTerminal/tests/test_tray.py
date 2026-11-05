# SPDX-License-Identifier: GPL-3.0-or-later
import os
import unittest
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from unittest.mock import patch
from PyQt5.QtWidgets import QApplication

from gui.shell.tray import AppTray, TASKBAR_CREATED

APP = QApplication.instance() or QApplication([])


class TrayTests(unittest.TestCase):
    def test_taskbar_created_is_a_registered_windows_message(self):
        self.assertGreater(TASKBAR_CREATED, 0xC000)
        self.assertLessEqual(TASKBAR_CREATED, 0xFFFF)


class TrayRedrawCacheTests(unittest.TestCase):
    def setUp(self):
        self.tray = AppTray()
        self.updates = []
        patcher = patch.object(AppTray, "setIcon", side_effect=self.updates.append)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tray._flash.stop)
        self.addCleanup(self.tray.hide)

    def test_ten_thousand_identical_phases_update_the_icon_once(self):
        self.tray.set_phase("online")
        for _ in range(10_000):
            self.tray.set_phase("online")
        self.assertEqual(len(self.updates), 1)
        self.assertIs(self.updates[0], self.tray._icons["ok"])
        for _ in range(100):
            self.tray.set_phase("online")
        self.assertEqual(len(self.updates), 1)

    def test_each_tone_change_redraws_once(self):
        for phase, tone in [("online", "ok"), ("connecting", "wait"), ("error", "err"),
                            ("fallback", "wait"), ("online", "ok")]:
            self.tray.set_phase(phase)
            self.assertIs(self.tray._icons[tone], self.updates[-1])

    def test_flashing_transitions_each_redraw_once_and_reuse_cache(self):
        self.tray.set_phase("error")
        self.updates.clear()
        self.tray.start_flash()
        self.assertTrue(self.tray.flashing)
        self.tray._blink()
        self.assertEqual(len(self.updates), 1)
        self.assertIs(self.updates[0], self.tray._icons["idle"])
        self.tray._blink()
        self.assertEqual(len(self.updates), 2)
        self.assertIs(self.updates[1], self.tray._icons["err"])
        self.tray._blink()
        self.assertEqual(len(self.updates), 3)
        self.assertIs(self.updates[2], self.tray._icons["idle"])
        self.tray._blink()
        self.assertEqual(len(self.updates), 4)
        self.assertIs(self.updates[3], self.tray._icons["err"])

    def test_stop_flash_does_not_leave_the_dark_icon(self):
        self.tray.set_phase("online")
        self.updates.clear()
        self.tray.start_flash()
        self.tray._blink()
        self.assertIs(self.updates[-1], self.tray._icons["idle"])
        self.tray.stop_flash()
        self.assertFalse(self.tray.flashing)
        self.assertIs(self.updates[-1], self.tray._icons["ok"])
        self.assertEqual(len(self.updates), 2)

    def test_restore_forces_one_refresh_even_when_the_tone_is_unchanged(self):
        self.tray.set_phase("online")
        self.updates.clear()
        with patch.object(self.tray, "hide"), patch.object(self.tray, "show"):
            self.tray.restore()
        self.assertEqual(len(self.updates), 1)
        self.assertIs(self.updates[0], self.tray._icons["ok"])
        with patch.object(self.tray, "hide"), patch.object(self.tray, "show"):
            self.tray.restore()
        self.assertEqual(len(self.updates), 2)

    def test_flashing_property_tracks_the_flash_timer(self):
        self.assertFalse(self.tray.flashing)
        self.tray.start_flash()
        self.assertTrue(self.tray.flashing)
        self.tray.stop_flash()
        self.assertFalse(self.tray.flashing)


if __name__ == "__main__":
    unittest.main()
