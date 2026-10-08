# SPDX-License-Identifier: GPL-3.0-or-later
import threading
import time
import uuid

from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
from gui.bridge import trace


class _RequestWatchdog:
    DEADLINES = {"status": 3.0, "configure": 3.0, "disconnect": 20.0, "shutdown": 25.0,
                 "connect": 100.0, "release_campus": 100.0, "ensure_started": 100.0}

    def __init__(self, request_id, method, started, grace=0.5, overrides=None, gap_limit=30.0):
        self.request_id, self.method, self.started = request_id, method, started
        self.threshold = (overrides or {}).get(method, self.DEADLINES.get(method, 10.0)) + grace
        self.gap_limit = gap_limit
        self._done, self._stop = threading.Event(), threading.Event()
        self._thread = threading.Thread(target=self._run, name="backend-request-watchdog", daemon=True)
        self._thread.start()

    def _run(self):
        last_poll = time.monotonic()
        deadline = last_poll + self.threshold
        while not self._done.is_set() and not self._stop.is_set():
            now = time.monotonic()
            delay = max(0.01, min(0.25, deadline - now))
            if self._done.wait(delay):
                return
            now = time.monotonic()
            poll_gap = now - last_poll
            last_poll = now
            if poll_gap > self.gap_limit:
                self.started += poll_gap
                deadline += poll_gap
                trace.emit("request_monitor_gap", request_id=self.request_id, method=self.method,
                           gap_kind="monitor_suspended")
                continue
            if now >= deadline:
                break
        if self._stop.is_set() or self._done.is_set():
            return
        now = time.monotonic()
        trace.emit("request_stalled", request_id=self.request_id, method=self.method,
                   duration_ms=int((now - self.started) * 1000), timeout_ms=int(self.threshold * 1000))
        while not self._done.wait(0.25):
            if self._stop.is_set():
                return
        elapsed = int((time.monotonic() - self.started) * 1000)
        trace.emit("request_recovered", request_id=self.request_id, method=self.method,
                   duration_ms=elapsed, recovery_ms=max(0, elapsed - int(self.threshold * 1000)))

    def finish(self):
        self._done.set()

    def close(self):
        self._stop.set()
        self._done.set()
        if self._thread is not threading.current_thread():
            self._thread.join(timeout=1)


class _Worker(QObject):
    completed = pyqtSignal(str, str, object)

    def __init__(self, backend):
        super().__init__()
        self.backend = backend

    @pyqtSlot(str, str, object, float, object)
    def execute(self, request_id, method, args, started, monitor):
        try:
            with trace.request_context(request_id):
                result = getattr(self.backend, method)(*args)
            outcome = "success" if isinstance(result, dict) and result.get("ok") else "error"
            error = result.get("error", "") if isinstance(result, dict) else ""
        except Exception as exc:
            result = {"ok": False, "error": "BackendRequestFailed"}
            outcome, error = "exception", "BackendRequestFailed"
            trace.safe_exception("worker_exception", type(exc), exc.__traceback__, request_id=request_id)
        duration = int((time.monotonic() - started) * 1000)
        monitor.finish()
        safe_error = trace.safe_error(error)
        if outcome != "success":
            trace.record_request_failure(request_id, method, duration, safe_error or "BackendError")
        else:
            trace.record_request_success(method)
        # Per-second status success is aggregated separately; keep failures and slow calls.
        if outcome == "success":
            if method != "status" or duration >= 3000:
                trace.emit("request_completed", request_id=request_id, method=method,
                       duration_ms=duration, timeout_ms=monitor.threshold * 1000, outcome=outcome,
                       error=safe_error)
            if method == "status":
                trace.emit("status_success")
        self.completed.emit(request_id, method, result)


class BackendWorker(QObject):
    request = pyqtSignal(str, str, object, float, object)
    completed = pyqtSignal(str, object)

    def __init__(self, backend, parent=None, request_deadlines=None, stall_grace=0.5):
        super().__init__(parent)
        self.busy = False
        self._request_started = 0.0
        self._request_deadlines, self._stall_grace = request_deadlines, stall_grace
        self._monitor = None
        self._request_id = ""
        self._closed = False
        self.thread = QThread(self)
        self.worker = _Worker(backend)
        self.worker.moveToThread(self.thread)
        self.thread.finished.connect(self.worker.deleteLater)
        self.request.connect(self.worker.execute)
        self.worker.completed.connect(self._done)
        self.thread.start()

    def submit(self, method, *args):
        if self.busy:
            return False
        self.busy = True
        self._request_started = time.monotonic()
        request_id = uuid.uuid4().hex
        self._request_id = request_id
        if method != "status":
            trace.emit("request_started", request_id=request_id, method=method)
        self._monitor = _RequestWatchdog(request_id, method, self._request_started,
                                         self._stall_grace, self._request_deadlines)
        self.request.emit(request_id, method, args, self._request_started, self._monitor)
        return True

    def _done(self, request_id, method, result):
        self.busy = False
        if method != "status":
            trace.emit("worker_idle", request_id=request_id, method=method,
                       busy_ms=int((time.monotonic() - self._request_started) * 1000))
        if self._monitor:
            self._monitor.close()
            self._monitor = None
        self.completed.emit(method, result)

    def close(self):
        if self._closed:
            return
        self._closed = True
        trace.emit("worker_close_started")
        if self._monitor:
            self._monitor.close()
            self._monitor = None
        self.thread.quit()
        if not self.thread.wait(8000):
            trace.emit("worker_close_timeout", busy_ms=int((time.monotonic() - self._request_started) * 1000) if self.busy else 0)
            self.thread.terminate()
            stopped = self.thread.wait(2000)
            trace.emit("worker_terminated", outcome="stopped" if stopped else "still_running")
        else:
            trace.emit("worker_closed", outcome="stopped")
