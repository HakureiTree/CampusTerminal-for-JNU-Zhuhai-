# SPDX-License-Identifier: GPL-3.0-or-later
# Packaged builds may drop edition.txt beside the exe ("portable" or "installed").
EDITION = "installed"


def current():
    from gui.bridge.paths import install_root
    root = install_root()
    marker = root / "edition.txt"
    if marker.is_file():
        value = marker.read_text(encoding="utf-8").strip().lower()
        if value in ("portable", "installed"):
            return value
    if (root / "CampusTerminal.portable").is_file():
        return "portable"
    return EDITION
