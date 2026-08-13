#!/usr/bin/env bash
# Build the Synora Bridge Stack Launcher GUI with PyInstaller (Linux / macOS).
#
#   one_dir -> dist/one_dir/SynoraBridge_Launcher/   (fastest start; daily use)
#   one_file-> dist/one_file/SynoraBridge_Launcher    (single portable binary)
#   macOS   -> dist/one_dir/SynoraBridge_Launcher.app (double-clickable app)
#
# Keep the built binary beside backend/ and frontend/ (or set SYNORA_HOME).
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-backend/.venv/bin/python}"
if [ ! -x "$PY" ]; then
  echo "venv python not found at $PY — create it first:"
  echo "  python -m venv backend/.venv"
  echo "  backend/.venv/bin/pip install -r launcher/requirements.txt"
  exit 1
fi

"$PY" -m PyInstaller launcher_onedir.spec --distpath dist/one_dir --noconfirm
"$PY" -m PyInstaller launcher.spec --distpath dist/one_file --noconfirm

echo
echo "Done."
if [ "$(uname)" = "Darwin" ]; then
  echo "  App bundle : dist/one_dir/SynoraBridge_Launcher.app"
  echo "  Portable   : dist/one_file/SynoraBridge_Launcher"
else
  echo "  Fast start : dist/one_dir/SynoraBridge_Launcher/SynoraBridge_Launcher"
  echo "  Portable   : dist/one_file/SynoraBridge_Launcher"
fi
echo "Keep the binary beside backend/ and frontend/ (or set SYNORA_HOME)."
