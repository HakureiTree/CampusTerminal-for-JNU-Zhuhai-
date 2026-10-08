# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path

import psutil

CLIENT = Path(r"C:\Program Files (x86)\iNode\iNode Client\iNode Client.exe")


def present():
    return CLIENT.is_file()


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
