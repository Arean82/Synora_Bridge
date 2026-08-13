"""PyInstaller entry point for the Stack Launcher GUI (current branch).

Build:  backend\\.venv\\Scripts\\pyinstaller.exe launcher.spec --noconfirm
Run:    dist\\SynoraBridge_Launcher.exe   (place beside backend/ and frontend/)
"""
from launcher.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
