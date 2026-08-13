"""Entry point: python -m launcher

Also doubles as the all-in-one service runner in frozen builds:
    SynoraBridge_Launcher.exe --service daphne [-b host -p port]
    SynoraBridge_Launcher.exe --service worker
    SynoraBridge_Launcher.exe --service beat
    SynoraBridge_Launcher.exe --selfcheck          (verify the bundle imports)
"""
from __future__ import annotations

import os
import sys


def _log(msg: str) -> None:
    """Windowed (console=False) exes have no stdout/stderr — mirror to a log
    file beside the exe so --service/--selfcheck output is recoverable."""
    try:
        print(msg)
    except Exception:  # noqa: BLE001 — no console in windowed builds
        pass
    try:
        log_path = os.path.join(os.path.dirname(sys.executable), "launcher-service.log")
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(msg + "\n")
    except Exception:  # noqa: BLE001
        pass


def _run_service(argv: list[str]) -> int:
    """Run a backend service inside the frozen bundle (no external venv)."""
    from launcher.config import FROZEN, BACKEND_DIR

    os.chdir(BACKEND_DIR)
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    try:
        service = argv[0]
        rest = argv[1:]
        if service == "daphne":
            from daphne.cli import CommandLineInterface

            CommandLineInterface().run(rest or ["-b", "127.0.0.1", "-p", "8000", "config.asgi:application"])
            return 0
        if service in ("worker", "beat"):
            from celery.bin.celery import celery

            celery.start(["celery", "-A", "config.celery", service, "--loglevel=info"] + rest)  # type: ignore[attr-defined]
            return 0
        _log(f"[launcher] unknown --service: {service}")
        return 2
    except Exception as exc:  # noqa: BLE001
        import traceback

        _log(f"[launcher] service '{argv[0] if argv else '?'}' failed:\n{traceback.format_exc()}")
        return 1


def _selfcheck() -> int:
    from launcher.config import BACKEND_DIR, FROZEN, REPO_ROOT

    os.chdir(BACKEND_DIR)
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    try:
        import django  # noqa: F401  (must import from the bundle)
        from django.conf import settings

        django.setup()
        _log(f"selfcheck OK — frozen={FROZEN} backend={BACKEND_DIR} root={REPO_ROOT}")
        _log(f"settings loaded; DB engine: {settings.DATABASES['default']['ENGINE']}")
        return 0
    except Exception as exc:  # noqa: BLE001
        import traceback

        _log(f"selfcheck FAILED:\n{traceback.format_exc()}")
        return 1


def main() -> int:
    argv = sys.argv[1:]
    if argv and argv[0] == "--service":
        return _run_service(argv[1:])
    if argv and argv[0] == "--selfcheck":
        return _selfcheck()

    from PySide6.QtWidgets import QApplication

    from launcher.app import APP_TITLE, LauncherApp

    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setStyle("Fusion")  # consistent base look across platforms; QSS on top

    launcher = LauncherApp()
    launcher.show()

    # Stop every service when the window closes / the app quits.
    app.aboutToQuit.connect(launcher.stop_all)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
