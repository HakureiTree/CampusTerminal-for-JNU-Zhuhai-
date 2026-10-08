# SPDX-License-Identifier: GPL-3.0-or-later
import ctypes
import json
import subprocess
import time
from pathlib import Path
from PyQt5.QtNetwork import QLocalSocket
from gui.bridge.paths import core_exe

PIPE = "CampusTerminal.gui"
HOST_TASK = "ReInode-CampusTerminal-Host"
_STILL_ACTIVE = 259
_PROCESS_QUERY = 0x1000
_PROCESS_TERMINATE = 0x0001


def _kernel32():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
    kernel.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_wchar_p,
                                                 ctypes.POINTER(ctypes.c_uint32)]
    return kernel


def process_running(pid):
    if not pid:
        return False
    kernel = _kernel32()
    handle = kernel.OpenProcess(_PROCESS_QUERY | _PROCESS_TERMINATE, False, int(pid))
    if not handle:
        handle = kernel.OpenProcess(_PROCESS_QUERY, False, int(pid))
    if not handle:
        return False
    try:
        code = ctypes.c_uint32()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == _STILL_ACTIVE
    finally:
        kernel.CloseHandle(handle)


def process_image_path(pid):
    if not pid:
        return None
    kernel = _kernel32()
    handle = kernel.OpenProcess(_PROCESS_QUERY, False, int(pid))
    if not handle:
        return None
    try:
        buf = ctypes.create_unicode_buffer(32768)
        size = ctypes.c_uint32(32768)
        if not kernel.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return None
        return buf.value
    finally:
        kernel.CloseHandle(handle)


def terminate_process(pid):
    if not pid:
        return False
    kernel = _kernel32()
    handle = kernel.OpenProcess(_PROCESS_TERMINATE, False, int(pid))
    if not handle:
        return False
    try:
        return bool(kernel.TerminateProcess(handle, 1))
    finally:
        kernel.CloseHandle(handle)


class BackendClient:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.exe = core_exe(self.root)
        self.process = None
        self.last_pid = None

    def available(self):
        found = core_exe(self.root)
        if found.is_file():
            self.exe = found
            return True
        self.exe = found
        return False

    def _talk_py(self, payload, timeout=3.0):
        socket = QLocalSocket()
        deadline = time.monotonic() + timeout
        remaining = lambda: max(1, int((deadline - time.monotonic()) * 1000))
        try:
            connect_deadline = min(deadline, time.monotonic() + 1)
            while True:
                socket.connectToServer(PIPE)
                if socket.waitForConnected(min(200, remaining())):
                    break
                if time.monotonic() >= connect_deadline:
                    return {"ok": False, "error": "BackendUnavailable", "detail": socket.errorString()}
                socket.abort()
                time.sleep(.02)
            socket.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
            if socket.bytesToWrite() and not socket.waitForBytesWritten(remaining()):
                return {"ok": False, "error": "BackendTimeout"}
            while time.monotonic() < deadline:
                if socket.canReadLine():
                    result = json.loads(bytes(socket.readLine()).decode("utf-8"))
                    if not isinstance(result, dict) or result.get("id") != payload["id"]:
                        return {"ok": False, "error": "BackendProtocolError"}
                    return result
                if socket.bytesAvailable() > 65536:
                    return {"ok": False, "error": "BackendProtocolError"}
                if not socket.waitForReadyRead(remaining()):
                    break
            return {"ok": False, "error": "BackendTimeout"}
        except (OSError, ValueError, UnicodeError):
            return {"ok": False, "error": "BackendProtocolError"}
        finally:
            socket.abort()

    def ensure_started(self, elevated=False):
        if not self.available():
            return {"ok": False, "error": "BackendMissing", "detail": str(self.exe)}
        current = self.status()
        if current.get("ok") and (not elevated or current.get("elevated")) and self._same_host(current):
            return current
        if current.get("ok"):
            stopped = self.shutdown()
            if not stopped.get("ok"):
                return stopped
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and self.status().get("ok"):
                time.sleep(.1)
        try:
            if elevated:
                if not self._start_elevated_host():
                    return {"ok": False, "error": "ElevationCancelled"}
            else:
                self.process = subprocess.Popen([str(self.exe), "gui-host"], cwd=self.root,
                                                creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)
        except OSError:
            return {"ok": False, "error": "BackendLaunchFailed"}
        deadline = time.monotonic() + (90 if elevated else 45)
        while time.monotonic() < deadline:
            reply = self.status()
            if reply.get("ok") and (not elevated or reply.get("elevated")):
                return reply
            time.sleep(.2)
        return {"ok": False, "error": "BackendStartTimeout"}

    def _same_host(self, status):
        remote = status.get("executable") or process_image_path(status.get("processId"))
        if not remote:
            return False
        try:
            return Path(remote).resolve() == self.exe.resolve()
        except OSError:
            return False

    def _start_elevated_host(self):
        try:
            launched = subprocess.run(
                ["schtasks.exe", "/Run", "/TN", HOST_TASK],
                capture_output=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
            if launched.returncode == 0:
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    st = self.status()
                    if st.get("ok") and self._same_host(st):
                        return True
                    if st.get("ok"):
                        self.shutdown()
                        break
                    time.sleep(.2)
        except (OSError, subprocess.TimeoutExpired):
            pass
        shell = ctypes.WinDLL("shell32", use_last_error=True)
        shell.ShellExecuteW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p,
                                       ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_int]
        shell.ShellExecuteW.restype = ctypes.c_void_p
        result = shell.ShellExecuteW(None, "runas", str(self.exe), "gui-host", str(self.exe.parent), 0)
        return bool(result and result > 32)

    def status(self):
        result = self._talk_py({"id": 1, "method": "status"})
        if result.get("ok") and result.get("processId"):
            self.last_pid = result["processId"]
        return result

    def connect(self, username, password, adapter, options):
        ready = self.ensure_started(elevated=True)
        if not ready.get("ok"):
            return ready
        return self._talk_py({"id": 2, "method": "connect", "username": username,
                             "password": password, "adapter": adapter, "options": options}, timeout=10)

    def disconnect(self):
        return self._talk_py({"id": 3, "method": "disconnect"}, timeout=20)

    def release_campus(self, adapter):
        ready = self.ensure_started(elevated=True)
        if not ready.get("ok"):
            return ready
        return self._talk_py({"id": 8, "method": "releaseCampus", "adapter": adapter})

    def configure(self, options):
        return self._talk_py({"id": 5, "method": "configure", "options": options})

    def wait_until_stopped(self, pid=None, timeout=10):
        pid = pid or self.last_pid
        child = self.process
        if not pid and child is None:
            return True
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            child_alive = child is not None and child.poll() is None
            if not process_running(pid) and not child_alive:
                self.process = None
                return True
            time.sleep(.15)
        if process_running(pid):
            terminate_process(pid)
            time.sleep(.3)
        if child is not None and child.poll() is None:
            try:
                child.terminate()
                child.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                pass
        self.process = None
        return not process_running(pid) and (child is None or child.poll() is not None)

    def shutdown(self, handoff=False, adapter=""):
        if handoff:
            # Exit must not resurrect a missing backend and start a new handoff.
            current = self.status()
            if not current.get("ok"):
                return current
            ready = self.ensure_started(elevated=True)
            if not ready.get("ok"):
                return ready
        result = self._talk_py({"id": 4, "method": "shutdown", "handoff": handoff, "adapter": adapter}, timeout=20)
        if result.get("ok") and result.get("processId"):
            self.last_pid = result["processId"]
        if not handoff:
            if not self.wait_until_stopped(result.get("processId") or self.last_pid):
                return {"ok": False, "error": "BackendStopTimeout", "processId": self.last_pid}
        elif self.process is not None and result.get("ok") and not result.get("pending"):
            try:
                self.process.wait(timeout=5)
                self.process = None
            except subprocess.TimeoutExpired:
                return {"ok": False, "error": "BackendStopTimeout"}
        return result
