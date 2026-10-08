# SPDX-License-Identifier: GPL-3.0-or-later
"""Safe, bounded GUI event journal."""
import json
import os
import re
import sys
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from gui.bridge.messages import MESSAGES

SAFE_BACKEND_ERRORS = frozenset(key for key in MESSAGES if key.isascii() and key.isalnum()) | {
    "BackendProtocolError", "BackendRequestFailed", "BackendError", "HeartbeatLogUnavailable", "RecoveryLogUnavailable"
}


def safe_error(error):
    return error if isinstance(error, str) and error in SAFE_BACKEND_ERRORS else ("BackendError" if error else "")

MAX_BYTES = 8 * 1024 * 1024
RETENTION_DAYS = 31
_lock = threading.RLock()
_failed = False
_run_id = uuid.uuid4().hex
_sequence = 0
_context = threading.local()
_active_run = False
_last_successful_status = 0.0
_healthy_status_count = 0
_request_failures = {}


def request_context(request_id):
    class Context:
        def __enter__(self):
            self.previous = getattr(_context, "request_id", None)
            _context.request_id = request_id
            return self
        def __exit__(self, *_args):
            if self.previous is None:
                _context.__dict__.pop("request_id", None)
            else:
                _context.request_id = self.previous
    return Context()


def current_request_id():
    return getattr(_context, "request_id", None)


def _directory():
    from gui.bridge.store import APP_DIR
    return Path(APP_DIR)


def _fallback(reason):
    """Write a fixed, non-sensitive marker once, then use stderr if possible."""
    global _failed
    with _lock:
        if _failed:
            return
        _failed = True
        try:
            root = _directory()
            root.mkdir(parents=True, exist_ok=True)
            temp = root / "gui-events.write-status.tmp"
            temp.write_text('{"status":"LOGWRITEFAIL"}\n', encoding="utf-8")
            temp.replace(root / "gui-events.write-status.json")
        except Exception:
            try:
                sys.stderr.write("CampusTerminal diagnostic log unavailable\n")
            except Exception:
                pass


def _segments(root):
    return sorted(root.glob("gui-events-*.jsonl"), key=lambda p: p.name)


def _rotate(path, root):
    if not path.exists() or path.stat().st_size < MAX_BYTES:
        return path
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    index = 1
    while True:
        target = root / f"gui-events-{day}-{index:04d}.jsonl"
        if not target.exists():
            os.replace(path, target)
            break
        index += 1
    return path


def _prune(root):
    cutoff = datetime.now(timezone.utc).date().toordinal() - (RETENTION_DAYS - 1)
    for path in _segments(root):
        try:
            day = datetime.strptime(path.name.split("-")[2], "%Y%m%d").date()
            if day.toordinal() < cutoff:
                path.unlink()
        except (ValueError, OSError, IndexError):
            continue


def emit(stage, **detail):
    """Persist only fields allowed by the selected event schema."""
    global _sequence, _failed, _last_successful_status, _healthy_status_count
    schemas = {
        "path_census": {"other", "rows"},
        "connect_submit": {"silent", "adapter", "takeover", "up"},
        "auto_armed": {"adapter", "has_password", "auto_due", "adapter_up"},
        "request_started": {"request_id", "method"},
        "request_completed": {"request_id", "method", "duration_ms", "timeout_ms", "outcome", "error"},
        "request_stalled": {"request_id", "method", "duration_ms", "timeout_ms"},
        "request_recovered": {"request_id", "method", "duration_ms", "recovery_ms"},
        "request_failure": {"request_id", "method", "duration_ms", "outcome", "error", "count", "first_at", "last_at", "recovery_ms"},
        "request_failure_recovered": {"method", "error", "count", "first_at", "last_at", "recovery_ms"},
        "worker_idle": {"request_id", "method", "busy_ms"},
        "backend_error": {"request_id", "method", "error"},
        "auto_retry_wait": {"count", "duration_ms", "campaign_id", "outcome", "reason"},
        "auto_retry_cap_reached": {"count", "campaign_id"},
        "status_healthy_summary": {"count"},
        "status_phase": {"phase", "active"},
    }
    common = {"request_id", "method", "duration_ms", "timeout_ms", "outcome", "error", "error_type",
              "filename", "function", "line", "busy_ms", "count", "first_at", "last_at", "recovery_ms",
              "reason", "campaign_id", "active", "threshold_ms", "gap_kind", "run_id", "pid", "sequence"}
    allowed = schemas.get(stage, common)
    row = {}
    safe_methods = {"status", "connect", "disconnect", "shutdown", "configure", "ensure_started", "release_campus"}
    safe_errors = SAFE_BACKEND_ERRORS
    safe_phases = {"idle", "connecting", "verifying", "online", "degraded", "recovering", "disconnecting",
                   "fallback", "fallback_active", "fallback_failed", "error"}
    for key in allowed:
        if key not in detail:
            continue
        value = detail.get(key)
        if isinstance(value, (int, float, bool, type(None))):
            row[key] = max(0, min(value, 2_147_483_647)) if key in {"duration_ms", "timeout_ms", "busy_ms", "recovery_ms", "count", "line"} and isinstance(value, (int, float)) else value
        elif isinstance(value, str):
            if key == "method" and value not in safe_methods:
                continue
            if key == "error" and value not in safe_errors:
                continue
            if key == "phase" and value not in safe_phases:
                continue
            if key in {"request_id", "campaign_id"} and not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", value):
                continue
            if key == "reason" and not re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", value):
                continue
            row[key] = value[:128]
    if stage == "path_census" and isinstance(detail.get("rows"), list):
        fields = ("id", "description", "name", "mac", "ipv4", "gateway", "up", "campus", "alternative")
        rows = []
        for item in detail["rows"][:32]:
            if isinstance(item, dict):
                clean = {}
                for key in fields:
                    if key not in item or not isinstance(item[key], (str, int, float, bool)):
                        continue
                    if key in {"up", "campus", "alternative"}:
                        value = item[key]
                        if isinstance(value, bool):
                            clean[key] = value
                        elif isinstance(value, int) and value in (0, 1):
                            clean[key] = bool(value)
                        elif str(value).lower() in {"true", "false"}:
                            clean[key] = str(value).lower() == "true"
                        continue
                    clean[key] = "".join(c for c in str(item[key]) if c.isprintable())[:128]
                rows.append(clean)
        row["rows"] = rows
    if isinstance(detail.get("frames"), list):
        row["frames"] = [{"filename": Path(str(frame.get("filename", ""))).name[:128],
                           "function": str(frame.get("function", ""))[:128],
                           "line": int(frame.get("line", 0))}
                          for frame in detail["frames"] if isinstance(frame, dict)]
    try:
        with _lock:
            root = _directory()
            root.mkdir(parents=True, exist_ok=True)
            path = root / "gui-events.jsonl"
            _rotate(path, root)
            if stage == "status_success":
                now = time.monotonic()
                _healthy_status_count += 1
                if now - _last_successful_status < 60:
                    return
                row.update(count=_healthy_status_count)
                _healthy_status_count = 0
                _last_successful_status = now
                stage = "status_healthy_summary"
            _sequence += 1
            row.update(at=datetime.now(timezone.utc).isoformat(), stage=str(stage)[:64],
                       pid=os.getpid(), run_id=_run_id, sequence=_sequence)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            _prune(root)
            marker = root / "gui-events.write-status.json"
            if _failed or marker.exists():
                marker.unlink(missing_ok=True)
                (root / "gui-events.write-status.tmp").unlink(missing_ok=True)
                _failed = False
                _sequence += 1
                recovery = {"at": datetime.now(timezone.utc).isoformat(), "stage": "log_write_recovered",
                            "pid": os.getpid(), "run_id": _run_id, "sequence": _sequence}
                with path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(recovery) + "\n")
    except Exception:
        _fallback("write")


def begin_session():
    global _run_id, _sequence, _active_run, _failed, _last_successful_status, _healthy_status_count
    root = _directory()
    marker = root / "gui-session.json"
    try:
        with _lock:
            unclean = marker.exists()
            _run_id, _sequence, _active_run = uuid.uuid4().hex, 0, True
            _last_successful_status, _healthy_status_count = 0.0, 0
            _request_failures.clear()
            root.mkdir(parents=True, exist_ok=True)
            temp = marker.with_suffix(".tmp")
            temp.write_text(json.dumps({"run_id": _run_id, "pid": os.getpid(), "heartbeat": time.time()}), encoding="utf-8")
            temp.replace(marker)
    except OSError:
        unclean = False
        _fallback("session")
    emit("gui_start")
    if unclean:
        emit("gui_unclean_previous_session")


def session_heartbeat():
    try:
        with _lock:
            marker = _directory() / "gui-session.json"
            temp = marker.with_suffix(".tmp")
            temp.write_text(json.dumps({"run_id": _run_id, "pid": os.getpid(), "heartbeat": time.time()}), encoding="utf-8")
            temp.replace(marker)
        emit("gui_heartbeat")
    except OSError:
        _fallback("heartbeat")


def end_session(crashed=False, exc_type=None, tb=None):
    global _active_run
    if not _active_run:
        return
    if crashed:
        safe_exception("gui_crash", exc_type or RuntimeError, tb)
    else:
        try:
            with _lock:
                (_directory() / "gui-session.json").unlink(missing_ok=True)
        except OSError:
            pass
        emit("gui_stop")
    _active_run = False


def safe_exception(stage, exc_type, tb, request_id=None):
    frames = traceback.extract_tb(tb) if tb else []
    emit(stage, request_id=request_id or current_request_id(), error_type=getattr(exc_type, "__name__", "Exception"),
         frames=[{"filename": Path(f.filename).name, "function": f.name, "line": f.lineno} for f in frames])


def record_request_failure(request_id, method, duration_ms, error):
    now = datetime.now(timezone.utc).isoformat()
    key = (method, error)
    with _lock:
        state = _request_failures.get(key)
        if state is None:
            state = {"count": 0, "first_at": now, "last_at": now, "last_emit": time.monotonic()}
            _request_failures[key] = state
        state["count"] += 1
        state["last_at"] = now
        due = state["count"] == 1 or time.monotonic() - state["last_emit"] >= 60
        if due:
            state["last_emit"] = time.monotonic()
            row = dict(count=state["count"], first_at=state["first_at"], last_at=state["last_at"])
        else:
            row = None
    if row:
        emit("request_failure", request_id=request_id, method=method, duration_ms=duration_ms,
             outcome="error", error=error, **row)


def record_request_success(method):
    recovered = []
    with _lock:
        for key in [key for key in _request_failures if key[0] == method]:
            state = _request_failures.pop(key)
            recovered.append((key[1], state))
    for error, state in recovered:
        emit("request_failure_recovered", method=method, error=error, count=state["count"],
             first_at=state["first_at"], last_at=state["last_at"],
             recovery_ms=max(0, int((datetime.now(timezone.utc) - datetime.fromisoformat(state["first_at"])).total_seconds() * 1000)))


class MainLoopWatchdog:
    """Independent monitor; pulse() must be called by the Qt event loop."""
    def __init__(self, threshold=10.0, callback=None, poll=0.25, gap_limit=30.0):
        self.threshold, self.callback, self.poll, self.gap_limit = threshold, callback, poll, gap_limit
        self._lock = threading.Lock()
        self._pulse = time.monotonic()
        self._reported = False
        self._last_poll = time.monotonic()
        self._stopped = threading.Event()
        self._thread = threading.Thread(target=self._run, name="gui-liveness", daemon=True)
        emit("gui_watchdog_start")
        self._thread.start()

    def pulse(self):
        now = time.monotonic()
        with self._lock:
            gap = now - self._pulse
            recovery = self._reported
            self._pulse, self._reported = now, False
        if recovery:
            emit("gui_resumed", recovery_ms=int(gap * 1000))

    def _run(self):
        while not self._stopped.wait(self.poll):
            now = time.monotonic()
            poll_gap = now - self._last_poll
            self._last_poll = now
            if poll_gap > self.gap_limit:
                with self._lock:
                    self._pulse, self._reported = now, False
                emit("gui_monitor_gap", gap_kind="monitor_suspended")
                continue
            alert = None
            with self._lock:
                age = now - self._pulse
                if age >= self.threshold and not self._reported:
                    self._reported = True
                    alert = age
            if alert is not None:
                emit("gui_unresponsive", duration_ms=int(alert * 1000), threshold_ms=int(self.threshold * 1000))
                if self.callback:
                    try:
                        self.callback()
                    except Exception:
                        emit("gui_watchdog_callback_error", error_type="CallbackError")

    def close(self):
        self._stopped.set()
        if self._thread is not threading.current_thread():
            self._thread.join(timeout=1)
