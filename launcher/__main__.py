"""Entry point: python -m launcher"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from launcher.app import LauncherApp, APP_TITLE


def main() -> int:
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
