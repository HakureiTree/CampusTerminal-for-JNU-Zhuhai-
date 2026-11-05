# SPDX-License-Identifier: GPL-3.0-or-later
"""Cheap GUI resource sampling for the diagnostic journal.

The sampler runs on the Qt main thread once a minute, so every operating
system lookup is optional: unavailable values become 0 instead of raising.
"""
import ctypes
import os

try:
    import psutil
except Exception:  # pragma: no cover - psutil ships with the application
    psutil = None

GDI_RESOURCES = 0
USER_RESOURCES = 1
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_MIB = 1024 * 1024

try:
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.OpenProcess.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_uint]
    _kernel32.OpenProcess.restype = ctypes.c_void_p
    _kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    _kernel32.CloseHandle.restype = ctypes.c_int
    _user32.GetGuiResources.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    _user32.GetGuiResources.restype = ctypes.c_uint
except Exception:  # pragma: no cover - only Windows runs the GUI
    _user32 = None
    _kernel32 = None


def _gui_resources(flag, pid=None):
    """Process GDI (flag 0) or USER (flag 1) object count; 0 when unavailable."""
    try:
        handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False,
                                       os.getpid() if pid is None else int(pid))
        if not handle:
            return 0
        try:
            return int(_user32.GetGuiResources(handle, flag))
        finally:
            _kernel32.CloseHandle(handle)
    except Exception:
        return 0


def _process(process=None):
    if process is not None:
        return process
    return psutil.Process(os.getpid())


def _private_bytes(process=None):
    """Private committed bytes, falling back to RSS when the platform lacks it."""
    try:
        info = _process(process).memory_info()
        value = getattr(info, "private", None)
        if value is None:
            value = getattr(info, "rss", 0)
        return int(value)
    except Exception:
        return 0


def _safe_int(read, default=0):
    try:
        value = read()
    except Exception:
        return default
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if number > 0 else default


def _as_bool(value):
    try:
        return bool(value)
    except Exception:
        return False


def sample_resources(visible, flashing, process=None):
    """Return the current GDI/USER/private-memory and visibility snapshot."""
    return {
        "gdi": _safe_int(lambda: _gui_resources(GDI_RESOURCES)),
        "user": _safe_int(lambda: _gui_resources(USER_RESOURCES)),
        "private_mb": _safe_int(lambda: _private_bytes(process)) // _MIB,
        "visible": _as_bool(visible),
        "tray_flashing": _as_bool(flashing),
    }
