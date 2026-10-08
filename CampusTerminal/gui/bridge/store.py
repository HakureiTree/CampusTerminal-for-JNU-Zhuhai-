# SPDX-License-Identifier: GPL-3.0-or-later
import json
import os
import uuid
from base64 import b64decode, b64encode
from ctypes import POINTER, Structure, byref, c_byte, c_void_p, c_wchar_p, windll
from ctypes.wintypes import BOOL, DWORD
from pathlib import Path

def _writable(candidate):
    candidate.mkdir(parents=True, exist_ok=True)
    probe = candidate / ".write"
    probe.write_text("ok", encoding="utf-8")
    probe.unlink()
    return candidate


def _app_dir():
    if os.environ.get("CAMPUS_TERMINAL_STATE"):
        return Path(os.environ["CAMPUS_TERMINAL_STATE"])
    from gui.bridge.edition import current
    from gui.bridge.paths import frozen, install_root
    if current() == "portable":
        return _writable(install_root() / "state")
    preferred = Path.home() / "AppData" / "Roaming" / "CampusTerminal"
    fallback = (install_root() if frozen() else Path(__file__).resolve().parents[2]) / "state"
    for candidate in (preferred, fallback):
        try:
            return _writable(candidate)
        except OSError:
            continue
    return preferred


APP_DIR = _app_dir()
SETTINGS_PATH = APP_DIR / "ui-settings.dpapi"
SECRET_PATH = APP_DIR / "password.dpapi"

DEFAULTS = {
    "account": "",
    "save_account": True,
    "save_password": False,
    "adapter": "",
    "adapter_id": "",
    "conn_type": "normal",
    "auto_start": True,
    "silent_start": False,
    "auto_connect": True,
    "auto_reconnect": True,
    "seamless": False,
    "inode_fallback": False,
}


class _Blob(Structure):
    _fields_ = [("cbData", DWORD), ("pbData", POINTER(c_byte))]


def load():
    APP_DIR.mkdir(parents=True, exist_ok=True)
    data = None
    if SETTINGS_PATH.exists():
        try:
            data = json.loads(_unprotect(SETTINGS_PATH.read_bytes()))
        except (ValueError, UnicodeError) as exc:
            raise OSError("Stored settings cannot be decrypted or decoded") from exc
    else:
        portable_json = APP_DIR / "ui-settings.json"
        if portable_json.exists():
            try:
                data = json.loads(portable_json.read_text(encoding="utf-8-sig"))
            except (ValueError, UnicodeError) as exc:
                raise OSError("Stored settings are invalid; original file preserved") from exc
            from gui.bridge.edition import current
            if current() != "portable":
                save(data)
                portable_json.unlink()
                return load()
        else:
            return dict(DEFAULTS)
    if not isinstance(data, dict):
        raise OSError("Stored settings are invalid; original file preserved")
    merged = dict(DEFAULTS)
    merged.update({k: data[k] for k in DEFAULTS if k in data})
    return merged


def save(data):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    payload = dict(DEFAULTS)
    payload.update({k: data[k] for k in DEFAULTS if k in data})
    if not payload.get("save_account"):
        payload["account"] = ""
    payload["conn_type"] = "normal"
    payload["seamless"] = False
    raw = json.dumps(payload, ensure_ascii=False)
    try:
        _atomic_write(SETTINGS_PATH, _protect(raw))
    except OSError:
        from gui.bridge.edition import current
        if current() != "portable":
            raise
        (APP_DIR / "ui-settings.json").write_text(raw, encoding="utf-8")


def _atomic_write(path, ciphertext):
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temp.open("xb") as stream:
            stream.write(ciphertext)
            stream.flush()
            os.fsync(stream.fileno())
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def startup_enabled():
    from gui.bridge import startup
    return startup.enabled()


def set_startup(enabled, silent=False):
    from gui.bridge import startup
    startup.configure(enabled, silent, APP_DIR)


def sync_silent_startup(silent):
    """Keep the logon command aligned with “自启动后不显示主面板” after the box is already checked."""
    from gui.bridge import startup
    from gui.bridge.paths import frozen
    if not frozen() or not startup.enabled():
        return
    if startup.run_key_is_silent() == bool(silent):
        return
    startup.configure(True, bool(silent), APP_DIR)


def _crypt():
    crypt = windll.crypt32
    crypt.CryptProtectData.argtypes = [POINTER(_Blob), c_wchar_p, POINTER(_Blob), c_void_p, c_void_p, DWORD, POINTER(_Blob)]
    crypt.CryptProtectData.restype = BOOL
    crypt.CryptUnprotectData.argtypes = [POINTER(_Blob), c_void_p, POINTER(_Blob), c_void_p, c_void_p, DWORD, POINTER(_Blob)]
    crypt.CryptUnprotectData.restype = BOOL
    return crypt


def _protect(text):
    raw = text.encode("utf-8")
    incoming = _Blob(len(raw), (c_byte * len(raw)).from_buffer_copy(raw))
    outgoing = _Blob()
    crypt = _crypt()
    if not crypt.CryptProtectData(byref(incoming), None, None, None, None, 1, byref(outgoing)):
        if not crypt.CryptProtectData(byref(incoming), None, None, None, None, 0, byref(outgoing)):
            raise OSError("CryptProtectData failed")
    try:
        return bytes(outgoing.pbData[i] & 0xFF for i in range(outgoing.cbData))
    finally:
        windll.kernel32.LocalFree(outgoing.pbData)


def _unprotect(blob):
    incoming = _Blob(len(blob), (c_byte * len(blob)).from_buffer_copy(blob))
    outgoing = _Blob()
    crypt = _crypt()
    if not crypt.CryptUnprotectData(byref(incoming), None, None, None, None, 1, byref(outgoing)):
        if not crypt.CryptUnprotectData(byref(incoming), None, None, None, None, 0, byref(outgoing)):
            raise OSError("CryptUnprotectData failed")
    try:
        data = bytes(outgoing.pbData[i] & 0xFF for i in range(outgoing.cbData))
    finally:
        windll.kernel32.LocalFree(outgoing.pbData)
    return data.decode("utf-8")


def save_password(password):
    if not password:
        return
    APP_DIR.mkdir(parents=True, exist_ok=True)
    _atomic_write(SECRET_PATH, b64encode(_protect(password)))


def load_password():
    if not SECRET_PATH.exists():
        return ""
    try:
        return _unprotect(b64decode(SECRET_PATH.read_bytes()))
    except (OSError, ValueError):
        return ""


def clear_password():
    try:
        SECRET_PATH.unlink()
    except FileNotFoundError:
        pass
