"""Launcher support — paths, platform helpers, config.ini access.

Mirrors the backend's own helpers (backend/config/ini_config.py) so the
launcher and the Settings web UI never disagree.
"""
from __future__ import annotations

import configparser
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
from pathlib import Path

# PyInstaller frozen mode: __file__ lives in the extraction dir (_MEIPASS).
FROZEN = bool(getattr(sys, "frozen", False))


def _repo_root() -> Path:
    """Repo root. Frozen: the exe's directory (or SYNORA_HOME override) — the
    stack (backend/, frontend/) must live beside the exe, or is bundled
    inside the all-in-one build."""
    if FROZEN:
        return Path(os.environ.get("SYNORA_HOME", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent.parent


def _launcher_dir() -> Path:
    """Where the bundled .ui/.qss live. Frozen: inside the PyInstaller bundle
    (_MEIPASS) under the 'launcher' prefix (the spec bundles
    launcher/ui/… and launcher/style/…); dev: this package directory."""
    if FROZEN:
        return Path(getattr(sys, "_MEIPASS", REPO_ROOT)) / "launcher"
    return Path(__file__).resolve().parent


REPO_ROOT = _repo_root()
LAUNCHER_DIR = _launcher_dir()


def _backend_dir() -> Path:
    """Backend source root. Frozen all-in-one: bundled inside the app under
    '_internal/backend' (onedir) / '_MEIPASS/backend' (onefile); dev or
    developer exe: the repo beside the exe."""
    if FROZEN:
        bundled = Path(getattr(sys, "_MEIPASS", REPO_ROOT)) / "backend"
        if bundled.exists():
            return bundled
        return REPO_ROOT / "backend"
    return REPO_ROOT / "backend"


def _frontend_dir() -> Path:
    """Frontend root (production build under it). Frozen all-in-one: bundled
    '_internal/frontend'; developer exe: repo beside the exe."""
    if FROZEN:
        bundled = Path(getattr(sys, "_MEIPASS", REPO_ROOT)) / "frontend"
        if bundled.exists():
            return bundled
    return REPO_ROOT / "frontend"


def _runtime_dir() -> Path:
    """Bundled runtimes (e.g. node). Frozen all-in-one: '_internal/runtime'."""
    if FROZEN:
        bundled = Path(getattr(sys, "_MEIPASS", REPO_ROOT)) / "runtime"
        if bundled.exists():
            return bundled
    return REPO_ROOT / "runtime"


BACKEND_DIR = _backend_dir()
FRONTEND_DIR = _frontend_dir()
RUNTIME_DIR = _runtime_dir()
UI_DIR = LAUNCHER_DIR / "ui"
STYLE_DIR = LAUNCHER_DIR / "style"

CONFIG_INI = BACKEND_DIR / "config.ini"
# Runtime prefs must be writable: never inside the onefile _MEIPASS temp dir.
LAUNCHER_JSON = (REPO_ROOT / "launcher.json") if FROZEN else (LAUNCHER_DIR / "launcher.json")

IS_WINDOWS = os.name == "nt"


def service_argv(*args) -> list[str]:
    """Command line for a backend service.

    Frozen all-in-one: the exe re-invokes itself in --service mode (the whole
    stack — django/daphne/celery — is bundled). Dev/developer exe: the repo
    venv's python runs `python -m …`.
    """
    if FROZEN:
        return [sys.executable, "--service"] + list(args)
    python = VENV_PYTHON if VENV_PYTHON.exists() else sys.executable
    return [str(python), "-m"] + list(args)


def _venv_layout() -> tuple[Path, Path]:
    """(python executable, scripts/bin dir) for the venv on this platform."""
    if IS_WINDOWS:
        return BACKEND_DIR / ".venv" / "Scripts" / "python.exe", BACKEND_DIR / ".venv" / "Scripts"
    return BACKEND_DIR / ".venv" / "bin" / "python", BACKEND_DIR / ".venv" / "bin"


VENV_PYTHON, VENV_SCRIPTS = _venv_layout()


def npm_argv(*args) -> list[str]:
    """npm on Windows is a .cmd shim — spawn through cmd.exe so it resolves;
    on POSIX call npm directly. The whole tree is killed via process group."""
    if IS_WINDOWS:
        return [os.environ.get("COMSPEC", "cmd.exe"), "/c"] + list(args)
    return list(args)


def kill_process_tree(proc: subprocess.Popen) -> None:
    """Kill a process and its children: taskkill /T on Windows, the process
    group (start_new_session) on POSIX."""
    if IS_WINDOWS:
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)  # type: ignore[attr-defined]  # noqa: E501  (POSIX-only)
        except (OSError, ProcessLookupError):
            return
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)  # type: ignore[attr-defined]  # noqa: E501  (POSIX-only)
            except (OSError, ProcessLookupError):
                pass


def open_file_default(path: Path) -> None:
    """Open a file with the OS default application."""
    if IS_WINDOWS:
        os.startfile(path)  # noqa: S606
    else:
        opener = shutil.which("xdg-open") or shutil.which("open")
        if opener:
            subprocess.Popen([opener, str(path)])  # noqa: S603


def read_ini(path: Path) -> dict:
    """Read a config.ini as {section: {key: value}} (no interpolation)."""
    config = configparser.ConfigParser(interpolation=None)
    config.read(path)
    return {section: dict(config.items(section)) for section in config.sections()}


def set_ini_value(path: Path, section: str, key: str, value: str) -> None:
    """Set ``key = value`` inside ``[section]`` preserving comments/formatting
    (mirrors backend/config/ini_config.py so the web UI and launcher agree)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    header = f"[{section}]"
    in_section = False
    replaced = False
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("["):
            in_section = stripped.lower() == header.lower()
        elif (
            in_section
            and not stripped.startswith(("#", ";"))
            and re.match(rf"^{re.escape(key)}\s*=", stripped, re.IGNORECASE)
        ):
            indent = line[: len(line) - len(line.lstrip())]
            out.append(f"{indent}{key} = {value}")
            replaced = True
            continue
        out.append(line)
    if not replaced:
        if not any(l.strip().lower() == header.lower() for l in out):
            out.append("")
            out.append(header)
        out.append(f"{key} = {value}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def load_launcher_json() -> dict:
    try:
        return json.loads(LAUNCHER_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_launcher_json(data: dict) -> None:
    LAUNCHER_JSON.write_text(json.dumps(data, indent=2), encoding="utf-8")


def port_in_use(host: str, port: int) -> bool:
    """True if something is already listening on host:port.

    Also probes the IPv6 loopback ([::1]) because Nuxt dev binds ::1 by
    default — checking only 127.0.0.1 would miss it.
    """
    candidates = [(host, port)]
    if host not in ("127.0.0.1", "::1"):
        candidates.append(("127.0.0.1", port))
    candidates.append(("::1", port))
    for h, p in candidates:
        family = socket.AF_INET6 if ":" in h else socket.AF_INET
        try:
            with socket.socket(family, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.4)
                if sock.connect_ex((h, p)) == 0:
                    return True
        except OSError:
            continue
    return False
