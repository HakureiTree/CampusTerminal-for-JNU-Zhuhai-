# SPDX-License-Identifier: GPL-3.0-or-later
import sys
from pathlib import Path


def frozen():
    return bool(getattr(sys, "frozen", False))


def resource_root():
    if frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[1]


def install_root():
    if frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


_CORE_RELATIVE = (
    "CampusTerminal.Core.exe",
    "core/bin/Release/net10.0-windows/CampusTerminal.Core.exe",
    "core/bin/Debug/net10.0-windows/CampusTerminal.Core.exe",
)


def _resolved(path):
    try:
        return Path(path).resolve()
    except OSError:
        return Path(path)


def search_roots(root: Path):
    ordered = []
    extras = [root]
    if frozen():
        extras.append(Path(sys.executable).parent)
    extras.append(Path.cwd())
    for item in extras:
        if item is None:
            continue
        resolved = _resolved(item)
        if resolved not in ordered:
            ordered.append(resolved)
    return ordered


def core_candidates(root: Path):
    for folder in search_roots(root):
        for rel in _CORE_RELATIVE:
            yield folder / rel


def core_exe(root: Path):
    first = None
    for candidate in core_candidates(root):
        if first is None:
            first = candidate
        if candidate.is_file():
            return candidate
    return first if first is not None else Path(root) / "CampusTerminal.Core.exe"


def diagnose(root: Path):
    exe = core_exe(root)
    return {
        "frozen": frozen(),
        "install_root": str(_resolved(root)),
        "core": str(exe),
        "core_exists": exe.is_file(),
    }
