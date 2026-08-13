# -*- mode: python ; coding: utf-8 -*-
# PyInstaller ALL-IN-ONE spec — the launcher exe contains the ENTIRE app:
#   - the Stack Launcher GUI (PySide6 + qt-material)
#   - the backend source (staged: installer_stage/backend) + every backend
#     dependency (django, daphne, celery, channels, DRF, ...) — run via the
#     hidden `--service daphne|worker|beat` mode (launcher/__main__.py)
#   - the frontend production build (frontend/.output)
#   - a node runtime (staged: installer_stage/runtime/node)
#
# Build:  build_allinone.bat   (or)
#         backend\.venv\Scripts\pyinstaller.exe launcher_allinone.spec --noconfirm
# Output: dist\allinone\SynoraBridge\SynoraBridge_Launcher.exe
#   Double-click it — the whole stack starts from the launcher. No repo, no
#   Python, no node needed.

import sys  # noqa: E402
import configparser
from pathlib import Path

from PyInstaller.utils.hooks import collect_all  # noqa: E402

# Build properties — single source of truth: launcher/build.properties
_props = configparser.ConfigParser(interpolation=None)
_props.read(Path(__file__).resolve().parent / "launcher" / "build.properties")
_VERSION = _props.get("build", "version", fallback="0.0.0")
_EXE_NAME = _props.get("build", "exe_name", fallback="SynoraBridge_Launcher")
_APP_NAME = _props.get("build", "app_name", fallback="Synora Bridge")
_FOLDER_NAME = _props.get("build", "folder_name", fallback="SynoraBridge")
_BUNDLE_ID = _props.get("build", "bundle_id", fallback="in.synorastudio.bridge.launcher")

# ---- Backend dependencies (all shipped inside the bundle) ----------------
BACKEND_DEPS = [
    "django", "asgiref", "sqlparse", "tzdata", "psycopg2", "redis", "dotenv",
    "rest_framework", "drf_spectacular", "strawberry", "graphql",
    "openapi_spec_validator", "openapi_schema_validator", "jsonschema",
    "jsonschema_path", "jsonschema_specifications", "pathable",
    "lazy_object_proxy", "referencing", "rpds", "rfc3339_validator",
    "corsheaders", "ratelimit", "cryptography", "cffi", "pycparser",
    "celery", "django_celery_beat", "billiard", "kombu", "amqp", "vine",
    "click", "click_didyoumean", "click_plugins", "click_repl",
    "prompt_toolkit", "wcwidth", "colorama",
    "channels", "channels_redis", "daphne", "autobahn", "twisted",
    "incremental", "constantly", "hyperlink", "txaio", "zope.interface",
    "msgpack", "requests", "httpx", "httpcore", "urllib3", "certifi", "idna",
    "charset_normalizer", "h11", "anyio", "whitenoise", "yaml",
    "django_timezone_field", "dateutil", "six", "typing_extensions", "attrs",
    "packaging", "markdown", "bleach", "tzdata",
]

hiddenimports = ["PySide6.QtUiTools"]
datas = []
binaries = []
for _pkg in BACKEND_DEPS:
    try:
        _hd, _dt, _bn = collect_all(_pkg)
        for _h in _hd:
            # django's collect_all mixes (src, dest) data tuples into
            # hiddenimports — route tuples to datas, keep strings as imports.
            if isinstance(_h, str):
                hiddenimports.append(_h)
            else:
                datas.append(_h)
        for _b in _bn:
            # Keep only (src, dest) pairs; skip malformed entries.
            if isinstance(_b, tuple) and len(_b) == 2 and all(isinstance(x, str) for x in _b):
                binaries.append(_b)
            elif isinstance(_b, str):
                # A bare path — treat as a data file so the build still works.
                datas.append((_b, "."))
        datas += _dt
    except Exception:  # noqa: BLE001 — optional/absent packages are skipped
        print(f"[spec] skip collect of {_pkg}", file=sys.stderr)

# ---- App data: UI, styles, backend source, frontend build, node ----------
datas += [
    ("launcher/ui/main_window.ui", "launcher/ui"),
    ("launcher/style", "launcher/style"),
    # Clean backend source (staged by build_allinone.bat — no .venv/caches)
    ("installer_stage/backend", "backend"),
    # Frontend production build
    ("frontend/.output", "frontend/.output"),
    # Node runtime (staged)
    ("installer_stage/runtime", "runtime"),
]
datas += [(p, d) for p, d in collect_all("qt_material")[1]
          if any(f"/{m}_" in p.replace("\\", "/") for m in (
              "dark_amber", "dark_blue", "dark_cyan", "dark_lightgreen",
              "dark_pink", "dark_purple", "dark_red", "dark_teal", "dark_yellow",
              "light_amber", "light_blue", "light_cyan", "light_lightgreen",
              "light_pink", "light_purple", "light_red", "light_teal", "light_yellow"))]

# ---- Excludes (unused Qt + dev cruft) ------------------------------------
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
    "pytest", "setuptools", "pip",
]

a = Analysis(
    ["launcher_entry.py"],
    pathex=["."],
    binaries=binaries,
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
    [],
    exclude_binaries=True,
    name=_EXE_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUI app
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    name=_FOLDER_NAME,
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{_APP_NAME}.app",
        icon=None,
        bundle_identifier=_BUNDLE_ID,
    )
