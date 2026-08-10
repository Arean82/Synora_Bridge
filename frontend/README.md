# Synora Bridge — Nuxt 4 frontend

Nuxt 4 (Vue 3) SPA for the Universal API Bridge. Consumes the Django backend at `/api/v1/*`, uses the **hey-api generated typed client** (from the drf-spectacular schema), **Nuxt components to the max** with **PrimeVue** as the fallback UI kit, and connects to the **Channels WebSocket feed** for live updates.

## Dev

```powershell
npm install
npm run api:generate   # regenerate app/lib/api from backend/schema/openapi.json
npm run dev            # http://localhost:3000
```

Backend must be running (see `backend/README.md`). Default API base: `http://127.0.0.1:8000` (override with `NUXT_PUBLIC_API_BASE`).

## Build & preview

```powershell
npm run build
npm run preview        # node .output/server/index.mjs → http://localhost:3000
```

## Structure (modular)

```
app/
  assets/css/main.css        # Tailwind v4 entry
  components/templates/      # feature components (TemplateBuilder, …)
  composables/
    useApi.ts                # typed fetch wrapper + base URL
    useLiveFeed.ts           # WebSocket live feed (Channels)
  layouts/default.vue        # sidebar shell
  lib/
    api/                     # hey-api generated client (types.gen, sdk.gen)
    api-client.ts            # base URL helper
  pages/
    index.vue                # dashboard (metrics + recent runs)
    templates/index.vue      # template list
    templates/create.vue     # new template builder
    templates/[id].vue       # edit template
    connections/index.vue    # API connections CRUD + mock links
    settings/index.vue       # runtime UI settings (AppSetting API)
    audit/index.vue          # universal audit log viewer
  plugins/primevue.ts        # PrimeVue (Aura theme, dark-mode aware)
```

## Regenerating the API client

1. Export the schema from the backend: `python manage.py spectacular --file ../backend/schema/openapi.json`
2. `npm run api:generate`

## Deployment

- Static assets: served by the reverse proxy (see `backend/deploy/nginx.conf`).
- SSR server: `node .output/server/index.mjs` behind nginx, proxying `/api/*` and `/ws/*` to daphne.
