# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise update decisions through the real Qt event loop with isolated services."""
from contextlib import ExitStack
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def run_case(case):
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QApplication
    from gui import app as gui

    calls, observations = [], {}
    offer = {"version": "9.9.9", "notes": "- fixture update", "assets": []}
    data = {**gui.store.DEFAULTS, "account": "fixture-user", "save_password": True,
            "auto_connect": True, "auto_start": False, "auto_update": case != "manual",
            "auto_check_update": case == "manual",
            "ignored_version": "9.9.9" if case == "ignored" else ""}
    nic = {"id": "fixture-nic", "name": "fixture", "label": "fixture", "up": True}

    class Backend:
        def __init__(self, _root):
            self.connected = False

        def status(self):
            calls.append("status")
            return {"ok": True, "active": self.connected,
                    "phase": "online" if self.connected else "idle", "recovery": {"events": []}}

        def connect(self, *_args):
            calls.append("connect")
            self.connected = True
            return self.status()

        def configure(self, _options):
            return self.status()

        def shutdown(self, *_args):
            calls.append("shutdown")
            self.connected = False
            return self.status()

        def disconnect(self):
            self.connected = False
            return self.status()

    def fetch(_agent):
        time.sleep(0.08)
        calls.append("checked")
        return offer

    def prepare(*_args):
        calls.append("prepare")
        if case == "failed":
            raise ValueError("fixture download failure")
        return {"script": "fixture-script", "transaction": "fixture-transaction"}

    def spawn(*_args):
        calls.append("spawn")

    real_window = gui.MainWindow
    def window_factory(*args):
        window = real_window(*args)
        def inspect():
            observations["offer_visible"] = window.update_chip.isVisible()
            if case == "manual":
                window.update_chip.clicked.emit()
                observations["notes_visible"] = "fixture update" in window.update_choice.body.text()
                window.update_choice.cancel_btn.click()
            QApplication.instance().quit()
        QTimer.singleShot(1400, inspect)
        return window

    with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
        for target, name, value in [
            (gui, "MainWindow", window_factory), (gui, "BackendClient", Backend),
            (gui, "SingleInstance", lambda *_a: SimpleNamespace(acquire=lambda: True)),
            (gui, "list_adapters", lambda: [nic]), (gui, "alternative_path", lambda *_a: False),
            (gui, "original_present", lambda: False), (gui, "frozen", lambda: True),
            (gui, "install_root", lambda: Path(temp)), (gui, "fetch_offer", fetch),
            (gui, "prepare_transaction", prepare), (gui, "spawn_apply", spawn),
            (gui, "consume_result", lambda: None),
            (gui.store, "APP_DIR", Path(temp)), (gui.store, "load", lambda: data),
            (gui.store, "load_password", lambda: "fixture-password"),
            (gui.store, "save", lambda *_a: None), (gui.store, "clear_password", lambda: None),
            (gui.store, "startup_enabled", lambda: False),
            (gui.store, "sync_silent_startup", lambda *_a: None),
            (gui.QSystemTrayIcon, "isSystemTrayAvailable", lambda: False),
        ]:
            stack.enter_context(patch.object(target, name, value))
        assert gui.main() == 0, calls
    if case == "success":
        assert calls.count("prepare") == calls.count("spawn") == calls.count("shutdown") == 1, calls
        assert "connect" not in calls, calls
        assert calls.index("checked") < calls.index("prepare") < calls.index("spawn") < calls.index("shutdown"), calls
    elif case == "failed":
        assert calls.count("prepare") == 1 and "spawn" not in calls and "shutdown" not in calls, calls
        assert calls.count("connect") == 1 and calls.index("prepare") < calls.index("connect"), calls
    elif case == "ignored":
        assert "prepare" not in calls and "spawn" not in calls and not observations["offer_visible"], calls
        assert calls.count("connect") == 1 and calls.index("checked") < calls.index("connect"), calls
    elif case == "manual":
        assert observations["offer_visible"] and observations["notes_visible"], observations
        assert "prepare" not in calls and "spawn" not in calls, calls


class UpdateFlowTests(unittest.TestCase):
    def test_automatic_update_success_failure_and_ignored_version(self):
        for case in ("success", "failed", "ignored"):
            with self.subTest(case=case):
                result = subprocess.run([sys.executable, __file__, case], capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))

    def test_manual_offer_does_not_apply_without_selection(self):
        result = subprocess.run([sys.executable, __file__, "manual"], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] in {"success", "failed", "ignored", "manual"}:
        run_case(sys.argv[1])
    else:
        unittest.main()
