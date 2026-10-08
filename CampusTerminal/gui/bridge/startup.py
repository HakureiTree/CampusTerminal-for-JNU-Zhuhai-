# SPDX-License-Identifier: GPL-3.0-or-later
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET

TASK = "ReInode-CampusTerminal"
ROOT = Path(__file__).resolve().parents[2]


def pythonw():
    path = Path(sys.executable).with_name("pythonw.exe")
    return path if path.exists() else Path(sys.executable)


def _launcher():
    from gui.bridge.paths import frozen, install_root
    if not frozen():
        return None
    root = install_root()
    for name in ("开源暨珠有线网络终端.exe", "CampusTerminal.exe"):
        candidate = root / name
        if candidate.is_file():
            return candidate
    return Path(sys.executable)


def _run_key_enabled():
    import winreg
    launcher = _launcher()
    if launcher is None:
        return False
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run")
        try:
            value, _kind = winreg.QueryValueEx(key, "CampusTerminal")
        finally:
            winreg.CloseKey(key)
        text = str(value).strip()
        if text.startswith('"'):
            end = text.find('"', 1)
            exe = Path(text[1:end] if end > 0 else text.strip('"'))
        else:
            exe = Path(text.split()[0] if text else "")
        return exe.resolve() == launcher.resolve()
    except OSError:
        return False


def has_silent(text):
    return "--silent" in str(text or "").lower().split()


def show_main_on_launch(silent, tray_ready, wait_expired):
    """Autostart stays hidden. A missing tray is retried before the panel is used as a fallback."""
    if not silent:
        return True
    if tray_ready:
        return False
    return bool(wait_expired)


def _run_command():
    import winreg
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run")
        try:
            value, _kind = winreg.QueryValueEx(key, "CampusTerminal")
        finally:
            winreg.CloseKey(key)
        return str(value)
    except OSError:
        return ""


def run_key_is_silent():
    return has_silent(_run_command())


def enabled():
    from gui.bridge.paths import frozen
    if frozen():
        return _run_key_enabled()
    result = subprocess.run(["schtasks.exe", "/Query", "/TN", TASK, "/XML"],
                            capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        return False
    try:
        # schtasks labels XML UTF-16 but writes OEM bytes when stdout is a pipe.
        text = result.stdout.decode("utf-16" if result.stdout.startswith(b"\xff\xfe") else "oem")
        root = ET.fromstring(text)
        ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
        command = root.findtext("t:Actions/t:Exec/t:Command", namespaces=ns)
        args = root.findtext("t:Actions/t:Exec/t:Arguments", namespaces=ns)
        return (command is not None and Path(command) == pythonw() and
                args in (f'"{ROOT / "run.py"}"', f'"{ROOT / "run.py"}" --silent') and
                root.findtext("t:Settings/t:Enabled", namespaces=ns) != "false" and
                root.findtext("t:Principals/t:Principal/t:RunLevel", namespaces=ns) == "HighestAvailable")
    except (ET.ParseError, ValueError, UnicodeError):
        return False


def _configure_frozen(on, silent, state_dir):
    import winreg
    launcher = _launcher()
    if launcher is None or not launcher.is_file():
        raise OSError("Portable launcher missing")
    path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    access = winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE
    key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, access)
    try:
        if on:
            command = f'"{launcher}"'
            if silent:
                command += " --silent"
            winreg.SetValueEx(key, "CampusTerminal", 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, "CampusTerminal")
            except FileNotFoundError:
                pass
    finally:
        winreg.CloseKey(key)
    if enabled() != on:
        raise OSError("Startup registration could not be verified")
    (state_dir / "startup-last-report.json").write_text(
        json.dumps({"Ok": True, "Mode": "Enable" if on else "Disable", "Frozen": True}), encoding="utf-8")


def configure(on, silent, state_dir):
    from gui.bridge.paths import frozen
    state_dir.mkdir(parents=True, exist_ok=True)
    if frozen():
        _configure_frozen(on, silent, state_dir)
        return
    report = state_dir / ("startup-" + uuid.uuid4().hex + ".json")
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    command = [str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
               "-File", str(ROOT / "operations/Install-Startup.ps1"), "-Mode", "Enable" if on else "Disable",
               "-Python", str(pythonw()), "-ReportPath", str(report)]
    if silent:
        command.append("-SilentStart")
    try:
        result = subprocess.run(command, capture_output=True, timeout=150, creationflags=subprocess.CREATE_NO_WINDOW)
        status = json.loads(report.read_text(encoding="utf-8-sig")) if report.exists() else {}
        if result.returncode or not status.get("Ok") or enabled() != on:
            raise OSError(status.get("Error") or "Startup task could not be verified")
    finally:
        if report.exists():
            report.replace(state_dir / "startup-last-report.json")
