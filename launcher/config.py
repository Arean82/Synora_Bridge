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
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend"
LAUNCHER_DIR = Path(__file__).resolve().parent
UI_DIR = LAUNCHER_DIR / "ui"
STYLE_DIR = LAUNCHER_DIR / "style"

CONFIG_INI = BACKEND_DIR / "config.ini"
LAUNCHER_JSON = LAUNCHER_DIR / "launcher.json"

IS_WINDOWS = os.name == "nt"


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
