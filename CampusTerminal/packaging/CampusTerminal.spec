# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path

root = Path(SPECPATH).resolve().parent
gui = root / "gui"

a = Analysis(
    [str(root / "run.py")],
    pathex=[str(gui)],
    binaries=[],
    datas=[(str(gui / "assets"), "gui/assets")],
    hiddenimports=[
        "PyQt5", "PyQt5.QtCore", "PyQt5.QtGui", "PyQt5.QtWidgets",
        "PyQt5.QtNetwork", "PyQt5.QtSvg", "PyQt5.sip",
        "gui", "gui.app", "gui.theme",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CampusTerminal",
    icon=str(gui / "assets" / "icons" / "app" / "app.ico"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="CampusTerminal",
)
