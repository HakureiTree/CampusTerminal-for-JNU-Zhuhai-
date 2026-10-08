import json
import os
import shutil
import threading
import unittest
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from gui.bridge import trace


class LoggingTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).parent / (".logging-test-state-" + uuid.uuid4().hex)
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir()
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))
        self.appdir = patch("gui.bridge.store.APP_DIR", self.root)
        self.appdir.start()
        self.addCleanup(self.appdir.stop)
        trace._failed = False

    def test_rotation_unique_and_retention(self):
        expected = set()
        with patch.object(trace, "MAX_BYTES", 200):
            for index in range(12):
                expected.add(index)
                trace.emit("sample", outcome="ok", reason=str(index))
        segments = list(self.root.glob("gui-events-*.jsonl"))
        self.assertGreaterEqual(len(segments), 3)
        self.assertEqual(len(segments), len({p.name for p in segments}))
        rows = [json.loads(line) for path in [*segments, self.root / "gui-events.jsonl"]
                if path.exists() for line in path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual({int(row["reason"]) for row in rows}, expected)
        cutoff = datetime.now(timezone.utc).date() - timedelta(days=trace.RETENTION_DAYS - 1)
        old = self.root / f"gui-events-{(cutoff - timedelta(days=1)):%Y%m%d}-0001.jsonl"
        boundary = self.root / f"gui-events-{cutoff:%Y%m%d}-0001.jsonl"
        old.write_text("{}\n", encoding="utf-8")
        boundary.write_text("{}\n", encoding="utf-8")
        with patch.object(trace, "MAX_BYTES", 200):
            trace.emit("sample")
        self.assertFalse(old.exists())
        self.assertTrue(boundary.exists())

    def test_redaction_and_exception_frames(self):
        try:
            raise RuntimeError("password=secret@example.com payload")
        except RuntimeError as exc:
            trace.safe_exception("worker_exception", type(exc), exc.__traceback__)
        trace.emit("request_completed", method="connect", password="secret", payload={"x": "y"})
        text = "\n".join(p.read_text(encoding="utf-8") for p in self.root.glob("*.jsonl"))
        self.assertNotIn("secret", text)
        self.assertNotIn("payload", text)
        row = json.loads(text.splitlines()[0])
        self.assertEqual(row["frames"][0]["function"], "test_redaction_and_exception_frames")

    def test_known_error_codes_retained_and_unknown_messages_redacted(self):
        self.assertEqual(trace.safe_error("AuthenticationRejected"), "AuthenticationRejected")
        self.assertEqual(trace.safe_error("RuntimeLogUnavailable"), "RuntimeLogUnavailable")
        self.assertEqual(trace.safe_error("password=synthetic-secret"), "BackendError")
        trace.emit("request_completed", error=trace.safe_error("AuthenticationRejected"), method="connect")
        row = json.loads((self.root / "gui-events.jsonl").read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(row["error"], "AuthenticationRejected")
        self.assertNotIn("duration_ms", row)

    def test_write_failure_has_separate_marker_and_keeps_running(self):
        marker = self.root / "gui-events.write-status.json"
        original_open = Path.open
        def fail_log(path, *args, **kwargs):
            if path.name == "gui-events.jsonl":
                raise OSError("secret path detail")
            return original_open(path, *args, **kwargs)
        with patch.object(Path, "open", fail_log):
            trace.emit("test")
        self.assertTrue(trace._failed)
        self.assertTrue(marker.exists())
        self.assertEqual(json.loads(marker.read_text(encoding="utf-8")), {"status": "LOGWRITEFAIL"})
        with patch.object(Path, "open", original_open):
            trace.emit("after_recovery")
        self.assertFalse(marker.exists())
        text = "\n".join(p.read_text(encoding="utf-8") for p in self.root.glob("*.jsonl"))
        self.assertIn("log_write_recovered", text)
        self.assertFalse(trace._failed)

    def test_session_markers_detect_unclean_and_clear_clean_stop(self):
        marker = self.root / "gui-session.json"
        marker.write_text('{"prior":"run"}', encoding="utf-8")
        trace.begin_session()
        self.assertTrue(marker.exists())
        trace.end_session()
        self.assertFalse(marker.exists())
        stages = [json.loads(line)["stage"] for path in self.root.glob("*.jsonl")
                  for line in path.read_text(encoding="utf-8").splitlines()]
        self.assertIn("gui_unclean_previous_session", stages)
        self.assertIn("gui_stop", stages)

    def test_worker_records_timeout_and_safe_exception_stack(self):
        from gui.bridge.worker import _Worker
        class Backend:
            def status(self):
                return {"ok": False, "error": "BackendTimeout", "detail": "secret payload"}
            def connect(self, *_args):
                raise RuntimeError("password=do-not-log")
        worker = _Worker(Backend())
        completed = []
        worker.completed.connect(lambda *args: completed.append(args))
        class Monitor:
            threshold = 3.5
            def finish(self): pass
        worker.execute("req-1", "status", (), time.monotonic(), Monitor())
        worker.execute("req-2", "connect", ("synthetic-account-SECRET", "synthetic-password-SECRET"), time.monotonic(), Monitor())
        text = "\n".join(p.read_text(encoding="utf-8") for p in self.root.glob("*.jsonl"))
        self.assertIn("BackendTimeout", text)
        self.assertIn('"frames"', text)
        for secret in ("secret payload", "do-not-log", "synthetic-account-SECRET", "synthetic-password-SECRET"):
            self.assertNotIn(secret, text)
        self.assertEqual(len(completed), 2)

    def test_independent_gui_watchdog_detects_and_recovers(self):
        watchdog = trace.MainLoopWatchdog(threshold=0.05, poll=0.01, gap_limit=1.0)
        self.addCleanup(watchdog.close)
        time.sleep(0.12)
        watchdog.pulse()
        text = "\n".join(p.read_text(encoding="utf-8") for p in self.root.glob("*.jsonl"))
        self.assertIn("gui_unresponsive", text)
        self.assertIn("gui_resumed", text)

    def test_watchdog_monitor_poll_gap_resets_pulse_without_false_hang(self):
        watchdog = trace.MainLoopWatchdog(threshold=0.2, poll=0.005, gap_limit=0.05)
        self.addCleanup(watchdog.close)
        time.sleep(0.01)
        watchdog._last_poll = time.monotonic() - 1
        time.sleep(0.03)
        watchdog.pulse()
        text = "\n".join(p.read_text(encoding="utf-8") for p in self.root.glob("*.jsonl"))
        self.assertIn("gui_monitor_gap", text)
        self.assertNotIn("gui_unresponsive", text)

    def test_offscreen_qt_main_loop_block_is_logged_before_recovery(self):
        from PyQt5.QtCore import QTimer
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        watchdog = trace.MainLoopWatchdog(threshold=0.06, poll=0.005, gap_limit=1.0)
        def block_main_loop():
            time.sleep(0.16)
            app.processEvents()
            watchdog.pulse()
            app.quit()
        QTimer.singleShot(0, block_main_loop)
        app.exec_()
        watchdog.close()
        lines = [line for path in self.root.glob("*.jsonl") for line in path.read_text(encoding="utf-8").splitlines()]
        stages = [json.loads(line)["stage"] for line in lines]
        self.assertLess(stages.index("gui_unresponsive"), stages.index("gui_resumed"))
        self.assertIn("gui_unresponsive", stages)

    def test_worker_timeout_termination_and_watchdog_stop_have_no_late_writes(self):
        from unittest.mock import Mock
        from gui.bridge.worker import BackendWorker
        class Backend:
            def status(self):
                return {"ok": True}
        worker = BackendWorker(Backend())
        worker.thread.quit()
        worker.thread.wait(1000)
        fake_thread = Mock()
        fake_thread.wait.return_value = False
        worker.thread = fake_thread
        watchdog = trace.MainLoopWatchdog(threshold=0.04, poll=0.005, gap_limit=1.0)
        time.sleep(0.08)
        worker.close()
        watchdog.close()
        before = [p.read_text(encoding="utf-8") for p in self.root.glob("*.jsonl")]
        time.sleep(0.05)
        after = [p.read_text(encoding="utf-8") for p in self.root.glob("*.jsonl")]
        self.assertEqual(before, after)
        text = "\n".join(before)
        self.assertIn("worker_close_timeout", text)
        self.assertIn('"stage": "worker_terminated"', text)
        self.assertTrue(fake_thread.terminate.called)

    def test_worker_stall_detected_while_gui_event_loop_remains_live(self):
        from PyQt5.QtCore import QTimer
        from PyQt5.QtWidgets import QApplication
        from gui.bridge.worker import BackendWorker
        app = QApplication.instance() or QApplication([])
        entered, release = threading.Event(), threading.Event()
        class Backend:
            def status(self):
                entered.set()
                release.wait(2)
                return {"ok": True}
        worker = BackendWorker(Backend(), request_deadlines={"status": 0.05}, stall_grace=0.01)
        worker.submit("status")
        self.assertTrue(entered.wait(1))
        ticks = []
        timer = QTimer()
        timer.setInterval(5)
        timer.timeout.connect(lambda: ticks.append(1))
        timer.start()
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            app.processEvents()
            if any('"stage": "request_stalled"' in path.read_text(encoding="utf-8")
                   for path in self.root.glob("*.jsonl")):
                break
            time.sleep(0.005)
        stalled_before_release = any('"stage": "request_stalled"' in path.read_text(encoding="utf-8")
                                     for path in self.root.glob("*.jsonl"))
        self.assertTrue(stalled_before_release)
        self.assertGreater(len(ticks), 2)
        release.set()
        deadline = time.monotonic() + 1
        while worker.busy and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.005)
        worker.close()
        timer.stop()
        text = "\n".join(path.read_text(encoding="utf-8") for path in self.root.glob("*.jsonl"))
        self.assertIn("request_recovered", text)
        self.assertIn('"request_id": "', text)
        self.assertNotIn("secret", text)

    def test_concurrent_journal_sequences_match_serialized_order(self):
        from concurrent.futures import ThreadPoolExecutor
        def write(index):
            for item in range(20):
                trace.emit("parallel", reason=f"{index}:{item}")
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(write, range(8)))
        rows = [json.loads(line) for path in self.root.glob("*.jsonl")
                for line in path.read_text(encoding="utf-8").splitlines()]
        sequences = [row["sequence"] for row in rows]
        self.assertEqual(sequences, sorted(sequences))
        self.assertEqual(len(sequences), len(set(sequences)))

    def test_path_context_schemas_keep_only_bounded_network_fields(self):
        trace.emit("path_census", other=True, rows=[{"id": "nic-a", "description": "x" * 300,
            "name": "Ethernet", "mac": "aa:bb", "ipv4": "10.0.0.2", "gateway": "10.0.0.1",
            "up": 1, "campus": False, "alternative": True, "secret": "credential"}])
        trace.emit("connect_submit", silent=True, adapter="nic-a", takeover=False, up=True,
                   username="account", password="secret", payload={"bad": True})
        trace.emit("auto_armed", adapter="nic-a", has_password=True, auto_due=True, adapter_up=True,
                   username="account")
        rows = [json.loads(line) for path in self.root.glob("*.jsonl")
                for line in path.read_text(encoding="utf-8").splitlines()]
        path_row, connect_row, armed_row = rows
        self.assertEqual(set(path_row["rows"][0]), {"id", "description", "name", "mac", "ipv4", "gateway", "up", "campus", "alternative"})
        self.assertEqual(len(path_row["rows"][0]["description"]), 128)
        self.assertEqual(connect_row["silent"], True)
        self.assertNotIn("password", connect_row)
        self.assertEqual(armed_row["has_password"], True)

    def test_backend_ipc_receives_only_thread_local_diagnostic_id_header(self):
        import json as json_module
        from gui.bridge.client import BackendClient
        class FakeSocket:
            written = b""
            def connectToServer(self, _pipe): pass
            def waitForConnected(self, _ms): return True
            def write(self, payload): self.written = payload; return len(payload)
            def bytesToWrite(self): return 0
            def canReadLine(self): return True
            def readLine(self): return b'{"id":1,"ok":true}\n'
            def abort(self): pass
        socket = FakeSocket()
        with patch("gui.bridge.client.QLocalSocket", return_value=socket):
            with trace.request_context("0123456789abcdef0123456789abcdef"):
                result = BackendClient.__new__(BackendClient)._talk_py({"id": 1, "method": "status"})
        self.assertTrue(result["ok"])
        sent = json_module.loads(socket.written.decode("utf-8"))
        self.assertEqual(sent["diagnosticRequestId"], "0123456789abcdef0123456789abcdef")
        self.assertEqual(set(sent), {"id", "method", "diagnosticRequestId"})

    def test_repeated_failures_aggregate_and_recovery_preserves_counts(self):
        for idx in range(4):
            trace.record_request_failure(f"req-{idx}", "configure", 20, "BackendProtocolError")
        trace.record_request_success("configure")
        rows = [json.loads(line) for path in self.root.glob("*.jsonl")
                for line in path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(sum(row["stage"] == "request_failure" for row in rows), 1)
        recovery = next(row for row in rows if row["stage"] == "request_failure_recovered")
        self.assertEqual(recovery["count"], 4)
        self.assertEqual(recovery["error"], "BackendProtocolError")

    def test_recovery_widget_keeps_three_visible_rows_from_full_history(self):
        from PyQt5.QtWidgets import QApplication
        from gui.home.recovery_card import RecoveryCard
        app = QApplication.instance() or QApplication([])
        card = RecoveryCard(1.0, "Arial")
        history = [(str(index), "12:00", str(index)) for index in range(100)]
        card.set_state("ok", history)
        self.assertEqual(len(history), 100)
        self.assertEqual(card.events, history[-3:])


if __name__ == "__main__":
    unittest.main()
