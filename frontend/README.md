<div align="center">

# 🎓 Sensei — Grounded AI Study Workspace

A multi-agent, **grounded** AI study platform. Upload your material and get
cited question banks, flashcards, study plans and revision sheets — every
output validated, grounded to source chunks, and gated by a human review
workflow before export.

[![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![React](https://img.shields.io/badge/React_19-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![TanStack Start](https://img.shields.io/badge/TanStack_Start-FF4154?logo=tanstack&logoColor=white)](https://tanstack.com/)
[![Vite](https://img.shields.io/badge/Vite-646CFF?logo=vite&logoColor=white)](https://vitejs.dev/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_v4-06B6D4?logo=tailwindcss&logoColor=white)](https://tailwindcss.com/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Frontend** — [github.com/joo156/sensei-ai](https://github.com/joo156/sensei-ai) ·
**Backend** — [github.com/MoHatemTC/ai-content-agents](https://github.com/MoHatemTC/ai-content-agents)

</div>

---

## What it does

Students upload educational material (PDF, DOCX, PPTX, TXT) and Sensei turns it
into study content through a transparent RAG pipeline:

```
upload → parse → chunk → embed → retrieve → generate → validate → human review → export
```

- **7 AI agents** — Mentor, Concept Explanation, Question Bank, Test Help,
  Flashcards, Study Plan, Revision Assistant.
- **Grounded outputs** — every question/chat answer cites the exact source
  page and chunk it came from, with grounding and quality scores.
- **Human review gate** — approve / reject / needs-edit with comments and an
  audit trail. Export stays locked until content is approved.
- **Workspaces** — fully isolated docs, chats, generations and review history.
- **Global search** — across documents, questions, flashcards and history.
- **Analytics** — grounding, quality, Bloom's distribution, topic coverage.

## Screenshots

> _Screenshots go here — drop preview images into `public/screenshots/` and link
> them from this section._

## Tech stack

| Layer         | Technology                             |
| ------------- | -------------------------------------- |
| Framework     | TanStack Start (SSR) + TanStack Router |
| UI            | React 19 + Tailwind CSS v4 + shadcn/ui |
| Data fetching | TanStack Query                         |
| Animations    | motion                                 |
| Charts        | recharts                               |
| Icons         | lucide-react                           |
| Build         | Vite 8 + Nitro                         |
| Language      | TypeScript (strict)                    |

## Quick start

```bash
npm install
npm run dev        # http://localhost:8080 (mock mode on by default)
```

By default (`VITE_ENABLE_MOCK=true`) the app runs **fully offline** from
`src/mock` — every feature works without a backend.

### Demo accounts

| Role     | Email                | Password   |
| -------- | -------------------- | ---------- |
| Student  | `student@sensei.ai`  | `student@sensei.ai`  |
| Reviewer | `reviewer@sensei.ai` | `reviewer@sensei.ai` |
| Admin    | `admin@sensei.ai`    | `admin@sensei.ai`    |

## Running the full app (backend + frontend)

Sensei is two processes: the **FastAPI backend** (port `8000`) and this
**frontend** (port `8080`). The frontend talks to the backend through
`src/api/http.ts`.

```bash
# Backend  — https://github.com/MoHatemTC/ai-content-agents
cd ~/Desktop/ai-content-agents
./start-dev.sh                          # boots FastAPI on :8000

# Frontend — this repo
cd ~/Desktop/Sensei-AI
npm run dev                             # http://localhost:8080
```

See the backend repository's README for setup (LiteLLM key, Supabase URL/anon
key, JWT secret). The frontend leaves mock mode by setting
`VITE_API_BASE_URL=http://localhost:8000` and `VITE_ENABLE_MOCK=false` in
`.env.local`.

> If you see **"Unable to load your workspaces · Load failed"**, the backend is
> down — start it with `./start-dev.sh`.

## Architecture & data flow

```
component → hook/context → Service → *.api.ts → (mock | FastAPI/Supabase)
```

A component never imports `src/api` or `src/mock`. Every backend interaction
flows through a service:

- Workspace → `WorkspaceService` → `workspace.api.ts`
- Generation → `GenerationService` → `generation.api.ts` (via `AIProvider`)
- Chat → `ChatService` → `chat.api.ts`
- Review → `ReviewService` → `review.api.ts`
- Analytics → `AnalyticsService` → `analytics.api.ts`
- Auth → `AuthService` → `auth.api.ts` (Supabase-shaped)

```
src/
├── routes/        # File-based pages (TanStack Router)
├── components/    # ui/ (shadcn primitives) + app/ (feature components)
├── contexts/      # Auth, Workspace, Theme, Notification providers
├── hooks/         # Shared React hooks
├── services/      # Business logic — the only layer a backend swap touches
│   └── ai/        # AI provider abstraction (Mock / Gemini / Kimi / Nvidia)
├── api/           # Endpoint functions (one file per domain) + HTTP client
├── mock/          # Offline mock data layer
├── types/         # Domain models + database + API contracts
├── config/        # Env var reading with safe defaults
├── constants/     # Roles, permissions, storage keys
└── lib/           # Utilities (logger, error reporter, result envelope)
```

## Pages

`/home` · `/studio` · `/workspace` · `/library` · `/generate` · `/chat/:chatId` ·
`/review` · `/pipeline` · `/agents` · `/history` · `/analytics` · `/settings` ·
`/admin` · `/login` · `/reopen/:generationId`

## AI providers

`services/ai/AIProvider.ts` exposes one `AIProvider` interface over four
providers: **Mock**, **Gemini**, **Kimi**, **Nvidia**. In real mode each
provider id maps to the same FastAPI routes; the UI only passes the selected
model id.

## Roles & permissions

`src/constants/index.ts` holds `ROLE_PERMISSIONS`. Use
`useAuth().can("review:approve")` and guard pages with `<RoleGate>`. Never
write `role === "admin"` inside a component.

## Environment variables

Copy `.env.example` to `.env.local`. Only publishable keys belong in the
browser.

| Variable                    | Default   | Purpose                                    |
| --------------------------- | --------- | ------------------------------------------ |
| `VITE_API_BASE_URL`         | `/api`    | FastAPI base URL                           |
| `VITE_SUPABASE_URL`         | _(empty)_ | Supabase project URL                       |
| `VITE_SUPABASE_ANON_KEY`    | _(empty)_ | Supabase anon key (publishable)            |
| `VITE_ENABLE_MOCK`          | `true`    | Resolve from `src/mock` instead of network |
| `VITE_DEFAULT_MODEL`        | `mock`    | Default AI provider id                     |

## Development

```bash
npm run dev        # dev server (HMR) on :8080
npm run typecheck  # tsc --noEmit
npm run lint       # ESLint + Prettier
npm run format     # Prettier write
npm run build      # production build
npm run preview    # preview the production build
```

## Documentation

| Document | Contents |
| -------- | -------- |
| [Project Reference](docs/PROJECT_REFERENCE.md) | Full build reference — architecture, routes, services, integration status |
| [Frontend Architecture](docs/FRONTEND_ARCHITECTURE.md) | Layering rules, contexts, stores |
| [Development Guide](docs/DEVELOPMENT_GUIDE.md) | Local setup, environment, checks |
| [FastAPI Integration](docs/FASTAPI_INTEGRATION.md) | Endpoint reference with JSON shapes |
| [Backend Contract](docs/BACKEND_CONTRACT.md) | Action → endpoint → auth matrix |
| [Database Schema](docs/DATABASE_SCHEMA.md) | Supabase tables, relationships, RLS |
| [Contributing](CONTRIBUTING.md) | How to work in this repo |

## License

[MIT](LICENSE) — see the LICENSE file.
