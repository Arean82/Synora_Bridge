# Deployment — Synora Bridge

## Prerequisites

- Python 3.12+, Node 20+ (for the frontend build)
- SQLite (development; production standalone default) or PostgreSQL (production opt-in via `[POSTGRES] enabled = true`)
- Redis or Memurai (channel layer + Celery broker)

## Development (Windows)

```powershell
# 1. Backend venv
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt

# 2. Configure environment + database (development → SQLite; production → PG/SQLite)
backend\.venv\Scripts\python.exe scripts\setup_db.py

# 3. Migrations + demo data
backend\.venv\Scripts\python.exe scripts\initialize_system.py

# 4. Run — easiest via the stack launcher GUI (4 tabs: daphne/worker/beat/frontend)
start_launcher.bat
```

Manual alternative (four terminals): daphne `-b 127.0.0.1 -p 8000 config.asgi:application` in `backend/`, `celery -A config.celery worker --pool=solo --concurrency=1 -l info`, `celery -A config.celery beat -l info`, and `npm run dev` in `frontend/`. See `docs/INSTALLATION_MANUAL.md` for the full beginner walkthrough (including building a standalone exe with PyInstaller).

## Production

1. **Configure** `backend/config.ini`:
   - `[Server] environment = production`
   - Database engine: `[SQLITE] enabled = true` (default — no setup, auto-creates the DB) **or** `[POSTGRES] enabled = true` + `[SQLITE] enabled = false` (the Settings GUI verifies the PostgreSQL connection before the switch is saved). Exactly one must be enabled.
   - `[POSTGRES]` — host/port/database/username/password (only when using PostgreSQL)
   - `[SECURITY]` — `secret_key` + `encryption_key` (required; app refuses to start without them)
   - `[CELERY] always_eager = false`
   - `[ReverseProxy] enabled = true`, `[DatabasePool] enabled = true` if using nginx/pgbouncer. **Important:** without `[ReverseProxy] enabled = true` the app serves plain HTTP (no HTTPS redirect, no secure cookies) so daphne can be tested directly at `http://localhost:8000/`. HTTPS is provided by the TLS-terminating proxy (deploy/nginx.conf), which must set `X-Forwarded-Proto: https` — the app only enforces HTTPS redirection/HSTS when the proxy flag is on.

2. **Migrate + collect static:**

```powershell
cd backend
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py sync_beat
```

3. **Run three processes** (Redis/Memurai must be running):

```powershell
python -m daphne -b 0.0.0.0 -p 8000 config.asgi:application   # HTTP + WebSockets
# Windows: Celery's default prefork pool fails (PermissionError WinError 5 +
# no SIGUSR1 for soft timeouts) — use --pool=solo or --pool=threads.
celery -A config.celery worker --pool=solo --concurrency=1 -l info   # push jobs
celery -A config.celery beat -l info                                # scheduler
```

> **Windows note:** Memurai (Redis) must be running. If the service won't start
> (needs admin), launch it directly:
> `"C:\Program Files\Memurai\memurai.exe" "C:\Program Files\Memurai\memurai.conf"`

4. **Reverse proxy** — use `deploy/nginx.conf` (TLS, gzip, static caching, WebSocket upgrade headers) and `deploy/pgbouncer.ini` (pooling). Point nginx at daphne (127.0.0.1:8000) and staticfiles.

## Configuration file reference (`backend/config.ini`)

| Section | Purpose |
|---|---|
| `[Server]` | host, port, debug, **environment** (development→SQLite locked / production→hardened), timezone (fail-fast validated), allowed_hosts |
| `[POSTGRES]` / `[SQLITE]` | database connection settings + **enabled** flag (the production engine selector — exactly one must be true; dev is locked to SQLite, prod postgresql requires a verified connection) |
| `[CELERY]` | broker_url, result_backend, always_eager, worker concurrency/prefetch, time limits |
| `[SECURITY]` | secret_key, encryption_key (AES-256-GCM master key) |
| `[CORS]` | allowed frontend origins |
| `[UI]` | theme, color mode, layout, date format |
| `[OPENTELEMETRY]` | enable/disable tracing + instrumented components |
| `[RateLimit]` | pull-endpoint rate limiting (enabled, rate, period) |
| `[Cache]` | pull response cache (enabled, TTL) |
| `[DatabasePool]` | enable/disable connection pooling |
| `[ReverseProxy]` | enable/disable trusted proxy headers |
| `[Logging]`, `[RetryQueue]`, `[Swagger]`, `[Email]` | logs, failed-payload retention, spec refresh cadence, alert email |

## Upgrading the generated API client (hey-api)

```powershell
cd backend
python manage.py spectacular --file schema/openapi.json   # export OpenAPI schema
cd ..\frontend
npm run api:generate                                       # regenerate app/lib/api
```
