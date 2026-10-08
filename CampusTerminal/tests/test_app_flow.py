# SPDX-License-Identifier: GPL-3.0-or-later
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["CAMPUS_TERMINAL_STATE"] = str(ROOT / "state/test-settings")


def run_scenario(scenario):
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QApplication
    from gui import app as gui

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
    def test_shutdown_modes_use_real_gui_event_loop(self):
        for scenario in ("disabled", "success", "failure"):
            with self.subTest(scenario=scenario):
                result = subprocess.run([sys.executable, __file__, "--scenario", scenario], capture_output=True, timeout=12)
                self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))


if __name__ == "__main__":
    if "--scenario" in sys.argv:
        run_scenario(sys.argv[-1])
    else:
        unittest.main(verbosity=2)
