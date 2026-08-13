# Synora Bridge — Universal API Bridge

A production-grade **API integration middleware** built on **Django 6 + Nuxt 4** that moves data between Partner Source APIs and Client Destination APIs — with **fully dynamic** endpoints: templates, connections, pull REST endpoints, OpenAPI specs, GraphQL schemas and mock routes are all created at runtime from the UI/API, no code per API.

> This is the new Django + Nuxt 4 implementation. The original Flask app is preserved on the `Flask` branch.

## Architecture

```
Django 6 (ASGI: daphne)
  ├─ DRF               ─ REST API        /api/v1/*
  ├─ Strawberry        ─ GraphQL         /api/v1/bridge/graphql/<slug>/ (dynamic schema)
  ├─ Channels          ─ WebSockets      /ws/feed/<template_id>/ (live feed)
  ├─ Celery            ─ background jobs (push engine, beat scheduler)
  ├─ drf-spectacular   ─ OpenAPI schema + generated clients (hey-api web, dart-dio mobile)
  └─ Redis (Memurai on Windows) ─ channel layer + Celery broker + pull cache

Nuxt 4 (Vue 3) — frontend SPA (Tailwind v4 + PrimeVue fallback)
```

## Repository layout

| Path | Contents |
|---|---|
| `backend/` | Django project — modular apps, `config.ini`-driven settings, tests |
| `frontend/` | Nuxt 4 SPA — pages, composables, hey-api generated client |
| `launcher/` | **PySide6 stack launcher** — Qt Designer UI (`.ui`), qt-material themes, PyInstaller spec |
| `scripts/` | `setup_db.py`, `activate_db.py`, `initialize_system.py` (env/db/demo workflows) |
| `deploy/` | Ops templates: nginx reverse proxy, pgbouncer pool |
| `docs/` | Architecture, deployment, security, **installation manual** |

## Feature summary

- **Push mode** — scheduled multi-source fetch (concurrent/async) + transform via field mappings + push to multiple destinations with retries, auth flows, audit, failed-payload queue, email alerts, live WebSocket feed.
- **Pull REST** — auto-generated endpoints with dynamic OpenAPI specs in **2.0 / 3.0.3 / 3.1.0 / 3.2.0** + Swagger UI.
- **Pull GraphQL** — auto-generated Strawberry schema (nested objects/lists from field mappings) + GraphiQL playground (per-template and per-destination).
- **Mock server** — serve example JSON from any connection's OpenAPI spec.
- **System Configuration GUI** — view/edit the entire `backend/config.ini` from the browser (all sections, typed widgets, auto-restart on core changes).
- **Templates** — per-template **Docs** (Swagger UI), **GraphQL playground**, **Clone**, **Edit** and **Delete**; two-pane **IN/OUT builder**.
- **Connections** — Add Connection modal (REST/GraphQL, URL/paste spec, upstream auth), status toggle, refresh, per-connection docs/playground/mock.
- **Dashboard** — schedule table with per-job toggle, **Bulk Start/Stop + master select**, live polling.
- **Audit** — transaction details modal with syntax-highlighted payload JSON.
- **Django admin** — themed with **Jazzmin** (26 Bootswatch themes, light/dark toggle).
- **Security** — AES-256-GCM at-rest encryption, per-template bearer auth, SSRF protection, rate limiting, fail-fast config validation.
- **Scale** — indexed slug routing, Redis pull cache, Celery tuning, pgbouncer + nginx templates, OpenTelemetry (config-gated).

## Quick start

**1. Create the backend virtual environment:**

```powershell
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

**2. Configure the environment + database** (development → SQLite; production → PostgreSQL or SQLite):

```powershell
backend\.venv\Scripts\python.exe scripts\setup_db.py
```

**3. Initialize** (migrations + demo data):

```powershell
backend\.venv\Scripts\python.exe scripts\initialize_system.py
```

**4. Run — the easy way (stack launcher GUI):**

```powershell
start_launcher.bat
```

The launcher opens one window with 4 tabs — **Daphne, Celery Worker, Celery Beat, Frontend** — with Start/Stop/Restart, live logs, port settings and light/dark Material themes.

**Run from four terminals instead** (one command per terminal, PowerShell):

```powershell
# Terminal 1 — backend ASGI server
cd backend
.\.venv\Scripts\python.exe -m daphne -b 127.0.0.1 -p 8000 config.asgi:application

# Terminal 2 — celery worker
cd backend
.\.venv\Scripts\python.exe -m celery -A config.celery worker --pool=solo --concurrency=1 -l info

# Terminal 3 — celery beat (scheduler)
cd backend
.\.venv\Scripts\python.exe -m celery -A config.celery beat -l info

# Terminal 4 — frontend (http://localhost:3000)
cd frontend
npm install
npm run dev
```

## Launcher

- GUI tool (PySide6) that manages the whole dev stack from one window — no juggling terminals.
- UI layout lives in `launcher/ui/main_window.ui` — open it with `backend\.venv\Scripts\pyside6-designer.exe launcher\ui\main_window.ui` to redesign the look.
- Theme: qt-material (Light/Dark/Auto + **Material ▸** accent submenu), persisted in `launcher/launcher.json`.

## Building

**1. Developer exes** (launcher GUI only; keep the exe beside `backend\` and `frontend\`):

```powershell
backend\.venv\Scripts\python.exe -m pip install -r launcher\requirements.txt
build_launcher.bat
```

- `dist\one_dir\SynoraBridge_Launcher\` — **fastest start** (no extraction), daily use
- `dist\one_file\SynoraBridge_Launcher.exe` — **single portable file**, distribution
- macOS additionally produces `dist\one_dir\SynoraBridge_Launcher.app` (`build_launcher.sh` on Linux/macOS)

**2. All-in-one exe** (launcher **+ backend + every dependency + frontend build + node** — everything inside the bundle):

```powershell
build_allinone.bat
```

- Output: `dist\allinone\SynoraBridge\SynoraBridge_Launcher.exe` — double-click it, the whole stack starts (the exe runs daphne/celery itself via a hidden `--service` mode; no repo, no Python, no node needed).
- The build script stages a clean backend copy (`installer_stage\`, gitignored), bundles the frontend production build, and self-checks the bundle before finishing.

> Full beginner walkthrough (venv, setup, run, build, troubleshooting): **[docs/INSTALLATION_MANUAL.md](docs/INSTALLATION_MANUAL.md)**

## Configuration

All runtime configuration lives in `backend/config.ini`. The most important flag:

```ini
[Server]
environment = development    ; development → SQLite (locked) — production → SQLite or PostgreSQL
```

The database engine is whichever of `[POSTGRES]`/`[SQLITE]` has `enabled = true` in production (exactly one). Everything is editable from the web UI (Settings page) or `scripts/setup_db.py`.

## Tests

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
```

## License

AGPL-3.0 — see `LICENSE`.
