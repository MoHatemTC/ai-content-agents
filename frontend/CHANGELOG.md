# Changelog

All notable changes to the Sensei frontend are documented here. This project
follows [Semantic Versioning](https://semver.org/). The changelog is
maintained in reverse chronological order.

## [1.0.0] - 2026-08

### Added

- Real end-to-end integration with the FastAPI backend
  ([ai-content-agents](https://github.com/MoHatemTC/ai-content-agents)):
  - Supabase-first auth — the backend verifies Supabase JWTs and
    auto-provisions platform users on first login.
  - Live workspace CRUD, upload (parse → chunk → embed), document library,
    search, grounded question generation, chat, review queue and export.
  - `ExportService` with object-URL downloads (CSV/JSON, approved content only).
  - `BackendStatus` banner probing `GET /health`.
  - `.env.example` documenting `VITE_API_BASE_URL`, `VITE_SUPABASE_URL`,
    `VITE_SUPABASE_ANON_KEY`, `VITE_ENABLE_MOCK`, `VITE_DEFAULT_MODEL`.
- Supabase migrations for identity, RLS, storage, realtime, review workflow,
  favorites and pipeline telemetry.
- Project documentation set: `README.md`, `CONTRIBUTING.md`,
  `docs/PROJECT_REFERENCE.md`, `docs/FRONTEND_ARCHITECTURE.md`,
  `docs/DEVELOPMENT_GUIDE.md`, `docs/FASTAPI_INTEGRATION.md`,
  `docs/BACKEND_CONTRACT.md`, `docs/DATABASE_SCHEMA.md`.

### Removed

- Dead components and modules (never imported): `agent-icons.ts`, `RagFlow`,
  `OutputCard`, `StatusBadge`, `usePermissions`, `mock/users.ts`,
  `mock/workspace-data.ts`, and unused api/types barrel `index.ts` files.
- Outdated planning artifacts (`ROADMAP.md`) and superseded integration notes
  (`docs/SUPABASE_INTEGRATION.md`, root-level `PHASE*.txt`, `e2e-deliverables/`).

### Fixed

- Lint (Prettier) errors in `WorkspaceContext.tsx`, `review.tsx`,
  `ReviewService.ts`.
- Stale documentation: `VITE_SUPABASE_ANON_KEY` naming, npm (not bun)
  commands, endpoint inventory aligned with `src/api/paths.ts`.

## [Unreleased]

### Planned

- CI/CD pipeline (typecheck → lint → test → build → deploy).
- Deployment presets (Nitro) and observability dashboards.
- Realtime review-queue updates on the review page.
