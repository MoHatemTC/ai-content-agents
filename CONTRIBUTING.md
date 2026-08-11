# Contributing to Sensei

Thanks for working on Sensei! This guide explains how the project is organised,
how to run it, and the conventions you must follow when you change code.

## Repository layout

Sensei is two repositories that run as one product:

| Component  | Repository                                                   | Port |
| ---------- | ------------------------------------------------------------ | ---- |
| Frontend   | [github.com/joo156/sensei-ai](https://github.com/joo156/sensei-ai) | 8080 |
| Backend    | [github.com/MoHatemTC/ai-content-agents](https://github.com/MoHatemTC/ai-content-agents) | 8000 |

This guide covers the **frontend** repository. The backend repo is a FastAPI
service that owns upload, chunking, embedding, retrieval, generation, review
and export; it verifies Supabase JWTs on every request.

## Getting started

```bash
npm install
npm run dev        # http://localhost:8080 (mock mode on by default)
```

No backend is needed for most work: `VITE_ENABLE_MOCK=true` (the default) runs
every feature offline against `src/mock`.

To run against the real backend, see [README → Running the full app](README.md).

## Project structure

```text
src/
├── routes/        # File-based pages (TanStack Router)
├── components/    # ui/ (shadcn primitives) + app/ (feature components)
├── contexts/      # Auth, Workspace, Theme, Notification providers
├── hooks/         # Shared React hooks
├── services/      # Business logic — the ONLY layer a backend swap touches
│   └── ai/        # AI provider abstraction (Mock / Gemini / Kimi / Nvidia)
├── api/           # Endpoint functions (one file per domain) + http client
├── mock/          # Offline mock data layer
├── types/         # Domain models + database + API contracts
├── config/        # Env var reading with safe defaults
├── constants/     # Roles, permissions, storage keys
└── lib/           # Utilities (logger, error reporter, result envelope)
docs/              # Architecture, contracts, schema, dev guide
supabase/          # SQL migrations (identity, RLS, storage)
```

## Engineering principles

1. **UI never imports `src/api` or `src/mock`** — always go through the service
   layer (`src/services`).
2. **Services are the only place backend behaviour changes.** When FastAPI or
   Supabase behaviour lands, only `src/api/*` and the relevant service internals
   change; components stay as-is.
3. **Role checks go through `useAuth().can()` / `<RoleGate>`** — never inline
   `role === "admin"` in a component.
4. **Workspace-owned data is read from `useWorkspace().data`**, already scoped
   to the active workspace. Pages never filter by workspace themselves.
5. **All network access flows through `src/api/http.ts`.** There is exactly one
   access-token holder and one error-shaping path.
6. **Never commit secrets.** Only publishable keys (e.g. the Supabase anon key)
   belong in the browser. The backend JWT secret stays in the backend `.env`.

## Data flow

```
component → hook/context → Service → *.api.ts → (mock | FastAPI/Supabase)
```

## Adding a feature or endpoint

1. Add the endpoint path to `src/api/paths.ts` **first**.
2. Add or extend the request/response contract in `src/types/api/*.contracts.ts`.
3. Add the api function in the matching `src/api/*.api.ts` module.
4. Expose it through a service in `src/services/`.
5. Update `docs/FASTAPI_INTEGRATION.md` and `docs/BACKEND_CONTRACT.md`.
6. Update the feature docs (README / `docs/PROJECT_REFERENCE.md`) if user-visible.

UI code should not change unless the feature is genuinely new.

## Verification

Run all three before pushing:

```bash
npm run typecheck   # npx tsc --noEmit — 0 errors expected
npm run lint        # ESLint + Prettier — 0 errors expected
npm run build       # production build (client + server bundle)
```

The working branch is expected to **build and type-check after every commit**.

## Git conventions

- Keep the working branch green and buildable at all times.
- Small, focused commits with descriptive messages.
- Do not rewrite or force-push published history.
- Match the existing commit style in `git log`.

## Documentation

Keep markdown accurate and up to date with the code — docs are part of the
deliverable:

- `README.md` — project overview, quick start, feature map, docs index.
- `CONTRIBUTING.md` — this file.
- `docs/PROJECT_REFERENCE.md` — the full build reference (architecture, routes,
  services, integration status).
- `docs/FRONTEND_ARCHITECTURE.md`, `docs/DEVELOPMENT_GUIDE.md`,
  `docs/FASTAPI_INTEGRATION.md`, `docs/BACKEND_CONTRACT.md`,
  `docs/DATABASE_SCHEMA.md` — layer-specific references.
