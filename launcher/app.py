"""Launcher — main window controller.

Loads the Qt Designer layout (launcher/ui/main_window.ui) at runtime via
QUiLoader, wires the Service layer (launcher/services.py) to the widgets, and
applies the QSS look (launcher/style/{light,dark}.qss). Open the .ui in Qt
Designer (``pyside6-designer launcher\\ui\\main_window.ui``) to redesign the
layout visually — no code changes needed for pure look/layout edits.
"""
from __future__ import annotations

import os
import queue
import shutil
import sys
import webbrowser
from pathlib import Path
from typing import TypeVar, cast

from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)
from qt_material import apply_stylesheet  # import AFTER PySide6 (qt-material requirement)

from launcher import config as C
from launcher.build_info import APP_NAME, APP_VERSION, EXE_NAME
from launcher.services import SERVICE_ORDER, Service, STATUS_COLORS

APP_TITLE = f"{APP_NAME} — Stack Launcher"

# qt-material accents available in both light and dark (from list_themes()).
ACCENTS = ["amber", "blue", "cyan", "lightgreen", "pink", "purple", "red", "teal", "yellow"]
DEFAULT_ACCENT = "blue"


def _system_dark() -> bool:
    """OS-level dark mode (darkdetect: Windows/macOS/Linux)."""
    try:
        import darkdetect

        return bool(darkdetect.isDark())
    except Exception:  # noqa: BLE001 — default to light on any failure
        return False

_W = TypeVar("_W")


def _find(widget, klass: type[_W], name: str) -> _W:
    """findChild that fails loudly when the .ui is missing a widget."""
    found = widget.findChild(klass, name)
    if found is None:
        raise RuntimeError(f"main_window.ui is missing widget: {name}")
    return cast(_W, found)


class LauncherApp:
    """Controller for the Qt Designer main window."""

    def __init__(self):
        loader = QUiLoader()
        self.window = loader.load(str(C.UI_DIR / "main_window.ui"))
        if self.window is None:
            raise RuntimeError(f"failed to load {C.UI_DIR / 'main_window.ui'}")

        self.theme_mode = "auto"  # light | dark | auto (follow the OS)
        self.theme_accent = DEFAULT_ACCENT
        self.resolved_theme = "light"
        self.accent_actions: dict[tuple[str, str], QAction] = {}
        self.services: dict[str, Service] = {}
        self._find_widgets()
        self._build_config()
        self._make_services()
        self._build_menubar()  # menubar is native Python — not in the .ui
        self._wire()
        self._apply_theme()
        self._sync_auto_follow()

        self.timer = QTimer(self.window)
        self.timer.timeout.connect(self._pump_all)
        self.timer.start(120)

    # ------------------------------------------------------------------ show
    def show(self):
        self.window.show()

    # ---------------------------------------------------------------- widgets
    def _find_widgets(self):
        win = cast(QMainWindow, self.window)
        self.status_label = QLabel("")
        win.statusBar().addWidget(self.status_label, 1)

        # Actions/menus are built in code (_build_menubar) — the .ui holds only
        # the layout, so adding a menu item is a single-place change.
        self.actions: dict[str, QAction] = {}

        self.tab_widgets: dict[str, dict] = {}
        for key, _label in SERVICE_ORDER:
            cap = key.capitalize()
            self.tab_widgets[key] = {
                "dot": _find(win, QLabel, f"dot{cap}"),
                "status": _find(win, QLabel, f"status{cap}"),
                "console": _find(win, QPlainTextEdit, f"console{cap}"),
                "start": _find(win, QPushButton, f"btnStart{cap}"),
                "stop": _find(win, QPushButton, f"btnStop{cap}"),
                "restart": _find(win, QPushButton, f"btnRestart{cap}"),
                "clear": _find(win, QPushButton, f"btnClear{cap}"),
            }

    # ------------------------------------------------------------------ config
    def _build_config(self):
        cfg = C.read_ini(C.CONFIG_INI) if C.CONFIG_INI.exists() else {}
        server = cfg.get("Server", {})
        launcher = C.load_launcher_json()

        self.daphne_host = server.get("host", "127.0.0.1")
        try:
            self.daphne_port = int(server.get("port", "8000"))
        except ValueError:
            self.daphne_port = 8000
        try:
            self.frontend_port = int(launcher.get("frontend_port", 3000))
        except (TypeError, ValueError):
            self.frontend_port = 3000

        # Persistent launcher preferences: theme mode + Material accent.
        mode = launcher.get("theme_mode", "auto")
        accent = launcher.get("theme_accent", DEFAULT_ACCENT)
        if mode in ("light", "dark", "auto"):
            self.theme_mode = mode
        if accent in ACCENTS:
            self.theme_accent = accent

    def _service_args(self):
        """Production-grade service invocations.

        - Daphne: binds the configured host/port and passes ``--proxy-headers``
          when [ReverseProxy] enabled (nginx in front), so X-Forwarded-For /
          X-Forwarded-Proto are parsed (SECURE_PROXY_SSL_HEADER trusts them).
        - Celery worker: Windows must use --pool=solo --concurrency=1 (prefork
          is broken there); on POSIX the default prefork pool with the
          configured [CELERY] worker_concurrency.
        - Python services run with PYTHONUNBUFFERED=1 so logs stream live to
          the console (no buffering when piped).
        - Frontend: serves the production build (frontend/.output) with node
          when present, else falls back to `npm run dev`.
        """
        venv = str(C.VENV_PYTHON if C.VENV_PYTHON.exists() else sys.executable)
        cfg = C.read_ini(C.CONFIG_INI) if C.CONFIG_INI.exists() else {}

        proxy_enabled = str(cfg.get("ReverseProxy", {}).get("enabled", "false")).lower() == "true"
        try:
            concurrency = int(cfg.get("CELERY", {}).get("worker_concurrency", "4"))
        except (TypeError, ValueError):
            concurrency = 4
        concurrency = max(1, concurrency)

        py_env = {"PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}

        # Frozen all-in-one: services re-invoke the exe via --service (the
        # whole stack is bundled). Dev: run the repo venv's python -m.
        daphne = C.service_argv("daphne", "-b", self.daphne_host, "-p", str(self.daphne_port))
        if proxy_enabled:
            daphne.append("--proxy-headers")
        daphne.append("config.asgi:application")

        if os.name == "nt":
            worker = C.service_argv("worker") + ["--pool=solo", "--concurrency=1", "--loglevel=info"]
        else:
            worker = C.service_argv("worker") + ["--concurrency", str(concurrency), "--loglevel=info"]
        beat = C.service_argv("beat") + ["--loglevel=info"]

        frontend_argv, frontend_env = self._frontend_argv()

        return {
            "daphne": (daphne, py_env),
            "worker": (worker, py_env),
            "beat": (beat, py_env),
            "frontend": (frontend_argv, frontend_env),
        }

    def _node_path(self) -> str:
        """Node executable: a bundled runtime (runtime/node, shipped by the
        all-in-one build) wins over the system PATH."""
        bundled = C.RUNTIME_DIR / "node" / ("node.exe" if os.name == "nt" else "node")
        if bundled.exists():
            return str(bundled)
        return shutil.which("node") or "node"

    def _frontend_argv(self):
        """(argv, env) for the frontend: production build if present, else dev."""
        prod_server = C.FRONTEND_DIR / ".output" / "server" / "index.mjs"
        if prod_server.exists():
            return (
                [self._node_path(), str(prod_server)],
                {"PORT": str(self.frontend_port), "HOST": self.daphne_host or "127.0.0.1"},
            )
        return (C.npm_argv("npm", "run", "dev", "--", "--port", str(self.frontend_port)), {})

    def _make_services(self):
        args = self._service_args()

        def spec(name, cwd, argv, env_extra, port=None, health_urls=None):
            return Service(self, name, cwd, lambda argv=argv: argv,
                           port=port, health_urls=health_urls, env_extra=env_extra)

        self.services = {
            "daphne": spec("Daphne (ASGI)", C.BACKEND_DIR, args["daphne"][0], args["daphne"][1],
                           port=(self.daphne_host, self.daphne_port),
                           health_urls=[f"http://{self.daphne_host}:{self.daphne_port}/api/v1/"]),
            "worker": spec("Celery Worker", C.BACKEND_DIR, args["worker"][0], args["worker"][1]),
            "beat": spec("Celery Beat", C.BACKEND_DIR, args["beat"][0], args["beat"][1]),
            # Nuxt dev binds [::1] by default — probe both loopbacks.
            "frontend": spec("Nuxt (Frontend)", C.FRONTEND_DIR, args["frontend"][0], args["frontend"][1],
                             port=("127.0.0.1", self.frontend_port),
                             health_urls=[
                                 f"http://127.0.0.1:{self.frontend_port}/",
                                 f"http://[::1]:{self.frontend_port}/",
                             ]),
        }
        for key, service in self.services.items():
            w = self.tab_widgets[key]
            service.bind_ui(w["console"], w["start"], w["stop"], w["restart"])
            service.status_changed.connect(lambda _s, svc=service: self.update_service_ui(svc))

    # ------------------------------------------------------------------- wire
    def _wire(self):
        """Connect toolbar buttons (once) + per-service widgets (rebuild-safe)."""
        self._wire_actions()
        self._wire_services()

    def _build_menubar(self):
        """The whole menubar is built here (not in the .ui) — adding a menu
        item is a one-place change and QUiLoader menu quirks are avoided."""
        bar = QMenuBar(self.window)

        def add(parent, name, text):
            action = QAction(text, self.window)
            self.actions[name] = action
            parent.addAction(action)
            return action

        # File
        m_file = bar.addMenu("File")
        add(m_file, "actionOpenServerUI", "Open Server UI (daphne)")
        add(m_file, "actionOpenWebUI", "Open Web UI (frontend)")
        m_file.addSeparator()
        add(m_file, "actionChangePorts", "Change Ports…")
        add(m_file, "actionOpenConfig", "Open config.ini")
        m_file.addSeparator()
        exit_action = add(m_file, "actionExit", "Exit")
        exit_action.setShortcut("Ctrl+Q")

        # Services
        m_services = bar.addMenu("Services")
        add(m_services, "actionStartAll", "Start All")
        add(m_services, "actionStopAll", "Stop All")
        add(m_services, "actionRestartAll", "Restart All")

        # Theme: checkable modes + Material accent submenu (checkmark on active)
        m_theme = bar.addMenu("Theme")
        for name, mode, label in (
            ("actionLight", "light", "☀️ Light Mode"),
            ("actionDark", "dark", "🌙 Dark Mode"),
            ("actionAuto", "auto", "🖥️ Auto (System)"),
        ):
            action = add(m_theme, name, label)
            action.setCheckable(True)
            action.triggered.connect(lambda _c=False, m=mode: self._set_mode(m))
        m_theme.addSeparator()
        material_menu = m_theme.addMenu("Material")
        self.accent_actions = {}
        for sub_label, mode_key in (("Dark", "dark"), ("Light", "light")):
            sub = material_menu.addMenu(sub_label)
            for accent in ACCENTS:
                action = QAction(f"{accent.capitalize()}", sub)
                action.setCheckable(True)
                action.triggered.connect(lambda _c=False, a=accent: self._set_accent(a))
                sub.addAction(action)
                self.accent_actions[(mode_key, accent)] = action

        # Documentation
        m_docs = bar.addMenu("Documentation")
        for doc, name in (("README.md", "actionDocReadme"),
                          ("docs/INSTALLATION_MANUAL.md", "actionDocManual"),
                          ("docs/ARCHITECTURE.md", "actionDocArch"),
                          ("docs/DEPLOYMENT.md", "actionDocDeploy"),
                          ("docs/SECURITY.md", "actionDocSecurity"),
                          ("LICENSE", "actionDocLicense")):
            action = add(m_docs, name, Path(doc).name)
            action.triggered.connect(lambda _c=False, d=doc: self._show_doc(d))

        # Help
        m_help = bar.addMenu("Help")
        add(m_help, "actionAbout", "About").triggered.connect(self._show_about)

        cast(QMainWindow, self.window).setMenuBar(bar)
        self._refresh_theme_checks()

    def _wire_actions(self):
        a = self.actions
        a["actionOpenServerUI"].triggered.connect(
            lambda: webbrowser.open(f"http://{self.daphne_host}:{self.daphne_port}"))
        a["actionOpenWebUI"].triggered.connect(
            lambda: webbrowser.open(f"http://localhost:{self.frontend_port}"))
        a["actionChangePorts"].triggered.connect(self._ports_dialog)
        a["actionOpenConfig"].triggered.connect(self._open_config)
        a["actionExit"].triggered.connect(self.window.close)
        a["actionStartAll"].triggered.connect(self.start_all)
        a["actionStopAll"].triggered.connect(self.stop_all)
        a["actionRestartAll"].triggered.connect(self.restart_all)

        for name, role in (("btnStartAll", "start"), ("btnStopAll", "stop"), ("btnRestartAll", "restart")):
            btn = _find(self.window, QPushButton, name)
            if role == "start":
                btn.clicked.connect(self.start_all)
            elif role == "stop":
                btn.clicked.connect(self.stop_all)
            else:
                btn.clicked.connect(self.restart_all)

    def _wire_services(self):
        for key, service in self.services.items():
            w = self.tab_widgets[key]
            w["start"].clicked.connect(service.start)
            w["stop"].clicked.connect(service.stop)
            w["restart"].clicked.connect(service.restart)
            # clicked() emits a `checked` bool — capture it so the key is not
            # overwritten by the signal argument.
            w["clear"].clicked.connect(lambda _checked=False, _k=key: self._clear_console(_k))

    # ------------------------------------------------------------------ state
    def update_service_ui(self, service):
        color = STATUS_COLORS.get(service.status, STATUS_COLORS["STOPPED"])
        key = next((k for k, s in self.services.items() if s is service), None)
        if key:
            self.tab_widgets[key]["dot"].setStyleSheet(f"color: {color}; font-size: 15px;")
            self.tab_widgets[key]["status"].setText(service.status)
        self._refresh_statusbar()

    def _refresh_statusbar(self):
        parts = []
        for key, service in self.services.items():
            suffix = f" :{service.port[1]}" if (service.port and service.status == "RUNNING") else ""
            parts.append(f"{key.title()}: {service.status}{suffix}")
        self.status_label.setText("   " + "   •   ".join(parts))

    def _pump_all(self):
        for service in self.services.values():
            try:
                while True:
                    chunk = service.lines.get_nowait()
                    if chunk is None:
                        service._append("\n[launcher] process exited.\n")
                        service._set_status("STOPPED")
                        continue
                    service._append(chunk)
            except queue.Empty:
                pass  # drained — next tick continues

    # --------------------------------------------------------------- actions
    def start_all(self):
        for key, _ in SERVICE_ORDER:
            self.services[key].start()

    def stop_all(self):
        for service in self.services.values():
            service.stop()

    def restart_all(self):
        self.stop_all()
        self.start_all()

    def _clear_console(self, key):
        self.tab_widgets[key]["console"].clear()

    def _open_config(self):
        if C.CONFIG_INI.exists():
            C.open_file_default(C.CONFIG_INI)
        else:
            QMessageBox.warning(self.window, APP_TITLE, f"{C.CONFIG_INI} not found.")

    # ---------------------------------------------------------------- dialogs
    def _ports_dialog(self):
        dialog = QDialog(self.window)
        dialog.setWindowTitle("Change Ports")
        form = QFormLayout(dialog)

        host = QLineEdit(self.daphne_host)
        port = QLineEdit(str(self.daphne_port))
        fe_port = QLineEdit(str(self.frontend_port))
        form.addRow("Daphne (backend) host:", host)
        form.addRow("Daphne (backend) port:", port)
        form.addRow("Frontend (Nuxt) port:", fe_port)

        note = QLabel("Daphne host/port are saved to backend/config.ini [Server]\n"
                      "(the backend auto-restart rebinds to these). Frontend port is\n"
                      "a launcher setting passed to `nuxt dev --port`.")
        note.setWordWrap(True)
        form.addRow(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        save_restart = buttons.addButton("Save && Restart All", QDialogButtonBox.ButtonRole.ActionRole)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            new_port = int(port.text())
            new_fe_port = int(fe_port.text())
        except ValueError:
            QMessageBox.warning(dialog, "Change Ports", "Ports must be integers.")
            return
        if not (1 <= new_port <= 65535) or not (1 <= new_fe_port <= 65535):
            QMessageBox.warning(dialog, "Change Ports", "Ports must be between 1 and 65535.")
            return

        new_host = host.text().strip() or "127.0.0.1"
        self.stop_all()
        if C.CONFIG_INI.exists():
            C.set_ini_value(C.CONFIG_INI, "Server", "host", new_host)
            C.set_ini_value(C.CONFIG_INI, "Server", "port", str(new_port))
        prefs = C.load_launcher_json()  # merge — keep theme prefs
        prefs["frontend_port"] = new_fe_port
        C.save_launcher_json(prefs)
        self.daphne_host = new_host
        self.daphne_port = new_port
        self.frontend_port = new_fe_port
        self._make_services()
        self._wire_services()  # actions stay wired once; re-wire only the new services
        QMessageBox.information(dialog, "Change Ports", "Ports updated. Start the services to apply.")

    def _show_doc(self, rel_path):
        target = C.REPO_ROOT / rel_path
        if not target.exists():
            QMessageBox.warning(self.window, APP_TITLE, f"{rel_path} not found.")
            return
        reader = QDialog(self.window)
        reader.setWindowTitle(f"Synora Bridge — {Path(rel_path).name}")
        reader.resize(860, 620)
        layout = QVBoxLayout(reader)
        # QTextBrowser renders the converted HTML (Python-Markdown + pygments —
        # same compiler the reference md_converter uses); links open externally.
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.document().setDocumentMargin(12)
        layout.addWidget(browser)
        try:
            content = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            content = f"[launcher] could not read {rel_path}: {exc}"
        if target.suffix.lower() == ".md":
            browser.setHtml(self._render_markdown(content))
        else:
            browser.setPlainText(content)
        reader.exec()

    def _render_markdown(self, content: str) -> str:
        """Convert Markdown to styled HTML (Python-Markdown + pygments).

        Mirrors the reference md_converter compiler: tables, footnotes,
        fenced code with syntax highlighting, md_in_html, meta, nl2br,
        sane_lists. pygments runs with ``noclasses`` so the highlight colors
        are inline styles — Qt's rich-text engine renders those reliably.
        """
        from markdown import Markdown
        from markdown.extensions.codehilite import CodeHiliteExtension
        from pygments.formatters import HtmlFormatter

        md = Markdown(extensions=[
            "tables", "footnotes", "fenced_code", "md_in_html", "meta",
            "nl2br", "sane_lists",
            CodeHiliteExtension(css_class="highlight", use_pygments=True,
                                pygments_style="monokai" if self.resolved_theme == "dark" else "default"),
        ])
        body = md.convert(content)

        if self.resolved_theme == "dark":
            bg, fg, border, link = "#0f172a", "#e5e7eb", "#334155", "#60a5fa"
            code_bg = "#0b0f19"
        else:
            bg, fg, border, link = "#ffffff", "#1f2937", "#cbd5e1", "#2563eb"
            code_bg = "#f8fafc"

        css = (
            f"body {{ margin:0; padding:0 4px 12px; font-family:'Segoe UI',Arial,sans-serif;"
            f" font-size:13px; color:{fg}; background:{bg}; line-height:1.5; }}"
            f"h1,h2,h3,h4 {{ margin:1.1em 0 .5em; }}"
            f"h1 {{ font-size:1.5em; border-bottom:2px solid {border}; padding-bottom:.25em; }}"
            f"h2 {{ font-size:1.25em; border-bottom:1px solid {border}; padding-bottom:.2em; }}"
            f"code {{ background:{code_bg}; padding:1px 4px; border-radius:4px;"
            f" font-family:Consolas,monospace; font-size:12px; }}"
            f"pre {{ background:{code_bg}; border:1px solid {border}; border-radius:8px;"
            f" padding:10px; overflow-x:auto; }}"
            f"pre code {{ background:none; padding:0; }}"
            f"table {{ border-collapse:collapse; margin:.8em 0; }}"
            f"th,td {{ border:1px solid {border}; padding:5px 10px; }}"
            f"th {{ background:{code_bg}; }}"
            f"a {{ color:{link}; }}"
            f"blockquote {{ border-left:4px solid {border}; margin:.6em 0; padding:2px 12px;"
            f" color:#6b7280; }}"
            f"hr {{ border:none; border-top:1px solid {border}; margin:1em 0; }}"
        )
        return f"<html><head><style>{css}</style></head><body>{body}</body></html>"

    def _show_about(self):
        QMessageBox.information(
            self.window, APP_TITLE,
            f"Synora Bridge — Stack Launcher v{APP_VERSION}\n\n"
            "Manages daphne, celery worker, celery beat and the Nuxt frontend\n"
            "from one window. Start each service from its tab, or use\n"
            "Services → Start All.\n\n"
            f"Backend: {C.CONFIG_INI.parent} (config.ini)\n"
            f"Frontend: {C.FRONTEND_DIR}",
        )

    # ------------------------------------------------------------------ theme
    def _set_mode(self, mode):
        self.theme_mode = mode
        self._apply_theme()
        self._sync_auto_follow()
        self._refresh_theme_checks()
        self._save_theme_prefs()

    def _set_accent(self, accent):
        self.theme_accent = accent
        self._apply_theme()
        self._refresh_theme_checks()
        self._save_theme_prefs()

    def _save_theme_prefs(self):
        prefs = C.load_launcher_json()
        prefs["theme_mode"] = self.theme_mode
        prefs["theme_accent"] = self.theme_accent
        C.save_launcher_json(prefs)

    def _refresh_theme_checks(self):
        for name, mode in (("actionLight", "light"), ("actionDark", "dark"), ("actionAuto", "auto")):
            self.actions[name].setChecked(mode == self.theme_mode)
        for (mode, accent), act in self.accent_actions.items():
            act.setChecked(accent == self.theme_accent)

    def _sync_auto_follow(self):
        """While mode == auto, poll the OS scheme and re-apply on change."""
        if self.theme_mode == "auto":
            if not getattr(self, "_auto_timer", None):
                self._auto_timer = QTimer(self.window)
                self._auto_timer.timeout.connect(self._follow_system)
                self._auto_timer.start(5000)
        elif getattr(self, "_auto_timer", None):
            self._auto_timer.stop()

    def _follow_system(self):
        if self.theme_mode != "auto":
            self._auto_timer.stop()
            return
        resolved = "dark" if _system_dark() else "light"
        if resolved != self.resolved_theme:
            self._apply_theme()

    def _apply_theme(self):
        if self.theme_mode == "auto":
            resolved = "dark" if _system_dark() else "light"
        else:
            resolved = self.theme_mode
        self.resolved_theme = resolved

        app = QApplication.instance()
        if app is None:  # pragma: no cover — always created in __main__ / tests
            return
        app = cast(QApplication, app)
        # qt-material owns the base Material look (theme by mode+accent)…
        apply_stylesheet(app, f"{resolved}_{self.theme_accent}.xml")
        # …and this launcher-specific extra QSS is appended on top.
        extra = (C.STYLE_DIR / f"{resolved}.qss").read_text(encoding="utf-8")
        app.setStyleSheet(app.styleSheet() + "\n" + extra)
