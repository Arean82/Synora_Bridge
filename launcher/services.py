"""Launcher — managed services (daphne, celery worker, celery beat, nuxt).

Each Service owns one subprocess with a live-log stream, health polling and
status reporting. UI-independent: it communicates through the ``status_changed``
Qt signal and a line queue that the main window drains on a QTimer, so no Qt
widget is ever touched from a worker thread.
"""
from __future__ import annotations

import os
import queue
import re
import subprocess
import threading

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QTextCursor

from launcher.config import VENV_SCRIPTS, kill_process_tree, port_in_use

STATUS_COLORS = {
    "RUNNING": "#22c55e",
    "STARTING": "#f59e0b",
    "STOPPED": "#94a3b8",
    "ERROR": "#ef4444",
}

# Display order + tab labels (must match the .ui tab names).
SERVICE_ORDER = [
    ("daphne", "1. Daphne"),
    ("worker", "2. Celery Worker"),
    ("beat", "3. Celery Beat"),
    ("frontend", "4. Frontend (Nuxt)"),
]

# Strip ANSI color/progress escapes (celery/vite colorize when piped).
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


class Service(QObject):
    """One managed process with a live-log stream."""

    status_changed = Signal(str)

    def __init__(self, app, name, cwd, argv_builder, port=None, health_urls=None, env_extra=None):
        super().__init__()
        self.app = app
        self.name = name
        self.cwd = cwd
        self.argv_builder = argv_builder  # callable() -> list[str]
        self.port = port
        self.health_urls = health_urls or []
        self.env_extra = env_extra or {}  # e.g. PORT/PYTHONUNBUFFERED overrides
        self.proc: subprocess.Popen | None = None
        self.lines: queue.Queue = queue.Queue()
        self.status = "STOPPED"  # STOPPED | RUNNING | STARTING | ERROR
        self._lock = threading.Lock()

    # -- UI wiring (created by the main window) --
    def bind_ui(self, text, start_btn, stop_btn, restart_btn):
        self.text = text          # QPlainTextEdit (main-thread only)
        self.start_btn = start_btn
        self.stop_btn = stop_btn
        self.restart_btn = restart_btn

    # -- state (main thread: set from the queue pump / queued signals) --
    def _set_status(self, status):
        self.status = status
        self.status_changed.emit(status)

    def _append(self, chunk: str):
        # Called from the main-thread pump; safe for QPlainTextEdit.
        chunk = _ANSI.sub("", chunk).replace("\r", "")
        self.text.moveCursor(QTextCursor.MoveOperation.End)
        self.text.insertPlainText(chunk)
        self.text.ensureCursorVisible()

    # -- lifecycle --
    def start(self):
        with self._lock:
            if self.proc and self.proc.poll() is None:
                return
            if self.port and port_in_use(self.port[0], self.port[1]):
                from PySide6.QtWidgets import QMessageBox

                answer = QMessageBox.question(
                    None, f"{self.name} — port busy",
                    f"Something is already listening on {self.port[0]}:{self.port[1]}.\n\n"
                    "This is often a leftover instance. Start anyway?",
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return
            self.text.clear()
            self._set_status("STARTING")
            env = os.environ.copy()
            env["PATH"] = str(VENV_SCRIPTS) + os.pathsep + env.get("PATH", "")
            env.update(self.env_extra)
            argv = self.argv_builder()
            try:
                popen_kwargs = {}
                if os.name == "nt":
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
        # Poll each health URL for up to ~60s; when one answers the service is
        # reported RUNNING (queued signal — safe from this thread). Nuxt binds
        # [::1] by default, so the frontend probes both loopbacks.
        import urllib.request

        if not self.health_urls:
            return
        for _ in range(60):
            if self.proc and self.proc.poll() is not None:
                break
            for url in self.health_urls:
                try:
                    with urllib.request.urlopen(url, timeout=1.5):  # noqa: S310
                        self._set_status("RUNNING")
                        return
                except OSError:
                    pass
            threading.Event().wait(1.0)
        self._set_status("RUNNING")

    def stop(self):
        with self._lock:
            proc = self.proc
            if proc is None or proc.poll() is not None:
                self._set_status("STOPPED")
                return
            self._append("\n[launcher] stopping…\n")
            self.proc = None  # prevent restart races; reader drains leftovers
            kill_process_tree(proc)  # whole tree: node/vite/celery children
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            self._set_status("STOPPED")

    def restart(self):
        self.stop()
        self.start()
