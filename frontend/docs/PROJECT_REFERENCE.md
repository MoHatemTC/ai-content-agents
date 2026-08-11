# Sensei — Frontend Project Reference

Comprehensive reference for the **Sensei** grounded AI study platform frontend.
Covers the architecture, every route, service, data layer, state model, auth,
mock strategy, AI provider abstraction, and the real FastAPI integration that
is proven end-to-end against the live backend.

> Status: **stable, buildable, type-checked, linted**. The working branch is kept
> green at all times; this document reflects the current source tree.

---

## 1. Overview

Sensei is a multi-agent, grounded AI study platform. Students upload educational
material (PDF, DOCX, PPTX, TXT) and the platform converts it into cited question
banks, flashcards, study plans and revision sheets through a transparent RAG
pipeline: upload → parse → chunk → embed → retrieve → generate → validate →
human review → export. Every output is grounded back to source chunks and gated
by a human review workflow before it can be exported.

The **frontend** is a production-quality TanStack Start (SSR) application built
with strict layering so that a real FastAPI backend and Supabase identity can be
connected **without touching UI code**. The frontend already talks to the real
FastAPI backend in non-mock mode; mock mode remains the default for fully
offline development.

## 2. Architecture

Layered, top → bottom. Data flows **down**; a layer may only import from the
layers below it.

```
routes/ + components/   UI only — no fetching, no mock imports, no role logic
contexts/ + hooks/      React state: Auth, Workspace, Theme, Notifications
services/               Business logic — the ONLY layer a backend swap touches
  └─ services/ai/       AIProvider abstraction (Mock / Gemini / Kimi / Nvidia)
api/                    One endpoint file per domain + the http client + paths
mock/                   Offline fake data (mock-data.ts, studio-data.ts)
types/ + types/api/     Domain models + database + request/response contracts
config/ + constants/    Env placeholders, roles, permissions, storage keys
lib/                    Utilities (logger, error reporter, result envelope)
```

Guarantee: **a component never imports `src/api` or `src/mock`.** Every backend
interaction flows through a service. See [docs/FRONTEND_ARCHITECTURE.md](docs/FRONTEND_ARCHITECTURE.md).

### Data flow

```
component → hook/context → Service → *.api.ts → (mock | FastAPI/Supabase)
```

- Mock mode (`isMockMode()`) resolves from `src/mock` — fully offline.
- Real mode delegates to `http.*` (the single client in `src/api/http.ts`) which
  talks to FastAPI via `VITE_API_BASE_URL`.

## 3. Route Mapping

File-based routing (TanStack Router) in `src/routes/`. Page → purpose → backend:

| Route file             | Path                  | Purpose | Backend |
| ---------------------- | --------------------- | ------- | ------- |
| `index.tsx`            | `/`                   | Redirect shell (to `/home`) | — |
| `__root.tsx`           | (root)                | Mounts QueryClient → Auth → Workspace providers | — |
| `login.tsx`            | `/login`              | Sign in (Supabase-shaped) | `auth.api.ts` → `POST /auth/login`, Supabase GoTrue |
| `home.tsx`             | `/home`               | Dashboard + `BackendStatus` banner | `analytics.api`, `catalogue.api` |
| `studio.tsx`           | `/studio`             | Upload + generate console | `document.api`, `generation.api` |
| `workspace.tsx`        | `/workspace`          | Workspace CRUD (switch/create/rename/delete) | `workspace.api.ts` → `/workspaces` |
| `library.tsx`          | `/library`            | Uploaded documents, parse/chunk/embed state | `document.api.ts` |
| `generate.tsx`         | `/generate`           | Question/flashcard generation | `generation.api.ts` |
| `chat.$chatId.tsx`     | `/chat/:chatId`       | Agent chat threads | `chat.api.ts` |
| `review.tsx`           | `/review`             | Approve/reject/needs-edit, audit trail, export | `review.api.ts`, `export.api.ts` |
| `pipeline.tsx`         | `/pipeline`           | Visualised RAG pipeline stages | — (static) |
| `agents.tsx`           | `/agents`             | 7-agent catalogue | `catalogue.api.ts` |
| `history.tsx`          | `/history`            | Generation history | `history.api.ts` |
| `analytics.tsx`        | `/analytics`          | Grounding/quality/Bloom/topic charts | `analytics.api.ts` |
| `settings.tsx`         | `/settings`           | Profile + preferences | — |
| `admin.tsx`            | `/admin`              | Admin (role-gated) | `admin.api.ts` |
| `reopen.$generationId.tsx` | `/reopen/:generationId` | Re-open a past generation | `generation.api.ts` |
| `sitemap[.]xml.ts`     | `/sitemap.xml`        | SEO sitemap | — |

`src/routes/README.md` documents route conventions.

## 4. Services

`src/services/` — business logic; the only layer that changes when backend
behaviour changes.

| Service | Responsibility |
| ------- | -------------- |
| `AuthService` | login/logout/session restore/persist; Supabase-shaped session |
| `WorkspaceService` | workspace CRUD + per-workspace data bootstrap |
| `DocumentService` | document listing, patch, delete |
| `UploadService` | upload → parse → chunk → embed orchestration |
| `GenerationService` | question/flashcard generation via `AIProvider` |
| `ChatService` | agent chat threads + messages |
| `ReviewService` | review queue, decide (approve/reject/needs-edit/flag), audit |
| `HistoryService` | generation history |
| `AnalyticsService` | grounding/quality/Bloom/topic analytics |
| `ExportService` | export approved content (CSV/JSON) + object-URL download |
| `SearchService` | global search across docs/questions/flashcards/history |
| `AdminService` | admin features (seeded from mock in mock mode) |
| `AgentService` | 7-agent catalogue |
| `NotificationService` | notification feed |
| `ModelService` | AI model list + default |
| `FavoriteService` | favourite docs/items |
| `ContentService` | content convenience facade |
| `index.ts` | service barrel |
| `ai/AIProvider.ts` | the AI provider interface + registry |

## 5. Data Layer

- `src/api/` — one file per domain: `auth`, `workspace`, `document`,
  `generation`, `chat`, `review`, `history`, `analytics`, `admin`, `model`,
  `search`, `export`, `catalogue`, `supabase`; plus `http.ts` (the single HTTP
  client + access-token holder + error shaping) and `paths.ts` (endpoint map).
- `src/mock/` — `mock-data.ts` (documents, flashcards, history, questions,
  analytics seeds) and `studio-data.ts` (workspaces, notifications, rag stages).
  Consumed only by `src/api/*` and one service.
- `src/types/` — `domain.ts` (domain model), `database.types.ts` (Postgres
  shapes), `types/api/*.contracts.ts` (request/response contracts).

All network access flows through `src/api/http.ts` — exactly one access-token
holder and one error-shaping path.

## 6. State Management

React Contexts (one consistent pattern), mounted in `__root.tsx`:

- `AuthContext` — `login`, `signIn`, `logout`, `refreshSession`,
  `getCurrentUser`, `hasRole`, `can`. Shaped like Supabase Auth.
- `WorkspaceContext` — single source of `activeWorkspaceId`; exposes
  `useWorkspace().data` already scoped to the active workspace. Pages never
  filter by workspace themselves.
- Theme context (`components/app/theme.tsx`) — dark/light.

Per-page UI state (generation form, chat input, current document) stays local to
the page but is always fed by services. Notifications come through the mock
layer with role filtering.

## 7. Auth & Roles

- Roles: `student`, `reviewer`, `admin`.
- `src/constants/index.ts` holds `ROLE_PERMISSIONS` (per-role permission map).
- Role checks go through `useAuth().can("review:approve")` and `<RoleGate>`
  (route guard by role) — **never** inline `role === "admin"`.
- In real mode the backend verifies Supabase JWTs (HS256 local verify, or GoTrue
  introspection) and auto-provisions the platform user on first login.
  `AuthService` returns a fresh Bearer token used for all API calls.

## 8. Mock Strategy

`VITE_ENABLE_MOCK=true` (default) keeps the app fully offline:

- Demo accounts (`student@sensei.ai` / `reviewer@sensei.ai` / `admin@sensei.ai`).
- Seeded workspaces, pre-chunked documents, generated questions, flashcards,
  chats, history and review data.
- Every feature works: login, workspace switching, generation, review, analytics.

Each `*.api.ts` function checks `isMockMode()`: resolve from `src/mock` now,
`http.*` when mock is off. Flipping `VITE_ENABLE_MOCK=false` + a valid
`VITE_API_BASE_URL` switches the whole app to the real backend.

## 9. AI Provider Abstraction

`src/services/ai/AIProvider.ts` exposes one `AIProvider` interface over four
providers — **Mock**, **Gemini**, **Kimi**, **Nvidia** — and `getProvider(id)`.
`GenerationService` and `ChatService` resolve the provider from the selected
model id; the UI only passes the model id. In real mode each provider id maps to
the same FastAPI `/generate` and `/chat` routes; `ModelService` lists the
available models and the default (`VITE_DEFAULT_MODEL`).

## 10. Workspace Model

- Workspaces are the **isolation boundary**: docs, chunks, questions,
  flashcards, chats, history and review state are all workspace-owned.
- `WorkspaceContext` holds a per-workspace store seeded from
  `WorkspaceService`; switching a workspace switches everything.
- `workspace.api.ts` → `GET/POST/PATCH/DELETE /workspaces` in real mode
  (FastAPI), `src/mock/studio-data.ts` in mock mode.
- `WeakTopics` per workspace drive the "focus areas" shown on the dashboard.

## 11. Document Handling

- `document.api.ts` — real mode routes to FastAPI:
  `uploadDocument` → `POST /upload` (multipart `workspace_id` + file),
  `getDocuments` → `GET /documents?workspace_id=`,
  `updateDocument` → `PATCH /documents/{id}`,
  `deleteDocument` → `DELETE /documents/{id}`.
- Upload pipeline (library + studio): upload → parse → chunk → embed, with
  per-stage status surfaced in the UI.
- Storage is backend-owned; the frontend keeps only the document metadata.

## 12. Question Generation

- `generate.tsx` + `generation.api.ts` + `GenerationService`.
- Output types: MCQ / True-False / Short Answer; difficulty tiers, Bloom's
  classification, citations, quality score and grounding score.
- Real backend: `POST /generate/questions` returns grounded questions with
  `groundingInfo` and per-question citations.
- Re-generation (`reopen.$generationId.tsx`) allows reopening a past run.

## 13. Chat

- `chat.$chatId.tsx` + `chat.api.ts` + `ChatService`.
- Multi-turn threads per agent (Mentor, Concept Explanation, …) with model
  attribution and citations back to source chunks.
- Real backend: `POST /chat` with message history.

## 14. Review Workflow

- `review.tsx` + `review.api.ts` + `ReviewService`.
- Actions: **approve / reject / needs-edit / flag** with comments; audit trail;
  grounding/quality auto-flagging.
- Export stays locked until content is approved.
- Real backend: `GET /review/items?workspace_id=` (reload-safe queue),
  `POST /review` decide (clean 409 `illegal_transition` on invalid transitions),
  `GET /audit` history.

## 15. Export

- `export.api.ts` + `ExportService` + `src/types/api/export.contracts.ts`.
- Export **approved** content only to CSV or JSON.
- `ExportService.exportApproved` guards the approved count, produces an
  object-URL download, and toasts success/error.
- Real backend: `GET /exports` (CSV/JSON attachment; 403 `not_exportable` for
  unapproved items).

## 16. Notifications

- `NotificationService` + `NotificationCenter` (top-right feed).
- Mock-driven with role filtering; badges for the active user.
- In real mode, `NotificationService.subscribe()` listens to Supabase
  `postgres_changes` on the `notifications` table (migration
  `013_realtime_and_notifications.sql`) and re-renders the feed on INSERT.

## 17. Admin

- `admin.tsx` (role-gated via `<RoleGate role="admin">`) + `admin.api.ts`.
- Mock mode seeds admin analytics from `src/mock/mock-data.ts`;
  real mode reads from the FastAPI admin endpoints.

## 18. API Layer

`src/api/paths.ts` is the single endpoint map. Modules and their real-mode
targets:

| Module | Endpoints (real mode) |
| ------ | --------------------- |
| `auth.api.ts` | `POST /auth/login`, Supabase-shaped session |
| `workspace.api.ts` | `/workspaces` CRUD + per-workspace data |
| `document.api.ts` | `/upload`, `/documents`, `PATCH /documents/{id}`, `DELETE /documents/{id}` |
| `generation.api.ts` | `POST /generate/questions` (and flashcards) |
| `chat.api.ts` | `POST /chat` |
| `review.api.ts` | `GET /review/items`, `POST /review`, `GET /audit` |
| `history.api.ts` | generation history |
| `analytics.api.ts` | analytics summaries |
| `export.api.ts` | `GET /exports` (CSV/JSON download) |
| `admin.api.ts` | admin endpoints |
| `search.api.ts` | `GET /search?q=&workspace_id=` |
| `model.api.ts` | model catalogue |
| `catalogue.api.ts` | agents, notifications, rag stages |
| `supabase.api.ts` | Supabase client wiring |
| `http.ts` | single HTTP client, token holder, error shaping, blob download |

## 19. Config & Env

`src/config/env.ts` reads (safe defaults):

| Variable | Default | Purpose |
| -------- | ------- | ------- |
| `VITE_API_BASE_URL` | `/api` | FastAPI base URL |
| `VITE_SUPABASE_URL` | _(empty)_ | Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | _(empty)_ | Supabase anon key |
| `VITE_ENABLE_MOCK` | `true` | Resolve from `src/mock` instead of network |
| `VITE_DEFAULT_MODEL` | `mock` | Default AI provider id |

Only publishable keys belong in the browser. `.env.example` documents every
variable; `.env.local` is git-ignored.

## 20. Styling & UI Kit

- Tailwind CSS v4 + shadcn/ui primitives in `src/components/ui`.
- App-level components in `src/components/app`: `AppShell`, `RoleGate`,
  `ModelSelector`, `NotificationCenter`, `GlobalSearch`, `BackendStatus`,
  `AsyncState`, `StatCard`, `Pipeline`, `InteractiveQuiz`, `FlashcardDeck`,
  `QuestionCard`, `CitationChip`, `TeamSection`, `BrandMark`, badges, theme.
- motion (animations), recharts (analytics), lucide-react (icons).
- Dark & light themes, responsive layout, loading/error/empty states everywhere.

## 21. Backend Integration & Status

The frontend is **already wired** to the real FastAPI backend
([`ai-content-agents`](https://github.com/MoHatemTC/ai-content-agents), port
`8000`). The full vertical slice is proven end-to-end:

```
Supabase login → Supabase JWT → FastAPI JWT verify → authenticated API
  → workspace → upload → parse → chunk → embed → search → RAG generation
  → human review approve/reject → export
```

Verified live over HTTP against a real server (local-HS256 JWTs):

- `GET /workspaces` 200 (401 without token / bad signature)
- `POST /upload` → parse → chunk → embed → 200/201
- `GET /search?q=` → scored chunk hits
- `POST /generate/questions` → grounded questions, `grounding_score=100.0`
- `GET /review/items` → pending queue; `POST /review` approve/reject (+ audit)
- `GET /exports` CSV → approved rows only; unapproved → 403 `not_exportable`

`BackendStatus` (`src/components/app/BackendStatus.tsx`) probes `GET /health`
and shows a banner when the backend is reachable (mock panel in mock mode).

### Running

```bash
# backend (ai-content-agents repo, port 8000)
cd ~/Desktop/ai-content-agents && ./start-dev.sh   # or manual uvicorn

# frontend (this repo, port 8080)
cd ~/Desktop/Sensei-AI && npm run dev
```

### Known external blockers (not resolvable from source)

1. The committed Supabase **anon key** is invalid/revoked → real browser login
   needs a valid project anon key, or sign a local HS256 JWT.
2. The **LiteLLM** proxy token is flaky (401 `token_not_found_in_db` between
   runs) → needs a re-issued key for reliable generation.
3. Grounding guard is content/query dependent → some texts surface
   `InsufficientGroundingError` as HTTP 500 (backend-side behaviour).

## 22. Current Progress & Known Issues

### Progress

- ✅ Layered architecture with strict import rules (UI never touches api/mock).
- ✅ 15 pages + root + sitemap; every feature reachable in mock mode.
- ✅ Real FastAPI integration for auth, workspaces, documents, upload,
  generation, chat, review, analytics and export.
- ✅ `BackendStatus` health probe; `.env.example` for both apps.
- ✅ Type-check (`npm run typecheck`), lint, and production build all clean.
- ✅ Backend vertical slice verified with real HTTP + Gemini (grounding=100).

### Known issues

- `npm run lint` reports a small set of `react-refresh` warnings in the UI kit
  (non-blocking).
- Some backend test cases surface `InsufficientGroundingError` in the test
  environment (a chroma-persistence quirk in CI); the live server (on-disk
  chroma) works.
- The two external credential blockers listed in §21.

### Docs map (which file covers what)

| Topic | File |
| ----- | ---- |
| This project reference | `docs/PROJECT_REFERENCE.md` |
| Quick start + ops | `README.md` |
| Contributor guide | `CONTRIBUTING.md` |
| Architecture | `docs/FRONTEND_ARCHITECTURE.md` |
| Dev guide | `docs/DEVELOPMENT_GUIDE.md` |
| Backend contract | `docs/BACKEND_CONTRACT.md` |
| FastAPI integration | `docs/FASTAPI_INTEGRATION.md` |
| Database schema | `docs/DATABASE_SCHEMA.md` |
| Route conventions | `src/routes/README.md` |
