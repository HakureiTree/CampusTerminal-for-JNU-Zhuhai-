# SPDX-License-Identifier: GPL-3.0-or-later
import os
import socket
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtWidgets import QApplication
import psutil
from gui import theme as T
from gui.bridge.local_net import ConnectionAddressRefresh, adapter_ipv4
from gui.shell.window import MainWindow

APP = QApplication.instance() or QApplication([])


def address(family, value):
    return SimpleNamespace(family=family, address=value)


class AddressTests(unittest.TestCase):
    def setUp(self):
        self.adapter = {"name": "Ethernet", "mac": "AABBCCDDEEFF"}
        self.addresses = {
            "Ethernet": [address(psutil.AF_LINK, "AA-BB-CC-DD-EE-FF"),
                         address(socket.AF_INET, "10.10.1.2")],
            "VPN": [address(psutil.AF_LINK, "00-11-22-33-44-55"),
                    address(socket.AF_INET, "192.168.1.2")],
        }
        self.addr_patch = patch("gui.bridge.local_net.psutil.net_if_addrs", return_value=self.addresses)
        self.stats_patch = patch("gui.bridge.local_net.psutil.net_if_stats", return_value={
            "Ethernet": SimpleNamespace(isup=True), "VPN": SimpleNamespace(isup=True)})
        self.addr_patch.start()
        self.stats_mock = self.stats_patch.start()
        self.addCleanup(self.addr_patch.stop)
        self.addCleanup(self.stats_patch.stop)

    def test_selected_adapter_and_changed_lease(self):
        self.assertEqual(adapter_ipv4(self.adapter), ["10.10.1.2"])
        self.addresses["Ethernet"][1].address = "10.10.5.6"
        self.assertEqual(adapter_ipv4(self.adapter), ["10.10.5.6"])
        self.assertEqual(adapter_ipv4({"name": "VPN", "mac": "001122334455"}), ["192.168.1.2"])

    def test_renamed_adapter_uses_identity_and_never_other_route(self):
        self.adapter["name"] = "old name"
        self.assertEqual(adapter_ipv4(self.adapter), ["10.10.1.2"])
        del self.addresses["Ethernet"]
        self.assertEqual(adapter_ipv4(self.adapter), [])
        self.assertEqual(adapter_ipv4(None), [])

    def test_disconnected_and_unassigned(self):
        self.stats_mock.return_value["Ethernet"].isup = False
        self.assertEqual(adapter_ipv4(self.adapter), [])
        self.stats_mock.return_value["Ethernet"].isup = True
        self.addresses["Ethernet"] = self.addresses["Ethernet"][:1]
        self.assertEqual(adapter_ipv4(self.adapter), [])

    def test_invalid_link_local_ipv6_and_duplicates(self):
        self.addresses["Ethernet"] += [address(socket.AF_INET, value) for value in
                                      ("0.0.0.0", "127.0.0.1", "169.254.2.3", "224.0.0.1", "10.999.1.2", "10.10.1.2")]
        self.addresses["Ethernet"].append(address(socket.AF_INET6, "::1"))
        self.assertEqual(adapter_ipv4(self.adapter), ["10.10.1.2"])


class ConnectionRefreshTests(unittest.TestCase):
    def test_verified_connection_only_and_no_refresh_for_status_polls(self):
        tracker = ConnectionAddressRefresh()
        identity = ("nic", 123, 0)
        for phase in ("idle", "connecting", "verifying"):
            self.assertFalse(tracker.observe(phase, identity))
        self.assertTrue(tracker.observe("online", identity))
        for _ in range(10):
            self.assertFalse(tracker.observe("online", identity))
        self.assertFalse(tracker.observe("degraded", identity))
        self.assertFalse(tracker.observe("online", identity))

    def test_reconnect_generation_and_backend_restart(self):
        tracker = ConnectionAddressRefresh()
        self.assertTrue(tracker.observe("online", ("nic", 123, 0)))
        self.assertTrue(tracker.observe("online", ("nic", 123, 1)))
        self.assertFalse(tracker.observe("online", ("nic", 123, 1)))
        self.assertTrue(tracker.observe("online", ("nic", 456, 0)))
        self.assertFalse(tracker.observe("recovering", ("nic", 456, 1)))
        self.assertTrue(tracker.observe("online", ("nic", 456, 1)))

    def test_disconnect_and_official_client_reconnect(self):
        tracker = ConnectionAddressRefresh()
        identity = ("nic", 123, 0)
        self.assertTrue(tracker.observe("online", identity))
        self.assertFalse(tracker.observe("idle", identity))
        self.assertTrue(tracker.observe("online", identity))
        self.assertFalse(tracker.observe("fallback", identity))
        self.assertTrue(tracker.observe("fallback_active", identity))
        self.assertFalse(tracker.observe("fallback_active", identity))


class ResizeTests(unittest.TestCase):
    def setUp(self):
        self.window = MainWindow(480 / T.WIN_W, T.load_design_font())
        self.window.show()
        APP.processEvents()
        self.addCleanup(self.window.quit_app)

    def test_scale_preserves_state_and_returns_to_original_geometry(self):
        window = self.window
        window.home.login.account.setText("test-user")
        window.home.login.password.setText("test-password")
        window.home.speed.set_rates(12, 34, [1, 2, 3])
        rect = window.home.login.account.geometry()
        initial = window.size()
        for factor in (1.5, .8, 2, 1):
            window.resize(round(initial.width() * factor), round(initial.height() * factor))
            APP.processEvents()
            self.assertEqual(window.home.login.account.text(), "test-user")
            self.assertEqual(window.home.login.password.text(), "test-password")
            self.assertEqual(window.home.speed.samples, [1, 2, 3])
            for child in (window.home.login, window.home.speed, window.home.recovery, window.home.advert):
                self.assertTrue(window.home.rect().contains(child.geometry()))
        self.assertEqual(window.home.login.account.geometry(), rect)

    def test_non_proportional_resize_and_settings_address_card(self):
        window = self.window
        window.show_settings()
        settings = window.settings
        settings.ip.set_address("10.10.5.6")
        settings.autos.toggles["auto_connect"].setChecked(False)
        window.resize(900, 800)
        settings.resize(600, 700)
        APP.processEvents()
        blocks = (settings.nic, settings.ip, settings.types, settings.autos)
        for child in blocks:
            self.assertTrue(settings.content.rect().contains(child.geometry()))
        for above, below in zip(blocks, blocks[1:]):
            self.assertLess(above.geometry().bottom(), below.geometry().top())
        self.assertEqual(settings.ip.value.text(), "10.10.5.6")
        self.assertFalse(settings.autos.toggles["auto_connect"].isChecked())
        self.assertTrue(settings.ip.value.textInteractionFlags() & Qt.TextSelectableByMouse)
        self.assertTrue(window.rect().contains(window.close_btn.geometry()))
        self.assertTrue(settings.rect().contains(settings.close_button.geometry()))

    def test_native_resize_dispatches_each_edge(self):
        for window in (self.window, self.window.settings):
            window.show()
            APP.processEvents()
            for grip in window.resize_grips:
                with patch.object(type(window.windowHandle()), "startSystemResize", return_value=True) as native:
                    event = QMouseEvent(QEvent.MouseButtonPress, QPointF(2, 2), QPointF(200, 200),
                                        Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
                    grip.mousePressEvent(event)
                    native.assert_called_once_with(grip.edges)
                    self.assertIsNone(grip._start)

    def test_fallback_resize_all_edges_keeps_opposite_edge_and_minimum(self):
        window = self.window
        for grip in window.resize_grips:
            window.setGeometry(100, 100, 480, 713)
            APP.processEvents()
            initial = window.geometry()
            with patch.object(type(window.windowHandle()), "startSystemResize", return_value=False):
                grip.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, QPointF(2, 2), QPointF(200, 200),
                                                Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
            dx = -60 if grip.edges & Qt.LeftEdge else 60 if grip.edges & Qt.RightEdge else 0
            dy = -70 if grip.edges & Qt.TopEdge else 70 if grip.edges & Qt.BottomEdge else 0
            grip.mouseMoveEvent(QMouseEvent(QEvent.MouseMove, QPointF(2, 2), QPointF(200 + dx, 200 + dy),
                                           Qt.NoButton, Qt.LeftButton, Qt.NoModifier))
            APP.processEvents()
            self.assertEqual(window.width(), initial.width() + abs(dx))
            self.assertEqual(window.height(), initial.height() + abs(dy))
            if grip.edges & Qt.LeftEdge:
                self.assertEqual(window.geometry().right(), initial.right())
            if grip.edges & Qt.TopEdge:
                self.assertEqual(window.geometry().bottom(), initial.bottom())
            grip.mouseMoveEvent(QMouseEvent(QEvent.MouseMove, QPointF(2, 2),
                                           QPointF(200 - dx * 100, 200 - dy * 100),
                                           Qt.NoButton, Qt.LeftButton, Qt.NoModifier))
            self.assertGreaterEqual(window.width(), window.minimumWidth())
            self.assertGreaterEqual(window.height(), window.minimumHeight())
            grip.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease, QPointF(2, 2),
                                              Qt.LeftButton, Qt.NoButton, Qt.NoModifier))


if __name__ == "__main__":
    unittest.main()
