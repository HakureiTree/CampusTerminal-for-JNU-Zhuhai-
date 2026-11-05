# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings-side update gate: layout order, the changelog row and its card."""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtWidgets import QApplication
from gui import theme
from gui.shell.window import MainWindow

APP = QApplication.instance() or QApplication([])


class SettingsUpdateTests(unittest.TestCase):
    def setUp(self):
        self.window = MainWindow(.2, theme.pick_font_family())
        self.addCleanup(self.window.close)

    def test_update_rows_and_cards_keep_order_and_fit_while_resizing(self):
        settings = self.window.settings
        settings.autos.set_options({"auto_check_update": True, "auto_update": True})
        for width, height in ((300, 560), (600, 700), (350, 750)):
            settings.resize(width, height)
            APP.processEvents()
            blocks = (settings.nic, settings.ip, settings.types, settings.updates,
                      settings.update_log, settings.autos)
            for above, below in zip(blocks, blocks[1:]):
                self.assertLess(above.geometry().bottom(), below.geometry().top())
            for block in blocks:
                self.assertTrue(settings.content.rect().contains(block.geometry()))
            self.assertTrue(settings.autos.toggles["auto_check_update"].isChecked())
            self.assertTrue(settings.autos.toggles["auto_update"].isChecked())
        self.assertEqual(list(settings.autos.toggles)[-2:], ["auto_check_update", "auto_update"])

    def test_changelog_card_lists_newest_first_and_falls_back(self):
        settings = self.window.settings
        settings.show_update_log([("新版本 V9.9.9", "新功能"), ("当前版本 V1.0.0", "")])
        self.assertFalse(settings.log_card.isHidden())
        text = settings.log_card.body.text()
        self.assertIn("新功能", text)
        self.assertIn("该版本未提供更新说明。", text)
        self.assertLess(text.index("新功能"), text.index("该版本未提供更新说明。"))
        settings.log_card.hide()

    def test_changelog_row_emits_log_requested(self):
        seen = []
        self.window.settings.log_requested.connect(lambda: seen.append(True))
        self.window.settings.update_log.button.click()
        self.assertEqual(seen, [True])


if __name__ == "__main__":
    unittest.main()
