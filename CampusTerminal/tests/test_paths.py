# SPDX-License-Identifier: GPL-3.0-or-later
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gui.bridge import paths
from gui.bridge.messages import MESSAGES, error_text

ROOT = Path(__file__).resolve().parents[1]


class PathTests(unittest.TestCase):
    def setUp(self):
        self.temp = ROOT / "state" / "test-paths"
        if self.temp.exists():
            shutil.rmtree(self.temp)
        self.temp.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.temp, ignore_errors=True)

    def test_unfrozen_install_root_is_project(self):
        self.assertFalse(paths.frozen())
        self.assertEqual(paths.install_root(), ROOT)

    def test_portable_core_next_to_root_wins(self):
        fake = self.temp / "CampusTerminal.Core.exe"
        fake.write_bytes(b"MZ")
        self.assertEqual(paths.core_exe(self.temp).resolve(), fake.resolve())
        self.assertTrue(paths.diagnose(self.temp)["core_exists"])

    def test_nested_release_core_is_discovered(self):
        nested = self.temp / "core/bin/Release/net10.0-windows/CampusTerminal.Core.exe"
        nested.parent.mkdir(parents=True)
        nested.write_bytes(b"MZ")
        self.assertEqual(paths.core_exe(self.temp).resolve(), nested.resolve())

    def test_backend_missing_is_for_classmates_not_developers(self):
        text = error_text("BackendMissing")
        self.assertNotIn("Start-Test.ps1", text)
        self.assertNotIn("Start-Test.ps1", MESSAGES["BackendMissing"])
        self.assertIn("完整压缩包", text)


class OriginalProcessTests(unittest.TestCase):
    def test_gui_running_matches_inode_client_process_name(self):
        from gui.bridge import original

        class Proc:
            def __init__(self, name):
                self.info = {"name": name}
        with patch("gui.bridge.original.psutil.process_iter", return_value=[Proc("iNode Client.exe")]):
            self.assertTrue(original.gui_running())
        with patch("gui.bridge.original.psutil.process_iter", return_value=[Proc("notepad.exe")]):
            self.assertFalse(original.gui_running())


class AlternativePathTests(unittest.TestCase):
    def test_phone_tether_names_count_and_wifi_does_not(self):
        from gui.bridge.local_net import looks_alternative
        self.assertTrue(looks_alternative("Remote NDIS based Internet Sharing Device", "以太网 2"))
        self.assertTrue(looks_alternative("Apple Mobile Device Ethernet", "以太网 3"))
        self.assertFalse(looks_alternative("Intel Wi-Fi 6 AX201", "Wi-Fi"))
        self.assertFalse(looks_alternative("Hyper-V Virtual Ethernet Adapter", "vEthernet"))
        self.assertFalse(looks_alternative("Realtek Gaming 2.5GbE Family Controller", "以太网"))

    def test_phone_tether_is_not_a_campus_port_but_usb_dongle_is(self):
        from gui.bridge.local_net import is_phone_tether
        self.assertTrue(is_phone_tether("Remote NDIS based Internet Sharing Device", "以太网 2"))
        self.assertTrue(is_phone_tether("Apple Mobile Device Ethernet", "以太网 3"))
        self.assertFalse(is_phone_tether("Realtek USB GbE Family Controller", "以太网"))
        self.assertTrue(is_phone_tether("USB Ethernet/RNDIS Gadget", "以太网 5"))
        self.assertTrue(is_phone_tether("远程 NDIS 兼容设备", "以太网 7"))
        self.assertFalse(is_phone_tether("Intel Wi-Fi 6 AX201", "WLAN"))


if __name__ == "__main__":
    unittest.main()
