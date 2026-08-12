<div align="center">

# Content Agents

**Grounded, multi-agent study content generation from your own material.**

Upload a document and seven AI agents turn it into cited explanations,
question banks, flashcards, study plans and revision sheets — every claim
traceable to the source passage it came from, gated by human review before
export.

[![CI](https://github.com/MoHatemTC/ai-content-agents/actions/workflows/ci.yml/badge.svg)](https://github.com/MoHatemTC/ai-content-agents/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React_19-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)

</div>

---

## Contents

- [What it does](#what-it-does)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Repository layout](#repository-layout)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [Running the app](#running-the-app)
- [Testing](#testing)
- [Documentation](#documentation)
- [Troubleshooting](#troubleshooting)
- [Collaboration model](#collaboration-model)

---

## What it does

A student uploads educational material (PDF, DOCX, PPTX, TXT) and the platform
turns it into study content through a transparent retrieval-augmented
pipeline:

```
upload → parse → chunk → embed → retrieve → generate → validate → human review → export
```

- **Seven agents** — Mentor, Concept Explanation, Question Bank, Test Help,
  Flashcards, Study Plan, Revision Assistant.
- **Grounded, not guessed** — every answer, question and card cites the exact
  chunk and page it was drawn from. A reply that cites something outside the
  retrieved set is refused (`422 ungrounded_reply`) rather than served with an
  invented citation.
- **Human review gate** — every generated output is `PENDING` until a
  reviewer approves, rejects, or requests an edit, with comments and an
  audit trail. Export stays locked until approval.
- **Workspaces** — isolated documents, chats, generations and history per
  workspace.
- **Two frontends, one backend** — a React/TanStack SPA (`frontend/`) for the
  product, and a Streamlit app (`src/app.py`) that reaches every agent
  directly, useful for demos and debugging the pipeline without the full UI.

## Architecture

```
                    ┌─────────────────────────┐
                    │   frontend/ (React)     │  :8080
                    │   TanStack Start + Vite │
                    └───────────┬─────────────┘
                                │  REST (Bearer <Supabase JWT>)
                    ┌───────────▼─────────────┐
                    │   backend/ (FastAPI)    │  :8000
                    │   auth · workspaces ·   │
                    │   documents · search ·  │
                    │   generation · chat ·   │
                    │   review · exports      │
                    └───────────┬─────────────┘
                                │  imports, does not duplicate
                    ┌───────────▼─────────────┐
                    │   src/ (domain layer)   │
                    │   agents · ingestion ·  │
                    │   retrieval · study ·   │
                    │   validation · exports  │
                    └───────────┬─────────────┘
                                │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                  ▼
        SQLite (state)     Chroma (vectors)   LiteLLM gateway
```

`backend/` is a thin HTTP layer: routers, request/response schemas and error
envelopes. The actual agents, retrieval, ingestion and review logic live once,
in `src/`, and are imported — not reimplemented — by both the FastAPI backend
and the Streamlit app. [`docs/agent-parity.md`](docs/agent-parity.md) tracks
where the two entry points have (and have had) to be kept in sync, since a fix
landing in one and not the other has been the most common defect class on this
project.

## Tech stack

| Layer | Technology |
|---|---|
| Backend framework | FastAPI + Pydantic v2 |
| Domain / agents | Python, OpenAI-compatible client (LiteLLM gateway) |
| Retrieval | ChromaDB (ONNX or hashing embedder) |
| Persistence | SQLite (`agent_runs`, `generated_outputs`, `reviews`, `documents`, `chunks`, …) |
| Auth | Supabase Auth (GoTrue), Bearer JWT |
| Frontend framework | TanStack Start (SSR) + TanStack Router |
| UI | React 19 + Tailwind CSS v4 + shadcn/ui |
| Data fetching | TanStack Query |
| Build | Vite 8 + Nitro |
| Language | TypeScript (strict) / Python 3.10+ |
| Secondary UI | Streamlit (`src/app.py`, `src/validation/ui.py`) |
| Testing | pytest (backend/domain), `tsc --noEmit` + ESLint (frontend) |
| CI | GitHub Actions — pytest + ruff on every PR |

## Repository layout

```text
ai-content-agents/
├── backend/                    FastAPI HTTP layer
│   ├── auth/                     Supabase-backed auth, dev scaffold login
│   ├── workspaces/                Workspace CRUD
│   ├── documents/                 Upload, parse, chunk, embed
│   ├── search/                    Cross-document search, grounded-context retrieval
│   ├── generation/                Question bank, test help, flashcards, study plan, revision
│   ├── chat/                      Mentor + Concept chat
│   ├── review/                    Human review queue, approve/reject/needs-edit, audit
│   ├── exports/                   Approved-output exporters
│   ├── history/                   Generation history
│   ├── admin/                     Site-wide stats (staff only)
│   └── main.py                    App factory — composes every router above
│
├── frontend/                   React + TanStack UI (vendored via git subtree from joo156/sensei-ai)
│   └── src/
│       ├── routes/                File-based pages
│       ├── components/            ui/ (shadcn primitives) + app/ (feature components)
│       ├── services/              Business logic layer
│       ├── api/                   One file per backend domain + HTTP client
│       └── mock/                  Offline mock data (VITE_ENABLE_MOCK=true)
│
├── src/                        Domain layer — imported by backend/ and src/app.py alike
│   ├── agents/                    Mentor, Concept, Question Bank, Test Help
│   ├── study/                     Flashcards, Study Plan, Revision (+ prompts)
│   ├── ingestion/                 Parsing, chunking, quality checks, OCR
│   ├── retrieval/                 Chroma index, grounding, structure labelling
│   ├── prompts/                   YAML prompt templates for src/agents
│   ├── schemas/                   Shared output schemas
│   ├── validation/                Review gate, orchestration, evaluation, export
│   ├── testing/                   Shared compliant test doubles
│   └── app.py                     Combined Streamlit app — every agent has a page here
│
├── docs/                       Lane documentation, deployment guide, agent-parity matrix
├── scripts/                    Benchmark and batch-run utilities
└── tests/                      pytest suite — backend, domain, and integration tests
```

All seven agents route their output through the review gate before it can be
exported, and the prompts share one shape (`name` / `description` / `role` /
`instructions` / `output_schema` / `notes` / `prompt_template`) whether they
live in `src/prompts/` or `src/study/`.

## Getting started

### Prerequisites

- Python 3.10+ (CI runs 3.12; developed on 3.14)
- Node.js 20+ and npm (for the frontend)
- A LiteLLM-compatible gateway key (or any OpenAI-compatible endpoint —
  OpenRouter works too)
- A Supabase project, if you want authenticated endpoints locally (optional —
  see [Configuration](#configuration))

### Backend

```bash
python -m venv .venv

.venv\Scripts\activate         # Windows
source .venv/bin/activate      # macOS / Linux

pip install -r requirements.txt

copy .env.example .env         # Windows
cp .env.example .env           # macOS / Linux
```

Fill in `.env` — see [Configuration](#configuration). At minimum,
`LITELLM_API_KEY` and `LITELLM_BASE_URL` are required: agents call the real
gateway and refuse to construct without them, rather than silently returning
canned output. Tests inject a fake client and never need a key.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local
```

Fill in `frontend/.env.local` to point at the backend — see
[Configuration](#configuration). Left at its defaults, the frontend runs
**fully offline** against `src/mock`, with no backend required.

## Configuration

### Backend (`.env`, project root)

| Variable | Default | Purpose |
|---|---|---|
| `LITELLM_BASE_URL` | — | **Required.** Gateway base URL. Any OpenAI-compatible endpoint works. |
| `LITELLM_API_KEY` | — | **Required.** Gateway key. Never commit the real value. |
| `DEFAULT_MODEL` | `kimi-k2.5` | Model requested from the gateway. |
| `PLATFORM_DB_PATH` | `ingestion.db` | SQLite file for `agent_runs`, `generated_outputs`, `reviews`, `documents`, etc. |
| `CHROMA_DIR` | _(unset → in-memory)_ | Where the retrieval index persists across restarts. |
| `RETRIEVAL_EMBEDDER` | `onnx` | `onnx` (semantic, ~80 MB one-time download) or `hashing` (offline, deterministic). Not interchangeable on an existing index. |
| `SUPABASE_URL` | — | Enables Supabase-authenticated endpoints. |
| `SUPABASE_ANON_KEY` | — | Paired with `SUPABASE_URL` for GoTrue token verification. |
| `SUPABASE_JWT_SECRET` | — | Optional: fast local HS256 verification instead of a GoTrue round trip. |
| `CORS_ORIGINS` | `*` | Comma-separated allowed origins for the FastAPI backend. |
| `ENABLE_OCR` | `false` | Scanned-PDF text extraction via Tesseract (needs the binary installed separately). |
| `MAX_UPLOAD_BYTES` | `36700160` (35 MB) | Largest file the ingestion lane accepts. |

Full reference with rationale for every value: [`.env.example`](.env.example).
Leaving Supabase unset still runs `/health` and the dev-scaffold login; every
other endpoint returns `401`.

### Frontend (`frontend/.env.local`)

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | `/api` | FastAPI base URL. Left at `/api`, the app stays in mock mode regardless of `VITE_ENABLE_MOCK`. |
| `VITE_ENABLE_MOCK` | `true` | Resolve from `src/mock` instead of the network. |
| `VITE_SUPABASE_URL` | — | Must match the backend's `SUPABASE_URL` or tokens will not verify. |
| `VITE_SUPABASE_ANON_KEY` | — | Publishable key — safe for the browser. |
| `VITE_DEFAULT_MODEL` | `mock` | Default model id in the selector. |

To run against the real backend: set `VITE_API_BASE_URL=http://localhost:8000`
and `VITE_ENABLE_MOCK=false`.

## Running the app

**Backend** (from the project root, with `.venv` active):

```bash
uvicorn backend.main:app --reload --port 8000
```

`backend/main.py` loads `.env` from an absolute path, so this works from any
working directory. Health check: `curl http://127.0.0.1:8000/health`.

**Frontend**:

```bash
cd frontend
npm run dev        # http://localhost:8080
```

**Demo accounts** (seeded in the configured Supabase project):

| Role | Email | Password |
|---|---|---|
| Student | `student@sensei.ai` | `student@sensei.ai` |
| Reviewer | `reviewer@sensei.ai` | `reviewer@sensei.ai` |
| Admin | `admin@sensei.ai` | `admin@sensei.ai` |

Without Supabase configured, a temporary dev-scaffold login seeds
`student@demo.com` / `reviewer@demo.com` / `admin@demo.com` (passwords
`student` / `reviewer` / `admin`) directly into the backend's own SQLite
`users` table — see [`backend/auth/seed.py`](backend/auth/seed.py). This
scaffold is removed once Supabase is the only auth path.

**Other entry points:**

```bash
streamlit run src/app.py               # combined study-assistant UI, every agent
streamlit run src/validation/ui.py     # review / history / export / metrics
python -m src.validation.automation    # batch run + quality report
```

## Testing

```bash
python -m pytest tests/ -q             # full suite
python -m ruff check src/ tests/       # lint (F-rules enforced in CI)
```

```bash
cd frontend
npm run typecheck                      # tsc --noEmit
npm run lint                           # ESLint + Prettier
```

The suite runs credential-free: agents take an injected client, and a test
that forgets to inject a double fails loudly instead of quietly billing the
gateway. Two opt-in lanes exist for when credentials are available:

```bash
RUN_LIVE_TESTS=true python -m pytest tests/test_question_bank_live.py -v
RUN_DEEPEVAL_TESTS=true python -m pytest -m deepeval    # needs pip install -e ".[eval]"
```

Neither runs in CI — live tests need real credentials, and DeepEval scores are
non-deterministic and cost money per run.

## Documentation

| Document | Contents |
|---|---|
| [Agent parity matrix](docs/agent-parity.md) | What each lane does and does not do, so a fix in one entry point doesn't silently miss the other |
| [Retrieval & grounding](docs/retrieval-lane.md) | Chunk indexing, `RetrievalScope`, grounding verification |
| [Content ingestion](docs/content-ingestion-lane.md) | Parsing, chunking, quality checks |
| [Study agents](docs/study-agent%20lane.md) | Flashcards, Study Plan, Revision |
| [Mentor & Concept](docs/mentor-concept-lane.md) | Explanation agents |
| [Review, validation & export](docs/validation-lane.md) | Human review gate, orchestration, exporters |
| [Deployment guide](docs/deployment.md) | Configuration, running, troubleshooting (Streamlit-focused; see this README for the FastAPI path) |
| [OCR & content quality](docs/ocr-and-content-quality.md) | Tesseract and vision-OCR fallbacks for scanned PDFs |

## Troubleshooting

**Backend fails to start: `sqlite3.OperationalError: no such column: workspace_id`.**
`PLATFORM_DB_PATH` defaults to `ingestion.db`, which the older ingestion lane
also writes to with a different `documents` schema. Point the backend at its
own file:

```bash
PLATFORM_DB_PATH=backend_preview.db uvicorn backend.main:app --reload --port 8000
```

**Frontend shows "Unable to load your workspaces · Load failed".**
The backend isn't running, or `VITE_API_BASE_URL` / `VITE_ENABLE_MOCK` in
`frontend/.env.local` don't point at it.

**`npm run lint` fails across the whole repo, not just changed files.**
Pre-existing on Windows checkouts with `core.autocrlf=true` — ESLint trips on
line-ending normalization repo-wide. Not caused by any one change; check
`git config core.autocrlf` if you hit this.

**A generated reply comes back `422 ungrounded_reply` or `502 invalid_model_reply`.**
Working as designed, not a bug: `422` means the model cited a chunk it wasn't
given (refused rather than served with a fabricated citation); `502` means the
reply couldn't be parsed as valid JSON at all. Both are recorded as failed
runs, visible in History.

**`Cannot reach the LLM gateway: LITELLM_API_KEY and LITELLM_BASE_URL are not
both set`.** There is no offline fallback by design — set both. Upload, the
library and the review queue keep working; only generation is blocked.

More scenarios, including gateway-side failure modes, are in
[`docs/deployment.md`](docs/deployment.md), section 6.

## Collaboration model

Contributors own a vertical slice ("lane") — ingestion, retrieval, study
agents, mentor/concept, or the review/validation platform — integrated only
through the contracts documented in `docs/`. The FastAPI backend and the
Streamlit app are two entry points into the same domain layer in `src/`; when
changing agent or retrieval behavior, check
[`docs/agent-parity.md`](docs/agent-parity.md) for whether both need updating.

Conventional-commit-style messages (`feat(...)`, `fix(...)`, `docs(...)`,
`refactor(...)`) and one logical change per commit are used throughout the
history — `git log` is a reasonable place to see the pattern in practice.
