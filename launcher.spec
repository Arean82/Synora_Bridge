# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the Synora Bridge Stack Launcher (PySide6).
#
# Build:  backend\.venv\Scripts\pyinstaller.exe launcher.spec --noconfirm
# Output: dist\SynoraBridge_Launcher.exe  (onefile, windowed — no console)
#
# At runtime the exe expects the repo stack beside it (backend\, frontend\)
# or a SYNORA_HOME env var pointing at it; see launcher/config.py.
# NOTE: prefer the onedir build (launcher_onedir.spec) for daily use — it
# starts much faster (onefile re-extracts its archive to %TEMP% every launch).

import configparser
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

# Build properties — single source of truth: launcher/build.properties
_props = configparser.ConfigParser(interpolation=None)
_props.read(Path(__file__).resolve().parent / "launcher" / "build.properties")
_VERSION = _props.get("build", "version", fallback="0.0.0")
_EXE_NAME = _props.get("build", "exe_name", fallback="SynoraBridge_Launcher")
_APP_NAME = _props.get("build", "app_name", fallback="Synora Bridge")

datas = [
    # The Qt Designer layout + QSS looks are loaded at runtime — bundle them.
    ("launcher/ui/main_window.ui", "launcher/ui"),
    ("launcher/style", "launcher/style"),
]
# qt-material ships its theme XMLs inside the package — collect them all.
datas += collect_data_files("qt_material")

# Only the themes we expose in the menu are needed (9 dark + 9 light).
datas += [(p, d) for p, d in collect_data_files("qt_material")
          if any(f"/{m}_" in p.replace("\\", "/") for m in (
              "dark_amber", "dark_blue", "dark_cyan", "dark_lightgreen",
              "dark_pink", "dark_purple", "dark_red", "dark_teal", "dark_yellow",
              "light_amber", "light_blue", "light_cyan", "light_lightgreen",
              "light_pink", "light_purple", "light_red", "light_teal", "light_yellow"))]

hiddenimports = ["PySide6.QtUiTools"]

# Qt modules we never touch — excluding them keeps the bundle smaller (and
# onefile extraction faster). WebEngine alone is hundreds of MB.
excludes = [
    "tkinter",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebChannel",
    "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtQml", "PySide6.QtQmlModels",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtCharts",
    "PySide6.QtDataVisualization", "PySide6.Qt3DCore", "PySide6.Qt3DRender",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtDesigner", "PySide6.QtHelp",
    "PySide6.QtSql", "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtTest",
    "PySide6.QtWebSockets", "PySide6.QtWebView", "PySide6.QtBluetooth",
    "PySide6.QtNfc", "PySide6.QtPositioning", "PySide6.QtLocation", "PySide6.QtScxml",
]

a = Analysis(
    ["launcher_entry.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=_EXE_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=["vcruntime140.dll", "python3*.dll"],
    console=False,  # GUI app
    disable_windowed_traceback=False,
)

