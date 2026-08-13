# Synora Bridge — Installation Manual (beginner friendly)

Everything you need to get the project running on Windows **from zero** — including how to build a standalone `.exe` installer with PyInstaller. Follow the steps in order. Copy-paste the commands into **PowerShell**.

---

## 1. What you need

| Requirement | Why | How to check |
|---|---|---|
| **Windows 10/11** | The project is developed on Windows | — |
| **Python 3.12** (64-bit) | Django backend + launcher | `python --version` |
| **Node.js 20+** | Nuxt frontend build | `node --version` |
| **Git** | Clone the repository | `git --version` |
| **Redis / Memurai** | Celery broker + channel layer + cache | a `redis`/`memurai` service running on `localhost:6379` |

> No Python installed? Download from <https://www.python.org/downloads/> — **tick "Add Python to PATH"** during install.

---

## 2. Get the code

```powershell
git clone https://github.com/Arean82/API_Bridge_Application.git
cd API_Bridge_Application
```

Switch to the current development branch (if not already on it):

```powershell
git checkout Django_Launcher
```

---

## 3. Create the backend virtual environment

A virtual environment keeps dependencies isolated. From the **repo root**:

```powershell
python -m venv backend\.venv
```

Then install the backend requirements **into that venv** (use the venv's python explicitly — do not rely on `pip` alone):

```powershell
backend\.venv\Scripts\python.exe -m pip install --upgrade pip
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Install the **launcher** requirements too (PySide6 GUI + qt-material themes):

```powershell
backend\.venv\Scripts\python.exe -m pip install -r launcher\requirements.txt
```

---

## 4. Configure the environment and database

Run the setup wizard — it asks which environment (`development` = SQLite, `production` = PostgreSQL/SQLite) and creates `backend/config.ini`:

```powershell
backend\.venv\Scripts\python.exe scripts\setup_db.py
```

**Development** → SQLite (nothing else to do).
**Production + PostgreSQL** → the wizard verifies the connection and creates the role/database for you.

---

## 5. Initialize the database (migrations + demo data)

```powershell
backend\.venv\Scripts\python.exe scripts\initialize_system.py
```

This applies migrations and seeds demo templates/connections (optional).

---

## 6. Run the stack

### Option A — Stack Launcher GUI (recommended)

One window, 4 tabs: **Daphne**, **Celery Worker**, **Celery Beat**, **Frontend**. Start/Stop/Restart per service, live logs, Change Ports, Material themes.

```powershell
start_launcher.bat
```

or from the repo root:

```powershell
backend\.venv\Scripts\python.exe -m launcher
```

> **"No module named launcher"?** You ran it from `backend\` — run from the **repo root** (or use `start_launcher.bat`).

### Option B — Manual terminals

```powershell
# Terminal 1 — backend (ASGI server)
cd backend
.\.venv\Scripts\python.exe -m daphne -b 127.0.0.1 -p 8000 config.asgi:application

# Terminal 2 — celery worker
cd backend
.\.venv\Scripts\python.exe -m celery -A config.celery worker --pool=solo --concurrency=1 -l info

# Terminal 3 — celery beat (scheduler)
cd backend
.\.venv\Scripts\python.exe -m celery -A config.celery beat -l info

# Terminal 4 — frontend
cd frontend
npm install
npm run dev
```

Open <http://localhost:3000> (frontend) and <http://127.0.0.1:8000/api/v1/> (backend).

---

## 7. Build a standalone `.exe` with PyInstaller

This creates `dist\SynoraBridge_Launcher.exe` — a single file you can double-click (no Python needed to start it; it still manages the real stack, which must live beside it).

### 7.1 Install PyInstaller

```powershell
backend\.venv\Scripts\python.exe -m pip install -r launcher\requirements.txt
```

(`pyinstaller` is included in `launcher\requirements.txt`.)

### 7.2 Build

```powershell
build_launcher.bat
```

Or run the two specs individually (Linux/macOS: `build_launcher.sh`):

```powershell
backend\.venv\Scripts\pyinstaller.exe launcher_onedir.spec --distpath dist\one_dir --noconfirm
backend\.venv\Scripts\pyinstaller.exe launcher.spec       --distpath dist\one_file --noconfirm
```

The build takes a few minutes (PySide6 is large). When it finishes you'll see:

```
Build complete! The results are available in: ...\dist\one_dir
Build complete! The results are available in: ...\dist\one_file
```

Two artifacts:

| Output | Use |
|---|---|
| `dist\one_dir\SynoraBridge_Launcher\` | **Fastest start** (no temp extraction) — use daily |
| `dist\one_file\SynoraBridge_Launcher.exe` | **Single portable file** — distribution |

> macOS: `dist\one_dir\SynoraBridge_Launcher.app` (double-clickable).

### 7.3 What was bundled

The `.spec` files automatically include:
- the Qt Designer UI (`launcher/ui/main_window.ui`) and the theme stylesheets (`launcher/style/*.qss`)
- the qt-material theme XMLs (only the 18 accents exposed in the menu)
- `PySide6.QtUiTools` (hidden import)
- unused Qt modules (WebEngine, QML, Multimedia, …) are **excluded** to keep it small

`dist/` and `build/` are gitignored — they won't pollute the repo.

### 7.4 Run the exe

Copy **`dist\one_file\SynoraBridge_Launcher.exe`** (or the whole `dist\one_dir\SynoraBridge_Launcher\` folder) to the **repo root** (next to `backend\` and `frontend\`) and double-click it.

- The exe finds the stack in its own folder.
- Put it somewhere else? Set the environment variable `SYNORA_HOME` to the repo path:

```powershell
$env:SYNORA_HOME = "E:\GitHub\API_Bridge_Application"
dist\one_file\SynoraBridge_Launcher.exe
```

> The exe is a **windowed** app (no console). Service logs appear inside its tabs.

### 7.5 Make a real "installer" (optional)

PyInstaller gives you the portable exe. For a setup wizard with Start-menu shortcut / install location, wrap **`dist\one_file\SynoraBridge_Launcher.exe`** with the free **Inno Setup** (<https://jrsoftware.org/isinfo.php>): point it at the exe and add `backend\`, `frontend\` as the install payload. That produces a `Setup.exe` a user can install.

---

## 8. Frontend production build

The launcher serves the frontend from its **production build** when it exists, otherwise falls back to dev mode:

```powershell
cd frontend
npm install
npm run build
```

Build output goes to `frontend\.output\` — the launcher then serves it with `node`. (Delete `frontend\.output` to go back to `npm run dev`.)

---

## 9. Troubleshooting

| Problem | Fix |
|---|---|
| `No module named launcher` | Run from the **repo root**, or use `start_launcher.bat` |
| `python` not found | Install Python 3.12 and tick "Add Python to PATH", then reopen PowerShell |
| Launcher shows "failed to start daphne" | `backend/config.ini` missing → run `scripts/setup_db.py` first |
| `address already in use` / port busy | Another instance is running; the launcher warns on start — use **File → Change Ports…** |
| Celery worker errors | Redis/Memurai not running → start it (`localhost:6379`) |
| Frontend tab shows nothing | Run `npm run build` (see section 8), or check the Frontend tab's log |
| `pyside6-designer` not found | Install the launcher requirements (section 3) |
| Theme choices not remembered | `launcher/launcher.json` holds them (deleted → defaults to Auto/blue) |

---

## 10. Useful references

- `README.md` — quick start + feature summary
- `docs/ARCHITECTURE.md` — how the pieces fit together
- `docs/DEPLOYMENT.md` — production deployment (nginx TLS, pgbouncer)
- `docs/SECURITY.md` — security model and configuration hardening
