"""
Synora Bridge — Stack Launcher
==============================

A small tkinter launcher that runs the whole development stack from one
window (menu bar + 4 tabbed live-log consoles), so you never juggle four
terminals again:

  1. Daphne        (Django ASGI server,  backend)
  2. Celery worker (task runner,         backend)
  3. Celery beat   (scheduler,           backend)
  4. Nuxt dev      (frontend,            frontend)

Menu bar (Flask launcher parity + stack controls):
  File        → Open Server UI, Open Web UI, Change Ports…, Open config.ini, Exit
  Services    → Start All, Stop All, Restart All
  Theme       → Light / Dark (launcher appearance)
  Documentation → README, DEPLOYMENT, SECURITY, LICENSE (in-window reader)
  Help        → About

Usage:
    backend\\.venv\\Scripts\\python.exe scripts\\launcher.py

Notes:
- Services are launched with the venv binaries directly (no Activate.ps1).
- Daphne host/port come from backend/config.ini [Server]; the frontend port
  defaults to 3000 and can be overridden via Change Ports… (persisted in
  scripts/launcher.json; daphne changes are written back to config.ini so the
  backend's auto-restart stays consistent).
- Stopping a service kills its whole process tree (taskkill /T on Windows,
  process-group SIGTERM/SIGKILL on POSIX), so node/vite and celery children
  never leak.
"""
from __future__ import annotations

import configparser
import json
import os
import queue
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

import tkinter as tk
from tkinter import messagebox, ttk

# ---------------------------------------------------------------------------
# Paths / platform
# ---------------------------------------------------------------------------
IS_WINDOWS = os.name == "nt"
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend"
SCRIPTS_DIR = REPO_ROOT / "scripts"
CONFIG_INI = BACKEND_DIR / "config.ini"
LAUNCHER_JSON = SCRIPTS_DIR / "launcher.json"


def _venv_layout() -> tuple[Path, Path]:
    """(python executable, scripts/bin dir) for the venv on this platform."""
    if IS_WINDOWS:
        return BACKEND_DIR / ".venv" / "Scripts" / "python.exe", BACKEND_DIR / ".venv" / "Scripts"
    return BACKEND_DIR / ".venv" / "bin" / "python", BACKEND_DIR / ".venv" / "bin"


VENV_PYTHON, VENV_SCRIPTS = _venv_layout()


def _npm_argv(*args) -> list[str]:
    """npm on Windows is a .cmd shim — spawn through cmd.exe so it resolves;
    on POSIX call npm directly. The whole tree is killed via process group."""
    if IS_WINDOWS:
        return [os.environ.get("COMSPEC", "cmd.exe"), "/c"] + list(args)
    return list(args)


def _kill_process_tree(proc: subprocess.Popen) -> None:
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


def _open_file_default(path: Path) -> None:
    """Open a file with the OS default application."""
    if IS_WINDOWS:
        os.startfile(path)  # noqa: S606
    else:
        opener = shutil.which("xdg-open") or shutil.which("open")
        if opener:
            subprocess.Popen([opener, str(path)])  # noqa: S603

APP_TITLE = "Synora Bridge — Stack Launcher"
APP_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Palette (Light / Dark)
# ---------------------------------------------------------------------------
PALETTES = {
    "light": {
        "bg": "#f5f5f5", "panel": "#ffffff", "text": "#1f2937",
        "console_bg": "#ffffff", "console_fg": "#1f2937",
        "active": "#2563eb", "muted": "#9ca3af",
    },
    "dark": {
        "bg": "#111827", "panel": "#1f2937", "text": "#e5e7eb",
        "console_bg": "#0b0f19", "console_fg": "#4ade80",
        "active": "#60a5fa", "muted": "#6b7280",
    },
}


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
class Service:
    """One managed process with a live-log tab."""

    def __init__(self, app, name, cwd, argv_builder, port=None, health_urls=None):
        self.app = app
        self.name = name
        self.cwd = cwd
        self.argv_builder = argv_builder  # callable() -> list[str]
        self.port = port
        self.health_urls = health_urls or []
        self.proc: subprocess.Popen | None = None
        self.lines: queue.Queue = queue.Queue()
        self.status = "STOPPED"  # STOPPED | RUNNING | STARTING | ERROR
        self._lock = threading.Lock()
        self._port_gate = threading.Event()  # set once the port answers

    # -- UI wiring (created by the app) --
    def bind_tab(self, tab, status_lbl, text, start_btn, stop_btn, restart_btn):
        self.tab = tab
        self.status_lbl = status_lbl
        self.text = text
        self.start_btn = start_btn
        self.stop_btn = stop_btn
        self.restart_btn = restart_btn

    # -- state helpers (main thread only) --
    def _set_status(self, status):
        self.status = status
        self.app.update_service_ui(self)

    def _append(self, chunk: str):
        # Strip ANSI color/progress escapes (celery/vite colorize when piped)
        # and stray carriage returns so the log tab stays readable.
        chunk = re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]", "", chunk).replace("\r", "")
        self.text.insert("end", chunk)
        self.text.see("end")

    # -- lifecycle --
    def start(self):
        with self._lock:
            if self.proc and self.proc.poll() is None:
                return
            if self.port and port_in_use(self.port[0], self.port[1]) and not self.app.force_ports:
                answer = messagebox.askyesno(
                    f"{self.name} — port busy",
                    f"Something is already listening on {self.port[0]}:{self.port[1]}.\n\n"
                    "This is often a leftover instance. Start anyway?",
                )
                if not answer:
                    return
            self.text.delete("1.0", "end")
            self._set_status("STARTING")
            env = os.environ.copy()
            env["PATH"] = str(VENV_SCRIPTS) + os.pathsep + env.get("PATH", "")
            argv = self.argv_builder()
            try:
                popen_kwargs = {}
                if IS_WINDOWS:
                    popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                else:
                    popen_kwargs["start_new_session"] = True  # own process group for killpg
                self.proc = subprocess.Popen(
                    argv,
                    cwd=str(self.cwd),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    # Decode as UTF-8 with replacement so ANSI/UTF-8 bytes from
                    # daphne/celery/vite never crash the reader thread (the
                    # default locale codec — cp1252 on Windows — raises).
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    **popen_kwargs,
                )
            except OSError as exc:
                self._append(f"[launcher] failed to start {self.name}: {exc}\n")
                self._set_status("ERROR")
                return
            self._append(f"[launcher] starting: {' '.join(argv)}\n")
            threading.Thread(target=self._reader, daemon=True).start()
            self._set_status("RUNNING")
            if self.health_urls:
                threading.Thread(target=self._health, daemon=True).start()

    def _reader(self):
        proc = self.proc
        stream = proc.stdout if proc else None
        if stream is None:
            return
        for chunk in iter(stream.readline, ""):
            self.lines.put(chunk)
        self.lines.put(None)  # EOF sentinel

    def _health(self):
        # Poll each health URL for up to ~30s; when one answers, the service
        # is reported RUNNING on the main thread. Nuxt binds [::1] by default,
        # so the frontend probes both loopbacks.
        import urllib.request

        if not self.health_urls:
            return
        for _ in range(30):
            if self.proc and self.proc.poll() is not None:
                break
            for url in self.health_urls:
                try:
                    with urllib.request.urlopen(url, timeout=1.5):  # noqa: S310
                        self.app.after(0, lambda: self._set_status("RUNNING"))
                        return
                except OSError:
                    pass
            threading.Event().wait(1.0)
        self.app.after(0, lambda: self._set_status("RUNNING"))

    def stop(self):
        with self._lock:
            proc = self.proc
            if proc is None or proc.poll() is not None:
                self._set_status("STOPPED")
                return
            self._append("\n[launcher] stopping…\n")
            self.proc = None  # prevent restart races; reader drains leftovers
            # Kill the whole process tree (node/vite/celery children).
            _kill_process_tree(proc)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            self._set_status("STOPPED")

    def restart(self):
        self.stop()
        self.start()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
class LauncherApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1000x680")
        self.minsize(760, 480)

        self.theme = "light"
        self.force_ports = False
        self.services: dict[str, Service] = {}
        self._build_config()

        self._build_menu()
        self._build_statusbar()  # before tabs: update_service_ui() refreshes it
        self._build_console()
        self.apply_theme()

        self.after(120, self._pump_all)  # drain service queues

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ config
    def _build_config(self):
        cfg = read_ini(CONFIG_INI) if CONFIG_INI.exists() else {}
        server = cfg.get("Server", {})
        launcher = load_launcher_json()

        self.daphne_host = server.get("host", "127.0.0.1")
        try:
            self.daphne_port = int(server.get("port", "8000"))
        except ValueError:
            self.daphne_port = 8000
        try:
            self.frontend_port = int(launcher.get("frontend_port", 3000))
        except (TypeError, ValueError):
            self.frontend_port = 3000

        self.venv_ok = VENV_PYTHON.exists()
        if not self.venv_ok:
            self.venv_ok = shutil.which("python") is not None

    def _npm(self, *args):
        # npm is a .cmd shim on Windows (needs cmd.exe); direct on POSIX.
        # The whole tree is killed via process group on stop.
        return _npm_argv(*args)

    def _service_args(self):
        venv = str(VENV_PYTHON if VENV_PYTHON.exists() else sys.executable)
        return {
            "daphne": [venv, "-m", "daphne", "-b", self.daphne_host, "-p", str(self.daphne_port),
                       "config.asgi:application"],
            "worker": [venv, "-m", "celery", "-A", "config.celery", "worker",
                       "--pool=solo", "--concurrency=1", "-l", "info"],
            "beat": [venv, "-m", "celery", "-A", "config.celery", "beat", "-l", "info"],
            "frontend": self._npm("npm", "run", "dev", "--", "--port", str(self.frontend_port)),
        }

    def _make_services(self):
        args = self._service_args()

        def spec(name, cwd, argv, port=None, health_urls=None):
            return Service(self, name, cwd, lambda argv=argv: argv,
                           port=port, health_urls=health_urls)

        self.services = {
            "daphne": spec("Daphne (ASGI)", BACKEND_DIR, args["daphne"],
                           port=(self.daphne_host, self.daphne_port),
                           health_urls=[f"http://{self.daphne_host}:{self.daphne_port}/api/v1/"]),
            "worker": spec("Celery Worker", BACKEND_DIR, args["worker"]),
            "beat": spec("Celery Beat", BACKEND_DIR, args["beat"]),
            # Nuxt dev binds [::1] by default — probe both loopbacks.
            "frontend": spec("Nuxt (Frontend)", FRONTEND_DIR, args["frontend"],
                             port=("127.0.0.1", self.frontend_port),
                             health_urls=[
                                 f"http://127.0.0.1:{self.frontend_port}/",
                                 f"http://[::1]:{self.frontend_port}/",
                             ]),
        }

    # ------------------------------------------------------------------- menu
    def _build_menu(self):
        menubar = tk.Menu(self)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="  Open Server UI (daphne)",
                              command=lambda: webbrowser.open(f"http://{self.daphne_host}:{self.daphne_port}"))
        file_menu.add_command(label="  Open Web UI (frontend)",
                              command=lambda: webbrowser.open(f"http://localhost:{self.frontend_port}"))
        file_menu.add_separator()
        file_menu.add_command(label="  Change Ports…", command=self._ports_dialog)
        file_menu.add_command(label="  Open config.ini", command=self._open_config)
        file_menu.add_separator()
        file_menu.add_command(label="  Exit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        services_menu = tk.Menu(menubar, tearoff=0)
        services_menu.add_command(label="  Start All", command=self.start_all)
        services_menu.add_command(label="  Stop All", command=self.stop_all)
        services_menu.add_command(label="  Restart All", command=self.restart_all)
        menubar.add_cascade(label="Services", menu=services_menu)

        theme_menu = tk.Menu(menubar, tearoff=0)
        theme_menu.add_command(label="  ☀️ Light Mode", command=lambda: self._set_theme("light"))
        theme_menu.add_command(label="  🌙 Dark Mode", command=lambda: self._set_theme("dark"))
        menubar.add_cascade(label="Theme", menu=theme_menu)

        docs_menu = tk.Menu(menubar, tearoff=0)
        for doc in ("README.md", "docs/DEPLOYMENT.md", "docs/SECURITY.md", "LICENSE"):
            docs_menu.add_command(label=f"  {Path(doc).name}",
                                  command=lambda d=doc: self._show_doc(d))
        menubar.add_cascade(label="Documentation", menu=docs_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="  About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.config(menu=menubar)

    # ---------------------------------------------------------------- console
    def _build_console(self):
        self._make_services()

        container = tk.Frame(self, padx=8, pady=8)
        container.pack(fill="both", expand=True)

        self.notebook = ttk.Notebook(container)
        self.notebook.pack(fill="both", expand=True)

        order = [
            ("daphne", "1. Daphne"),
            ("worker", "2. Celery Worker"),
            ("beat", "3. Celery Beat"),
            ("frontend", "4. Frontend (Nuxt)"),
        ]
        for key, label in order:
            self._build_tab(key, label)

    def _build_tab(self, key, label):
        service = self.services[key]
        tab = tk.Frame(self.notebook)
        self.notebook.add(tab, text=label)

        controls = tk.Frame(tab)
        controls.pack(fill="x", padx=6, pady=(6, 2))

        self._status_dots = getattr(self, "_status_dots", {})
        dot = tk.Label(controls, text="●", font=("Segoe UI", 11))
        dot.pack(side="left")
        self._status_dots[key] = dot

        status_lbl = tk.Label(controls, text=service.status, font=("Segoe UI", 9))
        status_lbl.pack(side="left", padx=(4, 12))
        service.status_lbl = status_lbl

        start_btn = tk.Button(controls, text="Start", width=8, command=service.start)
        start_btn.pack(side="right", padx=2)
        stop_btn = tk.Button(controls, text="Stop", width=8, command=service.stop)
        stop_btn.pack(side="right", padx=2)
        restart_btn = tk.Button(controls, text="Restart", width=8, command=service.restart)
        restart_btn.pack(side="right", padx=2)
        clear_btn = tk.Button(controls, text="Clear", width=7,
                              command=lambda t=tab: self._clear_tab(t))
        clear_btn.pack(side="right", padx=2)

        body = tk.Frame(tab)
        body.pack(fill="both", expand=True, padx=6, pady=6)

        text = tk.Text(body, wrap="none", font=("Consolas", 9), state="normal",
                       undo=False, borderwidth=0, highlightthickness=0)
        scroll_y = ttk.Scrollbar(body, orient="vertical", command=text.yview)
        scroll_x = ttk.Scrollbar(body, orient="horizontal", command=text.xview)
        text.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        scroll_y.pack(side="right", fill="y")
        scroll_x.pack(side="bottom", fill="x")
        text.pack(side="left", fill="both", expand=True)

        service.bind_tab(tab, status_lbl, text, start_btn, stop_btn, restart_btn)
        self.update_service_ui(service)

    def _clear_tab(self, tab):
        for service in self.services.values():
            if service.tab is tab:
                service.text.delete("1.0", "end")
                return

    # -------------------------------------------------------------- statusbar
    def _build_statusbar(self):
        self.statusbar = tk.Label(self, text="", anchor="w", font=("Segoe UI", 9))
        self.statusbar.pack(fill="x", side="bottom")

    def update_service_ui(self, service):
        colors = {
            "RUNNING": "#22c55e",
            "STARTING": "#f59e0b",
            "STOPPED": "#9ca3af",
            "ERROR": "#ef4444",
        }
        dot = self._status_dots.get(next((k for k, s in self.services.items() if s is service), ""))
        if dot:
            dot.configure(fg=colors.get(service.status, "#9ca3af"))
        service.status_lbl.configure(text=service.status)
        self._refresh_statusbar()

    def _refresh_statusbar(self):
        parts = []
        for key, service in self.services.items():
            suffix = ""
            if service.port and service.status == "RUNNING":
                suffix = f" :{service.port[1]}"
            parts.append(f"{key.title()}: {service.status}{suffix}")
        self.statusbar.configure(text="   " + "   •   ".join(parts))

    # ---------------------------------------------------------------- pumping
    def _pump_all(self):
        for service in self.services.values():
            try:
                while True:
                    chunk = service.lines.get_nowait()
                    if chunk is None:
                        # Process exited — show an explicit marker.
                        service._append("\n[launcher] process exited.\n")
                        service._set_status("STOPPED")
                        continue
                    service._append(chunk)
            except queue.Empty:
                pass
        self.after(120, self._pump_all)

    # --------------------------------------------------------------- actions
    def start_all(self):
        for key in ("daphne", "worker", "beat", "frontend"):
            self.services[key].start()

    def stop_all(self):
        for service in self.services.values():
            service.stop()

    def restart_all(self):
        self.stop_all()
        self.start_all()

    def _open_config(self):
        if CONFIG_INI.exists():
            _open_file_default(CONFIG_INI)
        else:
            messagebox.showerror(APP_TITLE, f"{CONFIG_INI} not found.")

    def _ports_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("Change Ports")
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry("+%d+%d" % (self.winfo_rootx() + 60, self.winfo_rooty() + 60))

        tk.Label(dialog, text="Daphne (backend) host:").grid(row=0, column=0, sticky="w", padx=10, pady=6)
        host_var = tk.StringVar(value=self.daphne_host)
        tk.Entry(dialog, textvariable=host_var, width=28).grid(row=0, column=1, padx=10, pady=6)

        tk.Label(dialog, text="Daphne (backend) port:").grid(row=1, column=0, sticky="w", padx=10, pady=6)
        port_var = tk.StringVar(value=str(self.daphne_port))
        tk.Entry(dialog, textvariable=port_var, width=28).grid(row=1, column=1, padx=10, pady=6)

        tk.Label(dialog, text="Frontend (Nuxt) port:").grid(row=2, column=0, sticky="w", padx=10, pady=6)
        fe_port_var = tk.StringVar(value=str(self.frontend_port))
        tk.Entry(dialog, textvariable=fe_port_var, width=28).grid(row=2, column=1, padx=10, pady=6)

        note = tk.Label(
            dialog,
            text="Daphne host/port are saved to backend/config.ini [Server]\n"
                 "(the backend auto-restart rebinds to these). Frontend port is\n"
                 "a launcher setting passed to `nuxt dev --port`.",
            justify="left", font=("Segoe UI", 8),
        )
        note.grid(row=3, column=0, columnspan=2, padx=10, pady=4, sticky="w")

        def save():
            try:
                new_port = int(port_var.get())
                new_fe_port = int(fe_port_var.get())
            except ValueError:
                messagebox.showerror("Change Ports", "Ports must be integers.", parent=dialog)
                return
            if not (1 <= new_port <= 65535) or not (1 <= new_fe_port <= 65535):
                messagebox.showerror("Change Ports", "Ports must be between 1 and 65535.", parent=dialog)
                return
            host = host_var.get().strip() or "127.0.0.1"
            # Stop the OLD services first so nothing keeps running on the old
            # ports and no orphan processes leak after the rebuild.
            self.stop_all()
            if CONFIG_INI.exists():
                set_ini_value(CONFIG_INI, "Server", "host", host)
                set_ini_value(CONFIG_INI, "Server", "port", str(new_port))
            save_launcher_json({"frontend_port": new_fe_port})
            self.daphne_host = host
            self.daphne_port = new_port
            self.frontend_port = new_fe_port
            self._rebuild_tabs()  # re-creates services with the new ports
            messagebox.showinfo("Change Ports", "Ports updated. Start the services to apply.", parent=dialog)
            dialog.destroy()

        def apply_and_restart():
            save()
            self.start_all()

        buttons = tk.Frame(dialog)
        buttons.grid(row=4, column=0, columnspan=2, pady=10)
        tk.Button(buttons, text="Save", width=10, command=save).pack(side="left", padx=4)
        tk.Button(buttons, text="Save & Restart All", width=16, command=apply_and_restart).pack(side="left", padx=4)
        tk.Button(buttons, text="Cancel", width=10, command=dialog.destroy).pack(side="left", padx=4)

    def _rebuild_tabs(self):
        # Rebuild the notebook (services were re-created with new ports).
        self.notebook.destroy()
        self._status_dots = {}
        self._build_console()

    def _show_doc(self, rel_path):
        target = REPO_ROOT / rel_path
        if not target.exists():
            messagebox.showerror(APP_TITLE, f"{rel_path} not found.")
            return
        reader = tk.Toplevel(self)
        reader.title(f"Synora Bridge — {Path(rel_path).name}")
        reader.geometry("760x560")
        text = tk.Text(reader, wrap="word", font=("Segoe UI", 10),
                       bg=PALETTES[self.theme]["panel"], fg=PALETTES[self.theme]["text"],
                       padx=16, pady=16, borderwidth=0, highlightthickness=0)
        scroll = ttk.Scrollbar(reader, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        text.pack(fill="both", expand=True)
        try:
            text.insert("1.0", target.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as exc:
            text.insert("1.0", f"[launcher] could not read {rel_path}: {exc}")
        text.configure(state="disabled")

    def _show_about(self):
        messagebox.showinfo(
            APP_TITLE,
            f"Synora Bridge — Stack Launcher v{APP_VERSION}\n\n"
            "Manages daphne, celery worker, celery beat and the Nuxt frontend\n"
            "from one window. Start each service from its tab, or use\n"
            "Services → Start All.\n\n"
            f"Backend: {CONFIG_INI.parent} (config.ini)\n"
            f"Frontend: {FRONTEND_DIR}",
        )

    # ---------------------------------------------------------------- theme
    def _set_theme(self, theme):
        self.theme = theme
        self.apply_theme()

    def apply_theme(self):
        p = PALETTES[self.theme]
        self.configure(bg=p["bg"])
        for key, service in self.services.items():
            service.text.configure(bg=p["console_bg"], fg=p["console_fg"])
            dot = self._status_dots.get(key)
            if dot:
                dot.configure(bg=p["bg"])
        self.statusbar.configure(bg=p["panel"], fg=p["text"])

    # ---------------------------------------------------------------- close
    def _on_close(self):
        self.stop_all()
        self.destroy()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    if not CONFIG_INI.exists():
        messagebox.showwarning(
            APP_TITLE,
            f"{CONFIG_INI} not found.\n\nRun setup first:\n"
            "  python scripts/setup_db.py\nor\n  python scripts/initialize_system.py",
        )
        return

    if not VENV_PYTHON.exists():
        messagebox.showwarning(
            APP_TITLE,
            f"{VENV_PYTHON} not found.\n\nCreate the virtual environment first:\n"
            "  python -m venv backend\\.venv\n"
            "  backend\\.venv\\Scripts\\pip install -r backend\\requirements.txt",
        )
        return

    app = LauncherApp()
    app.mainloop()


if __name__ == "__main__":
    main()
