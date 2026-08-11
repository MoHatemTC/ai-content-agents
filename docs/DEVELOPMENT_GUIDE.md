# Development Guide

Practical guide to running and extending the Sensei frontend.

## Run locally

```bash
npm install
npm run dev      # http://localhost:8080
```

With `VITE_ENABLE_MOCK=true` (default) everything works offline from `src/mock` —
no backend required.

To run against the real FastAPI backend, set `.env.local` (see the
[README](README.md#running-the-full-app-backend--frontend)).

## Environment

Copy `.env.example` to `.env.local`:

```
VITE_API_BASE_URL=http://localhost:8000
VITE_SUPABASE_URL=
VITE_SUPABASE_ANON_KEY=
VITE_ENABLE_MOCK=false
VITE_DEFAULT_MODEL=gemini
```

Only publishable keys (the Supabase anon key) belong in the browser.

## Golden rules

1. UI never imports `src/api` or `src/mock`.
2. Services are the only place backend behaviour changes.
3. Role checks go through `useAuth().can()` / `RoleGate`.
4. Workspace-owned data comes from `useWorkspace()`; never filter by workspace in a page.
5. All network access flows through `src/api/http.ts` (single token holder,
   single error-shaping path).

## How the pieces connect

The backend ([ai-content-agents](https://github.com/MoHatemTC/ai-content-agents))
is the single source of persisted behaviour:

1. **Auth** — the backend is Supabase-first: it verifies the Supabase JWT on
   every request (local HS256 or GoTrue introspection) and auto-provisions the
   platform user on first login. `auth.api.ts` + `AuthService` exchange the
   Supabase session for a Bearer token; `AuthContext`, `RoleGate` and pages
   stay as-is.
2. **Database** — Supabase migrations live in `supabase/migrations/`
   (identity, RLS, storage, realtime, review workflow, favorites, pipeline
   telemetry). See `docs/DATABASE_SCHEMA.md`.
3. **Storage** — backend-owned; the frontend only keeps document metadata.
   Uploads go through `POST /upload`.
4. **API** — `src/api/paths.ts` is the single endpoint map; each domain has an
   api module (`*.api.ts`) and a service (`src/services/`). Every function
   checks `isMockMode()`: mock data now, `http.*` when real.
5. **AI models** — `services/ai/AIProvider.ts` routes each model id to the same
   backend endpoints (`/generate/*`, `/chat`). `ModelService` lists models.
6. **Review workflow** — reviewer actions hit `/review/*`; the review queue is
   hydrated from Supabase (`generation_with_creator`) and decisions roll the
   generation status up per item.
7. **Realtime** — notifications/reviews subscriptions are wired via Supabase
   (migration `013_realtime_and_notifications.sql`); components re-render
   automatically.

## Checks before shipping

```bash
npm run typecheck   # npx tsc --noEmit
npm run lint        # ESLint + Prettier
npm run build       # production build
```

## Adding an endpoint

1. Add the path to `src/api/paths.ts`.
2. Add the contract to `src/types/api/*.contracts.ts`.
3. Add the api function in the matching `src/api/*.api.ts` module.
4. Expose it through a service in `src/services/`.
5. Update `docs/FASTAPI_INTEGRATION.md` + `docs/BACKEND_CONTRACT.md`.

## Production deployment

- Frontend: `npm run build` + any static/edge host. Set the `VITE_*` vars in
  the deploy environment; only publishable keys belong in the browser.
- Backend: containerise, expose HTTPS, allow the frontend origin via CORS,
  keep the Supabase service role and model API keys server-side only.
- Database: migrations in version control, RLS enabled everywhere, backups on.
- Observability: log request ids from `http.ts` errors, monitor model latency
  and rate limits (429), alert on grounding-score drops.
