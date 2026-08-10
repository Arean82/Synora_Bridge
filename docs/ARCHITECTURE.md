# Architecture — Synora Bridge (Django + Nuxt 4)

## System overview

```
                 ┌──────────────────────────────────────────────┐
   Nuxt 4 SPA    │              Django 5 / daphne (ASGI)        │
  (localhost:3000)│                                              │
                 │  ┌──────────┐  ┌───────────┐  ┌───────────┐  │
   REST /api/v1 ─┼─▶│ DRF      │  │ Pull REST │  │ Pull Graph│  │
   GraphQL      ─┼─▶│ viewsets │  │ (dynamic  │  │ (Strawb-  │  │
   WebSocket    ─┼─▶│          │  │  OpenAPI) │  │  erry)    │  │
   /ws/feed/    ─┼─▶│          │  └───────────┘  └───────────┘  │
                 │  └────┬─────┘        │            │          │
                 │       │              └──▶ Celery tasks ─────▶│  Source APIs
                 │  ┌────▼─────┐   ┌─── Channels ───┐           │  (external)
                 │  │ PostgreSQL│   │  (WS layer)   │           │
                 │  │ / SQLite │   └───────┬────────┘           │
                 │  └──────────┘           │ Redis/Memurai      │
                 └─────────────────────────┼────────────────────┘
                                           │ (channel layer + broker + cache)
```

## Modular app layout

Each feature is a self-contained Django app under `backend/apps/` owning its models, serializers, viewsets, router, services and URLs:

| App | Responsibility |
|---|---|
| `core` | Shared services (encryption, audit, email, OTel, errors), AppSetting, AuditLog |
| `configs` | Bridge templates (sources → destinations → field mappings), indexed slug |
| `connections` | OpenAPI/Swagger connections, spec validation/fetch, refresh task |
| `jobs` | Scheduled jobs, JobLog, FailedPayload, Celery tasks, beat sync |
| `pull` | Dynamic pull REST + GraphQL endpoints, OpenAPI generator, mock server |
| `realtime` | Channels WebSocket consumers (`/ws/feed/<id>/`) |
| `observability` | Health probes + metrics |

URLs compose in `config/api_router.py` — adding a feature = register its router, nothing else changes.

## Data flow — push mode

1. Celery beat fires `apps.jobs.tasks.pull_and_push_job` (schedule synced from DB via `django-celery-beat` DatabaseScheduler; signals keep beat in sync on job create/toggle/delete).
2. Sources are fetched concurrently (thread pool; pull endpoints use async httpx) and merged with `source_<i>.field` prefixes.
3. Each destination's `field_mapping` is applied by `build_nested_payload` (dot/bracket notation → nested JSON).
4. Push with retry session + auth flows (`bearer`, `custom_login`); outcome → JobLog + AuditLog; failures → FailedPayload + email alert; aggregated payload → WebSocket `feed_<template_id>`.

## Dynamic endpoints

- **Pull REST**: `/api/v1/bridge/pull/<slug>/<dest>/` — executed on demand; OpenAPI spec generated on the fly (`/spec?version=2.0|3.0.3|3.1.0|3.2.0`), Swagger UI at `/docs`.
- **Pull GraphQL**: `/api/v1/bridge/graphql/<slug>/<dest>/` — Strawberry schema built per request via `strawberry.tools.create_type` from field mappings (nested objects/lists), GraphiQL on GET, execution on POST (bare slug redirects to the first destination).
- **Mock server**: `/api/v1/mock/<connection_id>/<path>` — serves spec examples with `{param}` path matching.
- **Per-connection docs**: `/api/v1/docs/<id>/` (Swagger UI from the stored spec) and `/api/v1/graphql/test/<id>/` (GraphiQL for GraphQL connections).
- **Validation utilities**: `/api/v1/connections/validate/` (SSRF-hardened spec validation), `/api/v1/test_mapping/` (field-mapping preview), `/api/v1/bridge/graphql_introspect/`.
- **System Configuration**: `GET/PUT /api/v1/config/` reads/writes the entire `config.ini` (typed values, restart-required detection) for the Settings GUI.

## Security model

- AES-256-GCM at-rest encryption for tokens/credentials (`apps/core/fields.py`, marker-prefixed `$e$` ciphertext, prod-enforces `ENCRYPTION_KEY`).
- Per-template bearer auth on **data execution** only (pull REST data + GraphQL POST); spec/docs/playground pages are public (original parity).
- SSRF protection (resolved-IP + private-CIDR blocking) + 5 MB cap + external-`$ref` rejection in `openapi_validator.py`.
- Rate limiting (django-ratelimit, Redis, fail-open on cache outage) on pull endpoints — config.ini `[RateLimit]`.
- Email-template API rejects path traversal (resolve + containment check).
- Fail-fast config validation: invalid timezone / missing prod keys abort startup with clear messages.

## Observability

- `/health/live`, `/health/ready`, `/health`, `/metrics` (Zabbix-style counters).
- OpenTelemetry instrumentation, config-gated (`[OPENTELEMETRY]`, optional deps).
- Per-connection rotating file logs (`backend/logs/`).
