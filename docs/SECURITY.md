# Security — Synora Bridge

## At-rest encryption

Sensitive values (source auth tokens, destination credentials, client tokens, custom headers, payload caches) are stored **AES-256-GCM** encrypted (12-byte random nonce per value, marker-prefixed `$e$` ciphertext).

- Master key: `[SECURITY] encryption_key` in `backend/config.ini` (base64 32-byte key) — or `ENCRYPTION_KEY` env override.
- **Production refuses to start without it.** In development, a key is derived from `SECRET_KEY` so local data is still encrypted at rest.
- Legacy plaintext / legacy Flask-format values are detected and handled transparently on read.

Generate a key:

```python
python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"
```

## API authentication

- Management API (`/api/v1/*`) is open for read/write by design (parity with the original single-tenant Flask tool); Django admin is session-guarded.
- **Pull endpoints** enforce per-template bearer auth when `client_credentials.token` is set: the request must present `Authorization: Bearer <token>`.
- Optional **rate limiting** on pull endpoints (`[RateLimit]`, Redis-backed) — 429 responses when exceeded.

## Input validation & SSRF protection

- OpenAPI spec fetching and validation (`apps/connections/services.py`, `apps/pull`) block localhost/metadata addresses and enforce a 5 MB spec cap.
- URL paths are matched against validated templates/connections only (indexed slug lookups — no raw SQL, no template injection).
- DRF serializers validate all CRUD payloads; encrypted JSON columns are explicitly typed.

## Configuration hardening

- `backend/config.ini` fail-fast validation:
  - Invalid `[Server] timezone` → startup aborts with a clear message (IANA list required).
  - Production invariants: `environment = production` requires real `secret_key`, `encryption_key`, `always_eager = false`. HTTPS-only behavior (SSL redirect `SECURE_SSL_REDIRECT`, HSTS, secure cookies `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE`, trusted `X-Forwarded-Proto`) activates **only** when `[ReverseProxy] enabled = true` — i.e. daphne is behind a TLS-terminating proxy (deploy/nginx.conf). Running daphne directly (no proxy) serves plain HTTP and never redirects to https (which would dead-end on a TLS-less listener). The database engine is the section whose `enabled = true` — `[SQLITE]` (standalone default) or `[POSTGRES]`, which the Settings GUI verifies (stateless `POST /api/v1/config/verify-db/`) before the switch is persisted; unverified PostgreSQL falls back to SQLite with a user-visible message. Exactly one of the two flags must be enabled.
- `.env` (root) holds only the two secret overrides; it is gitignored.

## Audit

Every data transaction (PUSH / PULL_REST / PULL_GRAPHQL) is written to the **Universal Audit Engine** (`AuditLog`): transaction id, mode, caller, bytes, record count, status, endpoint, template. Viewable in the UI (Audit Logs page) and via `/api/v1/audit-logs/`.

## Reporting

Found a security issue? Open an issue on the repository. Do not open public issues for credential-related bugs.
