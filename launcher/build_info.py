"""Single source of truth for the launcher's build properties.

Edit `launcher/build.properties` — the About dialog, the exe name and every
PyInstaller spec read from here. Version is NEVER hardcoded elsewhere.
"""
import configparser
from pathlib import Path

_BUILD_PROPS = Path(__file__).resolve().parent / "build.properties"


def _load() -> dict:
    config = configparser.ConfigParser(interpolation=None)
    config.read(_BUILD_PROPS)
    if config.has_section("build"):
        return {k: v.strip() for k, v in config.items("build")}
    return {}


_props = _load()

APP_NAME = _props.get("app_name", "Synora Bridge")
APP_VERSION = _props.get("version", "0.0.0")
EXE_NAME = _props.get("exe_name", "SynoraBridge_Launcher")
FOLDER_NAME = _props.get("folder_name", "SynoraBridge")
BUNDLE_ID = _props.get("bundle_id", "in.synorastudio.bridge.launcher")
