# SPDX-License-Identifier: GPL-3.0-or-later
import time
from ctypes import POINTER, Structure, byref, c_char, cast, create_string_buffer, sizeof, windll
from ctypes.wintypes import BOOL, BYTE, DWORD, UINT

import psutil

_SKIP = ("loopback", "teredo", "isatap", "wan miniport", "bluetooth", "virtual", "hyper-v", "vpn", "tap", "tun", "wintun", "clash")
_ALT = ("rndis", "remote ndis", "usb", "iphone", "tether", "android",
        "apple mobile", "mobile device", "personal hotspot", "internet sharing")
# Phone tethering only. A bare "usb" token is a USB Ethernet dongle and can be the campus port.
_TETHER = ("rndis", "remote ndis", "gadget", "iphone", "tether", "android",
           "apple mobile", "mobile device", "personal hotspot", "internet sharing",
           "mobile connect", "cdc ncm", "usb ncm", "网络共享", "手机共享")


class _Addr(Structure):
    pass


_Addr._fields_ = [
    ("Next", POINTER(_Addr)),
    ("IpAddress", c_char * 16),
    ("IpMask", c_char * 16),
    ("Context", DWORD),
]


class _Adapter(Structure):
    pass


_Adapter._fields_ = [
    ("Next", POINTER(_Adapter)),
    ("ComboIndex", DWORD),
    ("AdapterName", c_char * 260),
    ("Description", c_char * 132),
    ("AddressLength", UINT),
    ("Address", BYTE * 8),
    ("Index", DWORD),
    ("Type", UINT),
    ("DhcpEnabled", UINT),
    ("CurrentIpAddress", POINTER(_Addr)),
    ("IpAddressList", _Addr),
    ("GatewayList", _Addr),
    ("DhcpServer", _Addr),
    ("HaveWins", BOOL),
    ("PrimaryWinsServer", _Addr),
    ("SecondaryWinsServer", _Addr),
    ("LeaseObtained", DWORD),
    ("LeaseExpires", DWORD),
]


def _macs_up():
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    up = {}
    names = {}
    for name, nic in addrs.items():
        mac = next((a.address for a in nic if getattr(a.family, "name", "") == "AF_LINK" or int(a.family) == -1), "")
        key = mac.replace("-", "").replace(":", "").upper()
        if not key:
            continue
        names[key] = name
        up[key] = bool(stats.get(name) and stats[name].isup)
    return up, names


def _win_adapters():
    iphlpapi = windll.iphlpapi
    size = DWORD(sizeof(_Adapter) * 16)
    buf = create_string_buffer(size.value)
    err = iphlpapi.GetAdaptersInfo(buf, byref(size))
    if err == 111:
        buf = create_string_buffer(size.value)
        err = iphlpapi.GetAdaptersInfo(buf, byref(size))
    if err != 0:
        return []
    rows = []
    node = cast(buf, POINTER(_Adapter))
    while node:
        info = node.contents
        desc = info.Description.decode("mbcs", "replace").strip()
        guid = info.AdapterName.decode("ascii", "replace").strip("{}")
        mac = "".join(f"{info.Address[i]:02X}" for i in range(int(info.AddressLength)))
        lowered = desc.lower()
        if info.Type == 6 and not any(token in lowered for token in _SKIP):
            ipv4 = _cstr(info.IpAddressList.IpAddress)
            gateway = _cstr(info.GatewayList.IpAddress)
            rows.append({"id": guid, "description": desc, "mac": mac, "type": int(info.Type),
                         "ipv4": ipv4 if _usable_ipv4(ipv4) else "", "gateway": gateway if _usable_ipv4(gateway) else ""})
        node = info.Next
    return rows


def list_adapters():
    up, names = _macs_up()
    try:
        hardware = _win_adapters()
    except OSError:
        hardware = []
    rows = []
    for item in hardware:
        mac = item["mac"]
        name = names.get(mac, item["description"])
        if is_phone_tether(item["description"], name):
            continue
        rows.append(
            {
                "id": item["id"],
                "name": name,
                "label": "以太网:" + item["description"],
                "mac": mac,
                "up": up.get(mac, False),
            }
        )
    if rows:
        rows.sort(key=lambda r: (not r["up"], r["label"]))
        return rows
    stats = psutil.net_if_stats()
    addrs = psutil.net_if_addrs()
    for name, info in stats.items():
        lowered = name.lower()
        if any(token in lowered for token in _SKIP) or is_phone_tether(name):
            continue
        nic = addrs.get(name) or []
        mac = next((a.address for a in nic if getattr(a.family, "name", "") == "AF_LINK" or int(a.family) == -1), "")
        rows.append(
            {
                "id": name,
                "name": name,
                "label": "以太网:" + name,
                "mac": mac.replace("-", "").replace(":", ""),
                "up": bool(info.isup),
            }
        )
    rows.sort(key=lambda r: (not r["up"], r["name"]))
    return rows


def _cstr(buf):
    raw = bytes(buf).split(b"\x00", 1)[0]
    return raw.decode("ascii", "replace")


def looks_alternative(description, name=""):
    text = ((description or "") + " " + (name or "")).lower()
    if any(token in text for token in _SKIP):
        return False
    return any(token in text for token in _ALT)


def is_phone_tether(description, name=""):
    text = ((description or "") + " " + (name or "")).lower()
    if any(token in text for token in _SKIP):
        return False
    if "远程" in text and "ndis" in text:
        return True
    return any(token in text for token in _TETHER)


def _usable_ipv4(address):
    parts = (address or "").split(".")
    if len(parts) != 4:
        return False
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return False
    return nums[0] not in (0, 127) and nums[0] < 224 and not (nums[0] == 169 and nums[1] == 254)


def alternative_path(campus_id):
    campus = (campus_id or "").strip("{}").lower()
    for item in _win_adapters_safe():
        if campus and item["id"].strip("{}").lower() == campus:
            continue
        if not looks_alternative(item.get("description", "")):
            continue
        if item.get("ipv4") or item.get("gateway"):
            return True
    return False


def path_census(campus_id=""):
    campus = (campus_id or "").strip("{}").lower()
    rows = []
    for item in _win_adapters_safe():
        text = item.get("description", "")
        rows.append({
            "id": item.get("id", ""),
            "description": text,
            "mac": item.get("mac", ""),
            "ipv4": item.get("ipv4", ""),
            "gateway": item.get("gateway", ""),
            "campus": bool(campus and item.get("id", "").strip("{}").lower() == campus),
            "alternative": looks_alternative(text) and bool(item.get("ipv4") or item.get("gateway")),
        })
    stats = psutil.net_if_stats()
    addrs = psutil.net_if_addrs()
    seen = {row["mac"] for row in rows}
    for name, nic in addrs.items():
        mac = next((a.address for a in nic if getattr(a.family, "name", "") == "AF_LINK" or int(a.family) == -1), "")
        mac = mac.replace("-", "").replace(":", "").upper()
        if mac and mac in seen:
            continue
        ipv4 = next((a.address for a in nic if _usable_ipv4(getattr(a, "address", ""))), "")
        rows.append({
            "id": "",
            "description": name,
            "mac": mac,
            "ipv4": ipv4,
            "gateway": "",
            "campus": False,
            "alternative": looks_alternative(name) and bool(ipv4),
            "up": bool(stats.get(name) and stats[name].isup),
        })
    return rows


def _win_adapters_safe():
    try:
        return _win_adapters()
    except OSError:
        return []


class TrafficSampler:
    def __init__(self):
        self._name = None
        self._prev = None
        self._at = None
        self.samples = []

    def set_adapter(self, name):
        self._name = name
        self._prev = None
        self._at = None
        self.samples = []

    def tick(self):
        counters = psutil.net_io_counters(pernic=True)
        name = self._name
        if not name or name not in counters:
            self._prev = None
            self._at = None
            self.samples = []
            return 0.0, 0.0, []
        now = time.monotonic()
        cur = counters[name]
        tx = rx = 0.0
        if self._prev is not None and now > self._at:
            dt = now - self._at
            rx = max(0.0, (cur.bytes_recv - self._prev.bytes_recv) / dt)
            tx = max(0.0, (cur.bytes_sent - self._prev.bytes_sent) / dt)
            self.samples.append(rx + tx)
            self.samples = self.samples[-60:]
        self._prev = cur
        self._at = now
        return tx, rx, list(self.samples)
