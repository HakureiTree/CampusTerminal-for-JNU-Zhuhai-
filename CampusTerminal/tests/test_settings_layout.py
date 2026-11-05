# SPDX-License-Identifier: GPL-3.0-or-later
"""P3 settings legibility: minimum font pixels, metric rows and vector checkbox."""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtCore import QPoint, QRect, Qt
from PyQt5.QtGui import QFontMetrics
from PyQt5.QtWidgets import QApplication
from PyQt5.QtTest import QTest
from gui import theme
from gui.shell.window import MainWindow

APP = QApplication.instance() or QApplication([])
SIZES = ((300, 560), (350, 750), (600, 700))


class SettingsLayoutTests(unittest.TestCase):
    def setUp(self):
        self.window = MainWindow(.2, theme.pick_font_family())
        self.window.show()
        APP.processEvents()
        self.window.show_settings()
        APP.processEvents()
        self.addCleanup(self.window.quit_app)

    def settings_at(self, width, height):
        settings = self.window.settings
        settings.resize(width, height)
        APP.processEvents()
        return settings

    def test_minimum_fonts_and_metric_button_heights(self):
        for width, height in SIZES:
            settings = self.settings_at(width, height)
            autos = settings.autos
            self.assertGreaterEqual(autos.body_font.pixelSize(), 14, (width, height))
            self.assertGreaterEqual(autos.title_font.pixelSize(), 15, (width, height))
            for block in (settings.updates, settings.update_log):
                self.assertGreaterEqual(block.title.font().pixelSize(), 15, (width, height))
                self.assertGreaterEqual(block.button.font().pixelSize(), 13, (width, height))
                metrics = QFontMetrics(block.button.font())
                self.assertGreaterEqual(block.button.height(), metrics.height())
                self.assertGreaterEqual(block.button.height(), block.button.fontMetrics().height())

    def test_rows_wrap_without_clipping_and_stay_inside_block(self):
        for width, height in SIZES:
            settings = self.settings_at(width, height)
            autos = settings.autos
            metrics = QFontMetrics(autos.body_font)
            self.assertEqual([row[0] for row in autos.rows], [spec[3] for spec in theme.SET_AUTOS])
            for key, label, row_rect, text_rect, visual_rect in autos.rows:
                bounds = metrics.boundingRect(
                    QRect(0, 0, text_rect.width(), 10000), int(Qt.TextWordWrap), label)
                self.assertLessEqual(bounds.width(), text_rect.width(), key)
                self.assertLessEqual(bounds.height(), text_rect.height(), key)
                self.assertEqual(row_rect.x(), 0)
                self.assertEqual(row_rect.width(), autos.width())
                self.assertLessEqual(row_rect.bottom(), autos.height() - 1, key)
                self.assertGreaterEqual(visual_rect.width(), 14, key)
                self.assertLessEqual(visual_rect.width(), 32, key)
                self.assertLessEqual(visual_rect.height(), 32, key)
                self.assertTrue(autos.rect().contains(visual_rect), key)
                toggle = autos.toggles[key]
                self.assertEqual(toggle.geometry(), row_rect, key)
                local_visual = visual_rect.translated(-row_rect.x(), -row_rect.y())
                self.assertEqual(toggle.visual_rect(), local_visual, key)
                self.assertGreaterEqual(toggle.width(), .8 * autos.width(), key)
                self.assertLess(visual_rect.width(), toggle.width(), key)
                centre_delta = visual_rect.center().y() - row_rect.center().y()
                self.assertLessEqual(abs(centre_delta), 1, key)

    def test_toggle_hit_area_is_full_row_and_visual_is_compact(self):
        settings = self.settings_at(300, 560)
        autos = settings.autos
        toggle = autos.toggles["silent_start"]
        self.assertFalse(toggle.isChecked())
        hit = QPoint(toggle.width() - 3, toggle.height() // 2)
        QTest.mouseClick(toggle, Qt.LeftButton, pos=hit)
        APP.processEvents()
        self.assertTrue(toggle.isChecked())
        visual = toggle.visual_rect()
        self.assertLessEqual(visual.width(), 32)
        self.assertLessEqual(visual.width(), toggle.width() // 2)
        self.assertFalse(autos.toggles["seamless"].isEnabled())

    def test_blocks_stay_ordered_and_contained_inside_content(self):
        for width, height in SIZES:
            settings = self.settings_at(width, height)
            blocks = (settings.nic, settings.ip, settings.types, settings.updates,
                      settings.update_log, settings.autos)
            for above, below in zip(blocks, blocks[1:]):
                self.assertLess(above.geometry().bottom(), below.geometry().top(), (width, height))
            for block in blocks:
                self.assertTrue(settings.content.rect().contains(block.geometry()),
                                (width, height, type(block).__name__))
            self.assertLessEqual(settings.autos.geometry().bottom(), settings.content.height() - 1)

    def test_short_page_scrolls_and_title_tracks_content(self):
        settings = self.settings_at(300, 560)
        bar = settings.scroll.verticalScrollBar()
        self.assertGreater(bar.maximum(), 0)
        self.assertGreater(settings.content.height(), settings.scroll.viewport().height())
        origin = settings.content.mapTo(settings, QPoint(0, 0))
        self.assertGreaterEqual(origin.y(), -1)
        bar.setValue(bar.maximum())
        APP.processEvents()
        self.assertLess(settings.content.mapTo(settings, QPoint(0, 0)).y(), 0)
        self.assertFalse(settings.grab().isNull())


if __name__ == "__main__":
    unittest.main()
