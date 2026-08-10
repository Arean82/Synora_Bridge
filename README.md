# Synora Bridge — Universal API Bridge

A production-grade **API integration middleware** built on **Django 5 + Nuxt 4** that moves data between Partner Source APIs and Client Destination APIs — with **fully dynamic** endpoints: templates, connections, pull REST endpoints, OpenAPI specs, GraphQL schemas and mock routes are all created at runtime from the UI/API, no code per API.

> This is the new Django + Nuxt 4 implementation. The original Flask app is preserved on the `Flask` branch.

## Architecture

```
Django 5 (ASGI: daphne)
├── DRF ───────────── REST API        /api/v1/*
├── Strawberry ────── GraphQL         /api/v1/bridge/graphql/<slug>/ (dynamic schema)
├── Channels ──────── WebSockets      /ws/feed/<template_id>/ (live feed)
├── Celery ────────── background jobs (push engine, beat scheduler)
├── drf-spectacular ── OpenAPI schema → generated clients (hey-api web, dart-dio mobile)
└── Redis (Memurai on Windows) ─────── channel layer + Celery broker + pull cache

Nuxt 4 (Vue 3) — frontend SPA (Tailwind v4 + PrimeVue fallback)
```

## Repository layout

| Path | Contents |
|---|---|
| `backend/` | Django project — modular apps, config.ini-driven settings, tests |
| `frontend/` | Nuxt 4 SPA — pages, composables, hey-api generated client |
| `deploy/` | Ops templates: nginx reverse proxy, pgbouncer pool |
| `scripts/` | Dev launchers (`dev_backend.bat`, `dev_frontend.bat`) |
| `instance/` | Runtime data: SQLite DB (dev) + uploaded spec files |

## Feature summary

- **Push mode** — scheduled multi-source fetch (concurrent/async) → transform via field mappings → push to multiple destinations with retries, auth flows, audit, failed-payload queue, email alerts, live WebSocket feed.
- **Pull REST** — auto-generated endpoints with dynamic OpenAPI specs in **2.0 / 3.0.3 / 3.1.0 / 3.2.0** + Swagger UI.
- **Pull GraphQL** — auto-generated Strawberry schema (nested objects/lists from field mappings) + GraphiQL playground (per-template and per-destination).
- **Mock server** — serve example JSON from any connection's OpenAPI spec.
- **System Configuration GUI** — view/edit the entire `backend/config.ini` from the browser (all 16 sections, typed widgets, restart-required banner).
- **Templates** — per-template **Docs** (Swagger UI, 3.2.0 default), **GraphQL playground**, **Clone**, **Edit** and **Delete**; two-pane **IN/OUT builder** (Source Input API ↔ Destination Client API, mode dropdown, global security token, mode-specific config, schedule footer).
- **Connections** — Add Connection modal (REST/GraphQL, URL/paste spec, upstream auth), status toggle, refresh, per-connection docs/playground/mock.
- **Dashboard** — schedule table with per-job toggle, **Bulk Start/Stop + master select**, live 5s polling.
- **Audit** — transaction details modal with syntax-highlighted payload JSON.
- **Email templates** — list/read/edit failure-alert templates (path-traversal hardened).
- **Validation utilities** — `/connections/validate` (SSRF-hardened), `/test_mapping` (mapping preview), `/bridge/graphql_introspect`.
- **Security** — AES-256-GCM at-rest encryption, per-template bearer auth on data execution (docs/playground public), SSRF protection, rate limiting, fail-fast config validation.
- **Scale** — indexed slug routing, Redis pull cache, async upstream fetch, Celery worker tuning, pgbouncer + nginx templates, OpenTelemetry (config-gated).

## Quick start

**Backend** (see `backend/README.md` for full details):

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python scripts/seed_demo.py --create-admin   # demo data (real fetchable sources) + admin/admin123
python -m daphne -b 127.0.0.1 -p 8000 config.asgi:application
```

**Frontend** (see `frontend/README.md`):

```powershell
cd frontend
npm install
npm run dev                       # http://localhost:3000
```

Or use the one-click launchers: `scripts\dev_backend.bat` and `scripts\dev_frontend.bat`.

## Configuration

All runtime configuration lives in `backend/config.ini` (same structure as the original Flask app). The single most important flag:

```ini
[Server]
environment = development    ; development → SQLite (instance/) · production → PostgreSQL
```

See `backend/README.md` → "Configuration file" for the full section reference.

## Tests

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests
```

## License

AGPL-3.0 — see `LICENSE`.
