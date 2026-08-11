# Deployment — Synora Bridge

## Prerequisites

- Python 3.12+, Node 20+ (for the frontend build)
- PostgreSQL (production) or SQLite (development)
- Redis or Memurai (channel layer + Celery broker)

## Development (Windows)

```powershell
# Backend
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python scripts/seed_demo.py --create-admin   # optional demo dataset (real fetchable sources)
python -m daphne -b 127.0.0.1 -p 8000 config.asgi:application

# Frontend (separate terminal)
cd frontend
npm install
npm run dev                       # http://localhost:3000
```

Or use `scripts\dev_backend.bat` and `scripts\dev_frontend.bat`.

## Production

1. **Configure** `backend/config.ini`:
   - `[Server] environment = production`
   - `[POSTGRES]` — host/port/database/username/password
   - `[SECURITY]` — `secret_key` + `encryption_key` (required; app refuses to start without them)
   - `[CELERY] always_eager = false`
   - `[ReverseProxy] enabled = true`, `[DatabasePool] enabled = true` if using nginx/pgbouncer

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
| `[Server]` | host, port, debug, **environment** (development→SQLite / production→PostgreSQL), timezone (fail-fast validated), allowed_hosts |
| `[POSTGRES]` / `[SQLITE]` | database connection settings |
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
