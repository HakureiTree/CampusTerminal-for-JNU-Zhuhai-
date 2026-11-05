# SPDX-License-Identifier: GPL-3.0-or-later
import winreg

import psutil

SERVICE_KEY = r"SYSTEM\CurrentControlSet\Services\INODE_SVR_SERVICE"


def present():
    # This controls UI availability only. The elevated handoff validates the
    # registered executable and running image before performing any action.
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, SERVICE_KEY) as key:
            command, _kind = winreg.QueryValueEx(key, "ImagePath")
        return isinstance(command, str) and bool(command.strip())
    except OSError:
        return False


def _process_base(name):
    text = (name or "").lower()
    return text[:-4] if text.endswith(".exe") else text


def gui_running():
    for proc in psutil.process_iter(["name"]):
        try:
            if _process_base(proc.info.get("name")) == "inode client":
                return True
        except (psutil.Error, OSError, TypeError, AttributeError):
            continue
    return False
