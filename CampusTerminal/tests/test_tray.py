# SPDX-License-Identifier: GPL-3.0-or-later
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gui.shell.tray import TASKBAR_CREATED


class TrayTests(unittest.TestCase):
    def test_taskbar_created_is_a_registered_windows_message(self):
        self.assertGreater(TASKBAR_CREATED, 0xC000)
        self.assertLessEqual(TASKBAR_CREATED, 0xFFFF)


if __name__ == "__main__":
    unittest.main()
