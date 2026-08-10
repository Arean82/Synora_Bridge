# Synora Bridge — Django backend

The Universal API Bridge rebuilt on **Django 5 + daphne** (replacing the Flask app; original preserved on the `Flask` branch).

**Stack:** Django 5.2 · DRF `/api/v1/*` · Strawberry GraphQL (dynamic schema) · Channels WebSockets · Celery + beat · drf-spectacular (hey-api/dart-dio client generation) · Redis/Memurai channel layer + broker · PostgreSQL (prod) / SQLite (dev).

## Quick start (development)

```powershell
# 1. Create + activate the venv and install
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Configure (optional — sensible defaults already set)
#    backend/config.ini  — same structure as the original Flask app.
#    [Server] environment = development  → SQLite (instance/bridge_app.db)
#    [Server] environment = production   → PostgreSQL ([POSTGRES] section)

# 3. Migrate + seed a demo dataset (17 connections, 34 templates, jobs, audit)
python manage.py migrate
python ../scripts/seed_demo.py --create-admin   # demo data: real fetchable sources, nested mappings, job logs, admin user

# 4. Run the server (daphne = ASGI: HTTP + WebSockets)
python -m daphne -b 127.0.0.1 -p 8000 config.asgi:application
```

## Frontend (Nuxt 4)

See `frontend/README.md`. Dev:

```powershell
cd frontend
npm install
npm run api:generate   # regenerate typed client from the backend OpenAPI schema
npm run dev            # http://localhost:3000
```

## Production

```powershell
# config.ini: [Server] environment = production + fill [POSTGRES], [SECURITY]
#   [SECURITY] secret_key + encryption_key required (app refuses to start without them)
#   [CELERY] always_eager must be false
python manage.py migrate --settings=config.settings
python manage.py collectstatic --noinput
python manage.py sync_beat

# Three processes (Redis/Memurai required):
python -m daphne -b 0.0.0.0 -p 8000 config.asgi:application   # HTTP + WS
celery -A config.celery worker -l info --concurrency=8        # jobs
celery -A config.celery beat -l info                          # scheduler
```

Optional ops components (config-gated, templates in `deploy/`):
- `deploy/nginx.conf` — TLS / gzip / static cache / WebSocket proxying (`[ReverseProxy] enabled = true`)
- `deploy/pgbouncer.ini` — connection pooling (`[DatabasePool] enabled = true`)
- OpenTelemetry tracing (`[OPENTELEMETRY] enabled = true` + optional pip packages)

## Configuration file

`backend/config.ini` mirrors the original Flask config: `[Server]` (incl. `environment`), `[POSTGRES]`, `[SQLITE]`, `[CELERY]`, `[SECURITY]`, `[CORS]`, `[UI]`, `[OPENTELEMETRY]`, `[RateLimit]`, `[Cache]`, `[DatabasePool]`, `[ReverseProxy]`, `[Logging]`, `[RetryQueue]`, `[Swagger]`, `[Email]`.

The `environment` flag selects the database: **development → SQLite, production → PostgreSQL**.

## Key endpoints

| Area | Path |
|---|---|
| REST API | `/api/v1/*` (templates, jobs, connections, settings, audit, health, metrics, config) |
| System Configuration | `GET/PUT /api/v1/config/` — read/write the full `config.ini` from the Settings GUI |
| Dynamic pull REST | `/api/v1/bridge/pull/<slug>/<dest>/` · spec `?version=2.0|3.0.3|3.1.0|3.2.0` · Swagger UI `docs` |
| Dynamic pull GraphQL | `/api/v1/bridge/graphql/<slug>/` (GET = GraphiQL, POST = execute) |
| Mock server | `/api/v1/mock/<connection_id>/<path>` |
| OpenAPI schema + docs | `/schema/` · `/schema/swagger-ui/` · `/schema/redoc/` |
| WebSockets | `/ws/feed/<template_id>/` |

## Tests

```powershell
python -m pytest backend/tests
```

## Management commands

- `python scripts/seed_demo.py` (from repo root) — demo-ready dataset: connections from live OpenAPI specs (APIs.guru registry resolved to latest versions), templates whose source URLs are derived from each spec (so pull endpoints return **real data**), schema-derived nested field mappings, job-run history, UI settings, optional `--create-admin`. Kept out of the app on purpose (demo tool, not needed in production).
- `python manage.py sync_beat` — reconcile Celery beat schedule with jobs

## Notes

- Sensitive template/connection JSON (tokens, credentials) is encrypted at rest with AES-256-GCM (`[SECURITY] encryption_key`).
- Pull endpoints enforce per-template bearer auth (`client_credentials.token`) when configured, plus optional rate limiting (`[RateLimit]`) and short-TTL response caching (`[Cache]`).
- Everything is dynamic: templates, connections, pull REST endpoints, GraphQL schemas and mock routes are created at runtime from the UI/API — no code per API.
