# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression replay for the 1.4.2 resume-identity incident.

The GUI reports adapter ids in uppercase while the core status returns the same
UUID in lowercase. These scenarios use the real Qt event loop with a fake core
that keeps the auth failure at 5, keeps iNode resident, and only accepts a
takeover when the resume request actually carries resumeOwnedSession=true.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ADAPTER_LOW = "325b38cc-bfd3-4628-beac-acbc8f520ed4"
ADAPTER_HIGH = ADAPTER_LOW.upper()
ADAPTER_B_LOW = "9c2f7a41-8d6e-4c52-91c1-2a4d0e6f7b88"
NIC_A = {"id": ADAPTER_HIGH, "name": "test-a", "label": "tab-a", "up": True}
NIC_B = {"id": ADAPTER_B_LOW.upper(), "name": "test-b", "label": "tab-b", "up": True}


def _read_events(root):
    path = Path(root) / "gui-events.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return [json.loads(line) for line in lines if line.strip()]


def run_mode(mode):
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QApplication
    from gui import app as gui
    from gui.bridge import auto_policy

    original_sys, original_thread = sys.excepthook, __import__("threading").excepthook
    attempts = []
    state = {"status_calls": 0, "online": True, "restored": False, "rejections": 0,
             "periodic": 0, "right_cleared": False, "manual": False,
             "adapter_changed": False, "auto_off": False, "marker": 0}

    class Backend:
        def __init__(self, _root):
            pass

        def status(self):
            state["status_calls"] += 1
            if state["status_calls"] > 2 and not state["restored"]:
                state["online"] = False
            right = not state["right_cleared"]
            base = {"ok": True, "processId": 51, "generation": 1,
                    "resumeOwnedSession": right,
                    "resumeAdapter": ADAPTER_LOW if right else ""}
            if state["online"]:
                return {**base, "active": True, "phase": "online", "firstError": None,
                        "recovery": {"events": [], "enabled": not state["auto_off"],
                                     "autoFailures": 0, "exhausted": False}}
            return {**base, "active": False, "phase": "error",
                    "firstError": "AuthenticationRejected",
                    "recovery": {"events": [], "enabled": not state["auto_off"],
                                 "autoFailures": 5, "exhausted": True}}

        def connect(self, _user, _password, _adapter, options):
            attempts.append(dict(options))
            if not options.get("silentRetry"):
                return {"ok": True, "active": True, "phase": "online"}
            state["periodic"] += 1
            if mode == "restart":
                QTimer.singleShot(120, QApplication.instance().quit)
                return {"ok": True, "active": False, "phase": "connecting"}
            if mode == "takeover":
                if state["periodic"] >= 3 and options.get("resumeOwnedSession"):
                    state["restored"], state["online"] = True, True
                    QTimer.singleShot(250, QApplication.instance().quit)
                    return {"ok": True, "active": True, "phase": "online"}
                state["rejections"] += 1
                return {"ok": False, "error": "OriginalClientRunning"}
            if mode == "rejected":
                state["rejections"] += 1
                if state["rejections"] >= 30:
                    QTimer.singleShot(150, QApplication.instance().quit)
                return {"ok": False, "error": "OriginalClientRunning"}
            state["rejections"] += 1
            if len(attempts) > state["marker"]:
                QTimer.singleShot(150, QApplication.instance().quit)
            return {"ok": False, "error": "OriginalClientRunning"}

        def configure(self, options):
            adapter = options.get("adapterId") or ""
            if mode == "adapter" and adapter and adapter.lower() == NIC_B["id"].lower():
                state["adapter_changed"] = True
                state["right_cleared"] = True
                return {"ok": True, "options": options, "phase": "idle",
                        "resumeOwnedSession": False, "resumeAdapter": ""}
            if mode == "autooff" and options.get("autoReconnect") is False:
                state["auto_off"] = True
                state["right_cleared"] = True
                return {"ok": True, "options": options, "phase": "idle",
                        "resumeOwnedSession": False, "resumeAdapter": "",
                        "recovery": {"enabled": False}}
            return {"ok": True, "options": options, "phase": "idle",
                    "resumeOwnedSession": not state["right_cleared"],
                    "resumeAdapter": ADAPTER_LOW if not state["right_cleared"] else ""}

        def disconnect(self):
            state["manual"] = True
            state["right_cleared"] = True
            if mode == "manual":
                QTimer.singleShot(700, QApplication.instance().quit)
            return {"ok": True, "phase": "idle"}

        def release_campus(self, _adapter):
            return {"ok": True}

        def shutdown(self, *_args):
            return {"ok": True, "active": False, "phase": "idle"}

    original_interval = QTimer.setInterval

    def quick_interval(timer, interval):
        return original_interval(timer, 20 if interval == 1000 else interval)

    data = {**gui.store.DEFAULTS, "account": "synthetic-account", "save_account": True,
            "save_password": True, "auto_connect": True, "auto_start": False,
            "auto_reconnect": True}
    nic_list = [NIC_A, NIC_B] if mode in ("adapter", "autooff") else [NIC_A]
    real_window = gui.MainWindow

    def window_factory(*args):
        window = real_window(*args)
        if mode == "manual":
            def stop():
                state["marker"] = len(attempts)
                window.home.disconnect_requested.emit()
            QTimer.singleShot(220, stop)
            QTimer.singleShot(2500, QApplication.instance().quit)
        elif mode == "adapter":
            def switch():
                state["marker"] = len(attempts)
                window.settings.nic.combo.setCurrentText(NIC_B["label"])
            QTimer.singleShot(220, switch)
            QTimer.singleShot(4000, QApplication.instance().quit)
        elif mode == "autooff":
            def disable():
                state["marker"] = len(attempts)
                window.settings.autos.toggles["auto_reconnect"].setChecked(False)
            QTimer.singleShot(220, disable)
            QTimer.singleShot(4000, QApplication.instance().quit)
        else:
            QTimer.singleShot(12000, QApplication.instance().quit)
        return window

    with tempfile.TemporaryDirectory() as temp, \
            patch.object(sys, "argv", [__file__, "--silent"]), \
            patch.object(gui, "BackendClient", Backend), \
            patch.object(gui, "MainWindow", window_factory), \
            patch.object(gui, "SingleInstance", return_value=SimpleNamespace(acquire=lambda: True)), \
            patch.object(gui, "list_adapters", return_value=nic_list), \
            patch.object(gui.store, "APP_DIR", Path(temp)), \
            patch.object(gui.store, "load", return_value=data), \
            patch.object(gui.store, "load_password", return_value="synthetic-password"), \
            patch.object(gui.store, "save"), patch.object(gui.store, "clear_password"), \
            patch.object(gui.store, "startup_enabled", return_value=False), \
            patch.object(gui.QSystemTrayIcon, "isSystemTrayAvailable", return_value=False), \
            patch.object(gui, "alternative_path", return_value=False), \
            patch.object(gui, "original_running", return_value=False), \
            patch.object(gui, "SILENT_RETRY_SECONDS", 1), \
            patch.object(auto_policy, "SILENT_RETRY_SECONDS", 1), \
            patch.object(QTimer, "setInterval", quick_interval):
        assert gui.main() == 0
        events = _read_events(Path(temp))

    periodic = [options for options in attempts if options.get("silentRetry")]
    decisions = [row for row in events if row.get("stage") == "resume_decision"]
    rejected_rows = [row for row in events if row.get("stage") == "resume_rejected"]
    assert sys.excepthook is original_sys
    assert __import__("threading").excepthook is original_thread

    if mode == "restart":
        assert periodic and all(o.get("resumeOwnedSession") is True for o in periodic), attempts
        assert decisions and all(row.get("same_adapter") is True and row.get("reason") == "ok"
                                 for row in decisions), decisions
        assert max(row.get("failures", 0) for row in decisions) <= 5, decisions
    elif mode == "takeover":
        assert state["restored"] and state["online"], state
        assert periodic and all(o.get("resumeOwnedSession") is True for o in periodic), attempts
        assert decisions and all(row.get("same_adapter") is True and row.get("reason") == "ok"
                                 for row in decisions), decisions
        assert max(row.get("failures", 0) for row in decisions) <= 5, decisions
        assert any(row.get("phase") == "online" for row in events if row.get("stage") == "status_phase"), events
        cleared = [row for row in events if row.get("stage") == "auto_retry_cleared"]
        assert cleared and all(row.get("count") == 0 for row in cleared), cleared
    elif mode == "rejected":
        assert state["rejections"] >= 30, state
        assert periodic and all(o.get("resumeOwnedSession") is True for o in periodic), attempts
        assert decisions and all(row.get("failures") == 5 for row in decisions), decisions
        assert len(rejected_rows) >= 30, rejected_rows
    elif mode == "manual":
        assert state["manual"], state
        after = [o for o in attempts[state["marker"]:] if o.get("silentRetry")]
        assert not after, after
    elif mode == "adapter":
        assert state["adapter_changed"], state
        after = [o for o in attempts[state["marker"]:] if o.get("silentRetry")]
        assert after and all(o.get("resumeOwnedSession") is False for o in after), after
    elif mode == "autooff":
        assert state["auto_off"], state
        after = [o for o in attempts[state["marker"]:] if o.get("silentRetry")]
        assert after and all(o.get("resumeOwnedSession") is False for o in after), after
    else:
        raise AssertionError("unknown mode " + mode)


class ResumeIdentityTests(unittest.TestCase):
    def test_old_uppercase_adapter_id_selects_the_lowercase_adapter(self):
        from gui import app as gui
        adapters = [NIC_A]
        chosen = gui._choose_adapter(adapters, {"adapter_id": ADAPTER_HIGH})
        self.assertIs(chosen, adapters[0])
        chosen = gui._choose_adapter([{"id": ADAPTER_LOW, "label": "tab-a", "up": True}],
                                     {"adapter_id": ADAPTER_HIGH})
        self.assertIsNotNone(chosen)

    def test_takeover_from_lowercase_core_and_uppercase_gui_reaches_online(self):
        result = subprocess.run([sys.executable, __file__, "takeover"], capture_output=True, timeout=25)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))

    def test_thirty_rejected_resume_requests_do_not_inflate_failure_count(self):
        result = subprocess.run([sys.executable, __file__, "rejected"], capture_output=True, timeout=25)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))

    def test_restart_with_core_held_right_continues_slow_recovery(self):
        result = subprocess.run([sys.executable, __file__, "restart"], capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))

    def test_manual_disconnect_adapter_switch_and_auto_off_suppress_resume(self):
        for mode in ("manual", "adapter", "autooff"):
            with self.subTest(mode=mode):
                result = subprocess.run([sys.executable, __file__, mode], capture_output=True, timeout=25)
                self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] in {"restart", "takeover", "rejected", "manual", "adapter", "autooff"}:
        run_mode(sys.argv[1])
    else:
        unittest.main(verbosity=2)
