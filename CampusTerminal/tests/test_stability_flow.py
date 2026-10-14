# SPDX-License-Identifier: GPL-3.0-or-later
"""Keep the 1.3.20 stability fixes covered in the real Qt event loop."""
from contextlib import ExitStack
import os
from pathlib import Path
import subprocess
import sys
import tempfile
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

    calls, rendered, exceptions, observations = [], [], [], {}
    history = [{"at": "10.15", "time": f"08:0{index}", "result": "成功"} for index in range(5)]
    data = {**gui.store.DEFAULTS, "account": "fixture-user", "save_password": True,
            "auto_start": False, "auto_update": False, "auto_connect": case == "already_connected"}
    nic = {"id": "fixture-nic", "name": "fixture", "label": "fixture", "up": True}

    class Backend:
        def __init__(self, _root):
            self.connected = case == "history"

        def status(self):
            calls.append("status")
            return {"ok": True, "active": self.connected,
                    "phase": "online" if self.connected else "idle",
                    "recovery": {"events": history}}

        def ensure_started(self):
            return self.status()

        def connect(self, *_args):
            calls.append("connect")
            self.connected = True
            return {"ok": False, "error": "AlreadyConnected"}

        def configure(self, *_args):
            return self.status()

        def shutdown(self, *_args):
            self.connected = False
            return self.status()

    real_window = gui.MainWindow
    def window_factory(*args):
        window = real_window(*args)
        card = window.home.recovery
        set_state = card.set_state
        def observe_state(state, rows, detail=None):
            rendered.append(state)
            set_state(state, rows, detail)
        card.set_state = observe_state

        def feed_history():
            worker = window.findChild(gui.BackendWorker)
            for _ in range(30):
                worker.completed.emit("status", {"ok": True, "active": True, "phase": "online",
                                                  "recovery": {"events": history}})
        if case == "history":
            QTimer.singleShot(100, feed_history)

        def finish():
            observations.update(state=card.state, events=list(card.events))
            QApplication.instance().quit()
        QTimer.singleShot(2200, finish)
        return window

    with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
        for target, name, value in [
            (gui, "MainWindow", window_factory), (gui, "BackendClient", Backend),
            (gui, "SingleInstance", lambda *_a: SimpleNamespace(acquire=lambda: True)),
            (gui, "list_adapters", lambda: [nic]), (gui, "alternative_path", lambda *_a: False),
            (gui, "original_present", lambda: False), (gui, "fetch_offer", lambda *_a: None),
            (gui, "consume_result", lambda: None), (gui, "install_root", lambda: Path(temp)),
            (gui, "adapter_ipv4", lambda *_a: []),
            (gui.store, "APP_DIR", Path(temp)), (gui.store, "load", lambda: data),
            (gui.store, "load_password", lambda: "fixture-password"),
            (gui.store, "save", lambda *_a: None), (gui.store, "clear_password", lambda: None),
            (gui.store, "startup_enabled", lambda: False),
            (gui.store, "sync_silent_startup", lambda *_a: None),
            (gui.QSystemTrayIcon, "isSystemTrayAvailable", lambda: False),
            (gui.trace, "safe_exception", lambda stage, *_a, **_kw: exceptions.append(stage)),
        ]:
            stack.enter_context(patch.object(target, name, value))
        stack.enter_context(patch.object(sys, "argv", [__file__, "--silent"]))
        assert gui.main() == 0
    assert not exceptions, exceptions
    assert observations["state"] == "ok" and "error" not in rendered, (observations, rendered, calls)
    expected = [(item["at"], item["time"], item["result"]) for item in history[-3:]]
    assert observations["events"] == expected, observations
    if case == "history":
        assert len(rendered) >= 30 and "connect" not in calls, calls
    else:
        assert calls.count("connect") == 1 and "status" in calls[calls.index("connect") + 1:], calls


class StabilityFlowTests(unittest.TestCase):
    def test_repeated_status_with_recovery_history_preserves_dictionary(self):
        result = subprocess.run([sys.executable, __file__, "history"], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))

    def test_silent_attach_to_connected_backend_has_no_error_transition(self):
        result = subprocess.run([sys.executable, __file__, "already_connected"], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] in {"history", "already_connected"}:
        run_case(sys.argv[1])
    else:
        unittest.main()
