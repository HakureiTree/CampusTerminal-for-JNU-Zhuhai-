# SPDX-License-Identifier: GPL-3.0-or-later
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["CAMPUS_TERMINAL_STATE"] = str(ROOT / "state" / ("test-settings-" + uuid.uuid4().hex))


def run_scenario(scenario):
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QApplication
    from gui import app as gui
    original_sys_hook, original_thread_hook = sys.excepthook, __import__("threading").excepthook

    events, warnings, windows = [], [], []
    writes, teardown_checks = [], []
    enabled = scenario != "disabled"

    class Backend:
        pending = False
        finished = False

        def __init__(self, _root):
            pass

        def ensure_started(self):
            return self.status()

        def status(self):
            if self.pending:
                self.finished = True
                phase = "fallback_failed" if scenario == "failure" else "fallback_active"
                return {"ok": True, "active": False, "phase": phase}
            return {"ok": True, "active": False, "phase": "idle"}

        def configure(self, options):
            events.append(("configure", options))
            return {**self.status(), "options": options}

        def shutdown(self, handoff=False, adapter=""):
            events.append(("shutdown", handoff, adapter))
            if not handoff:
                return {"ok": True, "active": False, "phase": "idle"}
            if not self.pending:
                self.pending = True
                return {"ok": True, "active": True, "pending": True, "phase": "fallback"}
            assert self.finished, "GUI must poll status before repeating shutdown"
            if scenario == "failure":
                return {"ok": False, "error": "HandoffFailed"}
            return {"ok": True, "active": False, "pending": False, "phase": "fallback_active"}

    actual_window = gui.MainWindow

    def window_factory(*args):
        window = actual_window(*args)
        windows.append(window)
        def choose_and_exit():
            def check_teardown():
                before = len(writes)
                window.home.login.account.editingFinished.emit()
                window.home.login.password.editingFinished.emit()
                teardown_checks.append(len(writes) == before)
            # Register after main() installed its shutdown guard.
            QApplication.instance().aboutToQuit.connect(check_teardown)
            if enabled:
                window.settings.option_changed.emit("inode_fallback", True)
            QTimer.singleShot(100, window.exit_requested.emit)
        QTimer.singleShot(100, choose_and_exit)
        def watchdog():
            if scenario != "failure":
                warnings.append("Unexpected watchdog exit")
            QApplication.instance().quit()
        QTimer.singleShot(3500, watchdog)
        return window

    data = {**gui.store.DEFAULTS, "auto_connect": False, "auto_start": False}
    nic = {"id": "test-adapter", "name": "test", "label": "test", "up": True}
    with patch.object(gui, "MainWindow", window_factory), patch.object(gui, "BackendClient", Backend), \
            patch.object(gui, "SingleInstance", return_value=SimpleNamespace(acquire=lambda: True)), \
            patch.object(gui, "list_adapters", return_value=[nic]), \
            patch.object(gui.store, "load", return_value=data), \
            patch.object(gui.store, "save", side_effect=lambda value: writes.append(dict(value))), \
            patch.object(gui.store, "clear_password"), patch.object(gui.store, "startup_enabled", return_value=False), \
            patch.object(gui.QSystemTrayIcon, "isSystemTrayAvailable", return_value=False), \
            patch.object(gui.QMessageBox, "warning", side_effect=lambda *args: warnings.append(args[-1])):
        assert gui.main() == 0
    assert sys.excepthook is original_sys_hook
    assert __import__("threading").excepthook is original_thread_hook
    assert teardown_checks == [True], "Late focus-loss signals must not persist after shutdown"
    shutdowns = [e for e in events if e[0] == "shutdown"]
    assert len(shutdowns) == (2 if enabled else 1), events
    assert all(e[1] == enabled for e in shutdowns), events
    if enabled:
        assert all(e[2] == "test-adapter" for e in shutdowns), events
        assert any(e[0] == "configure" and e[1]["inodeFallback"] for e in events), events
    if scenario == "failure":
        assert windows[0].notice.isVisible() and not windows[0]._force_close, "Failed handoff must keep GUI open with in-app notice"
    else:
        assert windows[0]._force_close, warnings


class AppFlowTests(unittest.TestCase):
    def test_main_wrapper_restores_hooks_after_startup_exception_without_message_leak(self):
        from gui import app as gui
        original_sys, original_thread = sys.excepthook, __import__("threading").excepthook
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(gui.store, "APP_DIR", Path(directory)), \
                patch.object(gui, "_main_impl", side_effect=RuntimeError("synthetic-password-secret")):
            self.assertEqual(gui.main(), 1)
            text = "\n".join(p.read_text(encoding="utf-8") for p in Path(directory).glob("gui-events*.jsonl"))
        self.assertIs(sys.excepthook, original_sys)
        self.assertIs(__import__("threading").excepthook, original_thread)
        self.assertIn("gui_startup_exception", text)
        self.assertIn("RuntimeError", text)
        self.assertNotIn("synthetic-password-secret", text)

    def test_address_refresh_once_per_connection_in_real_gui_event_loop(self):
        result = subprocess.run([sys.executable, __file__, "--address-refresh"], capture_output=True, timeout=12)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))

    def test_shutdown_modes_use_real_gui_event_loop(self):
        for scenario in ("disabled", "success", "failure"):
            with self.subTest(scenario=scenario):
                result = subprocess.run([sys.executable, __file__, "--scenario", scenario], capture_output=True, timeout=12)
                self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))

    def test_automatic_reconnect_campaign_metadata_is_sent_per_worker_attempt(self):
        result = subprocess.run([sys.executable, __file__, "--campaign"], capture_output=True, timeout=12)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))


def run_address_refresh_scenario():
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QApplication
    from gui import app as gui

    windows, observations = [], []
    actual_window = gui.MainWindow
    reader = SimpleNamespace(calls=0)

    def read_address(_nic):
        reader.calls += 1
        return [f"10.10.1.{reader.calls}"]

    def window_factory(*args):
        window = actual_window(*args)
        windows.append(window)

        def feed_status():
            backend = window.findChild(gui.BackendWorker)
            for phase, generation in [("connecting", 0), ("verifying", 0), ("online", 0),
                                      ("online", 0), ("degraded", 0), ("online", 0),
                                      ("recovering", 1), ("online", 1), ("online", 1)]:
                backend.completed.emit("status", {"ok": True, "active": True, "phase": phase,
                                                  "processId": 123, "generation": generation,
                                                  "recovery": {"events": [{"result": "成功"}]}})
            observations.append((reader.calls, window.settings.ip.value.text()))

        def finish():
            observations.append((reader.calls, window.settings.ip.value.text()))
            QApplication.instance().quit()

        QTimer.singleShot(100, feed_status)
        QTimer.singleShot(1300, finish)
        return window

    nic = {"id": "test-adapter", "name": "test", "label": "test", "up": True}
    with patch.object(sys, "argv", [__file__, "--preview"]), \
            patch.object(gui, "MainWindow", window_factory), \
            patch.object(gui, "list_adapters", return_value=[nic]), \
            patch.object(gui, "adapter_ipv4", side_effect=read_address), \
            patch.object(gui, "alternative_path", return_value=False), \
            patch.object(gui, "original_present", return_value=False):
        assert gui.main() == 0
    assert observations == [(3, "10.10.1.3"), (3, "10.10.1.3")], observations


def run_campaign_scenario():
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QApplication
    from gui import app as gui

    original_sys, original_thread = sys.excepthook, __import__("threading").excepthook
    attempts = []
    class Backend:
        connects = 0
        def __init__(self, _root): pass
        def status(self):
            return {"ok": True, "active": self.connects >= 3,
                    "phase": "online" if self.connects >= 3 else "idle",
                    "processId": 44, "generation": 1, "recovery": {"events": []}}
        def connect(self, _user, _password, _adapter, options):
            attempts.append(dict(options))
            self.connects += 1
            if self.connects < 3:
                return {"ok": True, "active": False, "phase": "error", "firstError": "AuthenticationRejected",
                        "recovery": {"events": []}}
            return {"ok": True, "active": True, "phase": "online", "recovery": {"events": []}}
        def shutdown(self, *_args): return {"ok": True, "active": False, "phase": "idle"}
        def configure(self, options): return {"ok": True, "options": options, "phase": "idle"}
        def disconnect(self): return {"ok": True, "phase": "idle"}
        def release_campus(self, _adapter): return {"ok": True}

    original_interval = QTimer.setInterval
    def quick_interval(timer, interval):
        return original_interval(timer, 20 if interval == 1000 else interval)
    data = {**gui.store.DEFAULTS, "account": "synthetic-account", "save_account": True,
            "save_password": True, "auto_connect": True, "auto_start": False}
    nic = {"id": "campaign-adapter", "name": "test", "label": "test", "up": True}
    real_window = gui.MainWindow
    def campaign_window(*args):
        window = real_window(*args)
        QTimer.singleShot(4500, QApplication.instance().quit)
        return window
    with patch.object(gui, "BackendClient", Backend), \
            patch.object(gui, "MainWindow", campaign_window), \
            patch.object(gui, "SingleInstance", return_value=SimpleNamespace(acquire=lambda: True)), \
            patch.object(gui, "list_adapters", return_value=[nic]), \
            patch.object(gui.store, "load", return_value=data), \
            patch.object(gui.store, "load_password", return_value="synthetic-password"), \
            patch.object(gui.store, "save"), patch.object(gui.store, "clear_password"), \
            patch.object(gui.store, "startup_enabled", return_value=False), \
            patch.object(gui.QSystemTrayIcon, "isSystemTrayAvailable", return_value=False), \
            patch.object(gui, "alternative_path", return_value=False), \
            patch.object(gui, "original_present", return_value=False), \
            patch.object(QTimer, "setInterval", quick_interval):
        assert gui.main() == 0
    assert len(attempts) >= 3, attempts
    assert "autoReconnectCampaign" not in attempts[0]
    later = attempts[1:]
    assert all(row.get("autoReconnectCampaign") is True for row in later), attempts
    campaign_ids = {row.get("campaignId") for row in later}
    assert len(campaign_ids) == 1 and next(iter(campaign_ids)), attempts
    assert sys.excepthook is original_sys
    assert __import__("threading").excepthook is original_thread


if __name__ == "__main__":
    if "--address-refresh" in sys.argv:
        run_address_refresh_scenario()
    elif "--scenario" in sys.argv:
        run_scenario(sys.argv[-1])
    elif "--campaign" in sys.argv:
        run_campaign_scenario()
    else:
        unittest.main(verbosity=2)
