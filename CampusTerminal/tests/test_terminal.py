# SPDX-License-Identifier: GPL-3.0-or-later
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CAMPUS_TERMINAL_STATE"] = str(ROOT / "state/test-settings")
from PyQt5.QtCore import QRect, QRectF, QTimer, QSize, Qt, QPoint
from PyQt5.QtGui import QImage, QPainter
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import QApplication
from PyQt5.QtTest import QTest
from gui import theme as T
from gui.bridge import store
from gui.bridge.client import BackendClient
from gui.bridge.worker import BackendWorker
from gui.bridge.local_net import TrafficSampler
from gui.shell.window import MainWindow, settings_position
from gui.shell.tray import AppTray
from gui.shell.notifications import Notice

APP = QApplication.instance() or QApplication([])


class TerminalTests(unittest.TestCase):
    def test_windows_notification_adapter_and_click(self):
        tray = AppTray()
        shown = []
        tray.show_main.connect(lambda: shown.append(True))
        with patch.object(tray, "showMessage") as native:
            tray.notify(Notice("Test title", "Test body", "warning"))
            native.assert_called_once_with("Test title", "Test body", tray.Warning, 8000)
        tray.messageClicked.emit()
        self.assertEqual(shown, [True])
        shown.clear()
        with patch.object(tray, "showMessage"):
            tray.notify(Notice("Hint", "ok", "information", "remind"), raise_main=False, timeout_ms=2000)
        tray.messageClicked.emit()
        self.assertEqual(shown, [])

    def test_preview_lifecycle_has_no_backend_or_network_actions(self):
        result = subprocess.run([sys.executable, str(ROOT / "run.py"), "--preview", "--smoke"],
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))

    def test_geometry_and_screenshots(self):
        folder = ROOT / "state/qa" / ("dpi-" + os.environ.get("QT_SCALE_FACTOR", "1"))
        folder.mkdir(parents=True, exist_ok=True)
        for width, height in [(1920, 1040), (1366, 728), (1280, 672), (800, 552)]:
            screen = type("Screen", (), {"availableGeometry": lambda _: QRect(0, 0, width, height)})()
            window = MainWindow(T.window_scale(screen), T.load_design_font())
            window._available_geometry = screen.availableGeometry
            window.move(24, 24)
            window.settings.nic.set_adapters(["以太网:Realtek Gaming 2.5GbE Family Controller"], "")
            window.show()
            APP.processEvents()
            self.assertLessEqual(window.width(), width - T.SCREEN_MARGIN)
            self.assertLessEqual(window.height(), height - T.SCREEN_MARGIN)
            expected_w, expected_h = T.window_pixel_size(width, height)
            self.assertAlmostEqual(window.width() / expected_w, 1.0, delta=0.02)
            self.assertAlmostEqual(window.height() / expected_h, 1.0, delta=0.02)
            window.grab().save(str(folder / f"home-{width}.png"))
            window.show_settings()
            APP.processEvents()
            self.assertTrue(window.home.isVisible())
            self.assertTrue(window.settings.isWindow())
            self.assertGreater(window.settings.x(), window.frameGeometry().right())
            self.assertTrue(screen.availableGeometry().contains(window.settings.frameGeometry()))
            for block in [window.settings.nic, window.settings.types, window.settings.autos]:
                self.assertTrue(window.settings.rect().contains(block.geometry()))
            bounds = window.frameGeometry().united(window.settings.frameGeometry())
            ratio = window.devicePixelRatioF()
            combined = QImage(round(bounds.width() * ratio), round(bounds.height() * ratio), QImage.Format_ARGB32)
            combined.setDevicePixelRatio(ratio)
            combined.fill(0)
            painter = QPainter(combined)
            painter.drawPixmap(window.pos() - bounds.topLeft(), window.grab())
            painter.drawPixmap(window.settings.pos() - bounds.topLeft(), window.settings.grab())
            painter.end()
            combined.save(str(folder / f"settings-{width}.png"))
            window.show_home()
            window.home.recovery.set_state("error", [], "认证后台未连接，请检查管理员权限")
            window.grab().save(str(folder / f"error-{width}.png"))
            window.quit_app()
        renderer = QSvgRenderer(str(T.DESIGN_SVG))
        self.assertTrue(renderer.isValid())
        image = QImage(1024, 1024, QImage.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        renderer.render(painter, QRectF(0, 0, 1024, 1024))
        painter.end()
        image.save(str(folder / "reference.png"))

    def test_window_scale_follows_screen_share(self):
        large = T.window_pixel_size(1920, 1040)
        mid = T.window_pixel_size(1366, 728)
        small = T.window_pixel_size(800, 552)
        self.assertGreater(large[1], mid[1])
        self.assertGreater(mid[1], small[1])
        for width, height in [(1920, 1040), (1366, 728), (1280, 672), (800, 552)]:
            w, h = T.window_pixel_size(width, height)
            self.assertLessEqual(w, width - T.SCREEN_MARGIN)
            self.assertLessEqual(h, height - T.SCREEN_MARGIN)
            self.assertLessEqual(w / max(1, width - T.SCREEN_MARGIN), T.WIDTH_FRACTION + 1e-6)
            self.assertLessEqual(h / max(1, height - T.SCREEN_MARGIN), T.HEIGHT_FRACTION + 1e-6)
            self.assertAlmostEqual(w / h, T.WIN_W / T.WIN_H, places=3)
        self.assertLess(small[0], 480)

    def test_settings_panel_placement(self):
        panel = QSize(338, 443)
        area = QRect(0, 0, 1920, 1040)
        anchor = QRect(100, 100, 480, 713)
        position = settings_position(anchor, panel, area, 12)
        self.assertEqual(position.x(), 592)
        self.assertEqual(position.y() + panel.height(), anchor.bottom() + 1)
        edge = QRect(1440, 100, 480, 713)
        position = settings_position(edge, panel, area, 12)
        self.assertLess(position.x() + panel.width(), edge.left())
        for available, main in [(QRect(-1920, 0, 1920, 1040), QRect(-500, 20, 480, 713)),
                                (QRect(0, 0, 600, 800), QRect(100, 0, 480, 713))]:
            self.assertTrue(available.contains(QRect(settings_position(main, panel, available, 12), panel)))

    def test_settings_panel_lifecycle(self):
        window = MainWindow(480 / T.WIN_W, T.load_design_font())
        window._available_geometry = lambda: QRect(0, 0, 1920, 1040)
        window.move(100, 100)
        window.show()
        window.home.login.account.setText("local-ui-test")
        window.show_settings()
        APP.processEvents()
        self.assertTrue(window.home.isVisible())
        original = window.settings.pos()
        window.move(150, 130)
        APP.processEvents()
        self.assertEqual(window.settings.pos() - original, window.pos() - QPoint(100, 100))
        QTest.keyClick(window.settings, Qt.Key_Escape)
        self.assertFalse(window.settings.isVisible())
        self.assertTrue(window.home.isVisible())
        window.show_settings()
        QTest.mouseClick(window.settings.close_button, Qt.LeftButton)
        self.assertFalse(window.settings.isVisible())
        window.show_settings()
        window.show_settings()
        self.assertFalse(window.settings.isVisible())
        window.show_settings()
        window.hide()
        self.assertFalse(window.settings.isVisible())
        window.show()
        self.assertFalse(window.settings.isVisible())
        self.assertEqual(window.home.login.account.text(), "local-ui-test")
        window.show_settings()
        window.showMinimized()
        APP.processEvents()
        self.assertFalse(window.settings.isVisible())
        window.showNormal()
        window.show_settings()
        window.quit_app()
        self.assertFalse(window.settings.isVisible())

    def test_hidpi_geometry(self):
        for factor in ["1.25", "1.5"]:
            result = subprocess.run([sys.executable, __file__, "TerminalTests.test_geometry_and_screenshots"],
                                    env={**os.environ, "QT_SCALE_FACTOR": factor}, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))

    def test_backend_launch_readiness(self):
        client = BackendClient(ROOT)
        if client.status().get("ok"):
            self.skipTest("Existing user backend preserved")
        try:
            result = client.ensure_started()
            self.assertTrue(result.get("ok"), result)
            self.assertFalse(result["active"])
            self.assertEqual(client.ensure_started()["version"], "CampusTerminal-1.3.18")
        finally:
            self.assertTrue(client.shutdown().get("ok"))
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and client.status().get("ok"):
                time.sleep(.05)

    def test_unsupported_controls_and_real_empty_state(self):
        window = MainWindow(480 / T.WIN_W, T.load_design_font())
        window.settings.types.set_type("sso")
        for key, button in window.settings.types.buttons:
            self.assertEqual(button.isEnabled(), key == "normal")
            self.assertEqual(button.isChecked(), key == "normal")
        window.settings.autos.set_options({"seamless": True})
        self.assertFalse(window.settings.autos.toggles["seamless"].isChecked())
        self.assertFalse(store.DEFAULTS["inode_fallback"])
        self.assertFalse(window.settings.autos.toggles["inode_fallback"].isChecked())
        self.assertTrue(window.settings.autos.rect().contains(window.settings.autos.toggles["inode_fallback"].geometry()))
        self.assertEqual(window.home.recovery.events, [])
        self.assertEqual(window.home.speed.up, 0)
        window.quit_app()

    def test_settings_do_not_store_unsaved_account_or_password(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(store, "APP_DIR", Path(temp)), patch.object(store, "SETTINGS_PATH", Path(temp) / "settings.json"):
                store.save({"account": "test-account", "save_account": False, "password": "not-real",
                            "conn_type": "sso", "seamless": True, "adapter_id": "test-guid"})
                saved = store.load()
                self.assertEqual(saved["account"], "")
                self.assertNotIn("password", saved)
                self.assertEqual(saved["conn_type"], "normal")
                self.assertFalse(saved["seamless"])
                self.assertEqual(saved["adapter_id"], "test-guid")

    def test_missing_adapter_does_not_show_other_network(self):
        sampler = TrafficSampler()
        sampler.set_adapter("missing-test-adapter")
        with patch("gui.bridge.local_net.psutil.net_io_counters", return_value={"proxy": object()}):
            self.assertEqual(sampler.tick(), (0, 0, []))

    def test_worker_does_not_block_event_loop(self):
        class Slow:
            def status(self):
                time.sleep(.2)
                return {"ok": True}
        worker = BackendWorker(Slow())
        results, ticks = [], []
        worker.completed.connect(lambda *args: results.append(args))
        timer = QTimer()
        timer.setInterval(10)
        timer.timeout.connect(lambda: ticks.append(1))
        timer.start()
        try:
            self.assertTrue(worker.submit("status"))
            self.assertFalse(worker.submit("status"))
            deadline = time.monotonic() + 3
            while not results and time.monotonic() < deadline:
                APP.processEvents()
                time.sleep(.005)
            self.assertTrue(results)
            self.assertGreater(len(ticks), 5)
        finally:
            timer.stop()
            worker.close()

    def test_actual_backend_status_configure_shutdown_without_authentication(self):
        client = BackendClient(ROOT)
        existing = client.status()
        if existing.get("ok"):
            self.skipTest("Existing user backend preserved")
        process = subprocess.Popen([str(client.exe), "gui-host"], creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                status = client.status()
                if status.get("ok"):
                    break
                time.sleep(.05)
            self.assertTrue(status.get("ok"), status)
            self.assertEqual(status["version"], "CampusTerminal-1.3.18")
            self.assertFalse(status["options"]["inodeFallback"])
            self.assertFalse(status["active"])
            for enabled in [False, True, False]:
                result = client.configure({"autoReconnect": enabled})
                self.assertTrue(result["ok"], result)
                self.assertEqual(result["options"]["autoReconnect"], enabled)
            result = client._talk_py({"id": 7, "method": "connect", "options": {"connectionType": "sso"}})
            self.assertEqual(result["error"], "UnsupportedConnectionType")
            for enabled in [True, False]:
                result = client.configure({"inodeFallback": enabled})
                self.assertEqual(result["options"]["inodeFallback"], enabled)
            for _ in range(20):
                self.assertTrue(client.status().get("ok"))
            self.assertTrue(client.disconnect()["ok"])
        finally:
            reply = client.shutdown()
            self.assertTrue(reply.get("ok"), reply)
            process.wait(timeout=10)
        self.assertEqual(process.returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
