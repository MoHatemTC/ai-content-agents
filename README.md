# Content Agents

Group project for the **Content Agents Intermediate** internship track — AI agents that generate grounded study content (explanations, questions, flashcards, study plans) from uploaded educational material.

## Stack

- **Python**
- **Streamlit** (frontend)
- **FastAPI** + **Pydantic** (backend)
- **SQLite** (persistence)

## Lane documentation

Each engineer owns a vertical slice ("lane"); the docs describe the contracts:

- [Content Ingestion & Processing](docs/content-ingestion-lane.md)
- [Study Agents (Flashcards, Study Plan, Revision)](docs/study-agent%20lane.md)
- [Mentor & Concept Agents](docs/mentor-concept-lane.md)
- [Retrieval & Grounding](docs/retrieval-lane.md)
- [Review, Validation, Orchestration & Export](docs/validation-lane.md)
- [Agent parity matrix](docs/agent-parity.md) — what each lane does and does not do, so a fix that lands in one lane is not silently missing from the other two

[Deployment guide](docs/deployment.md) — configuration, running, troubleshooting.

## Folder map

```text
content-agents/
  frontend/          # React + TanStack UI, vendored from joo156/sensei-ai
  backend/           # Reserved for the FastAPI layer (see PR #36)
  docs/              # Lane and architecture docs
  tests/             # Test suite (pytest)
  src/
    app.py           # Combined Streamlit app — every agent has a page here
    agents/          # Mentor, Concept, Question Bank, Test Help
    study/           # Flashcards, Study Plan, Revision (+ their prompts)
    ingestion/       # Content ingestion & processing lane
    prompts/         # Prompt templates for src/agents (YAML)
    retrieval/       # Retrieval / grounding lane
    schemas/         # Flashcard output schemas
    services/        # Shared services
    validation/      # Review, validation, orchestration & export platform
    exports/         # Approved-output exporters (JSON / CSV / Markdown / PDF)
```

All seven agents are reachable from `src/app.py`, and every one of them routes
its output through the review gate before it can be exported. The prompts come
in one shape — `name` / `description` / `role` / `instructions` /
`output_schema` / `notes` / `prompt_template` — whether they live in
`src/prompts/` or `src/study/prompts/`.

The `validation/` package is the platform layer that connects the other lanes:
`orchestrator` runs agents, `integration` chains ingest → retrieve → generate →
validate, `review_service` + `ui` are the human review gate, `store` persists
`agent_runs` / `generated_outputs` / `reviews`, `automation` runs it in batch and
`evaluation` measures the result.

## Frontend

`frontend/` is the React + TanStack UI, vendored from
[joo156/sensei-ai](https://github.com/joo156/sensei-ai) with `git subtree` so
the whole product is one clone on one branch.

**It is a subtree, not a fork.** The upstream repo is still where the frontend
is developed, so pull rather than diverge:

```bash
git subtree pull --prefix frontend https://github.com/joo156/sensei-ai main --squash
```

If a change is made here that belongs upstream, push it back rather than
letting the two drift:

```bash
git subtree push --prefix frontend https://github.com/joo156/sensei-ai <branch>
```

Run it against the FastAPI layer:

```bash
cd frontend
npm install
cp .env.example .env.local     # then fill in
npm run dev
```

`.env.local` needs `VITE_API_BASE_URL=http://localhost:8000`,
`VITE_ENABLE_MOCK=false`, and `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY`
pointing at the **same** Supabase project as the backend's `SUPABASE_*`, or the
JWT will not verify. Leaving `VITE_API_BASE_URL` at its `/api` default keeps the
app in mock mode however `VITE_ENABLE_MOCK` is set, so it never calls the
backend at all.

CI lints and tests `src/`, `tests/` and `scripts/` only; the frontend has its
own `npm run lint` and `npm run typecheck`.

## Setup

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # Windows
# cp .env.example .env   # macOS / Linux
```

Fill in `.env` with your own keys. Never commit secrets. The agents call the
gateway for real; without `LITELLM_API_KEY` and `LITELLM_BASE_URL` they refuse
to construct rather than quietly returning canned text. Tests inject a fake
client and never need a key.

## Run

The FastAPI backend serves the Sensei frontend on port `8000`:

```bash
.venv/bin/python -c "
import os
from dotenv import load_dotenv
load_dotenv('.env', override=False)
os.environ.pop('SUPABASE_JWT_SECRET', None)
import uvicorn
uvicorn.run('backend.main:app', host='127.0.0.1', port=8000)
"
```

Or simply:

```bash
~/Desktop/Sensei-AI/start-dev.sh   # starts this backend AND the frontend together
~/Desktop/Sensei-AI/start-dev.sh status   # check what is running
~/Desktop/Sensei-AI/start-dev.sh stop     # stop both
```

- `backend/main.py` loads `.env` from an absolute path, so uvicorn works from
  any working directory.
- `SUPABASE_JWT_SECRET` is dropped at launch so the backend verifies Supabase
  access tokens via GoTrue (local HS256 verification breaks login).
- Health check: `curl http://127.0.0.1:8000/health`.
- **The backend stops on laptop shutdown** — after a reboot run
  `start-dev.sh` again before using the frontend, or the app shows
  "Unable to load your workspaces / Load failed".

Other entrypoints:

```bash
streamlit run src/app.py               # combined study-assistant UI
streamlit run src/validation/ui.py     # review / history / export / metrics
python -m src.validation.automation    # batch run + quality report
python -m pytest tests/                # full test suite
```

## Collaboration

Mentors and interns work in this repo in parallel — one lane per engineer, integrated only through the shared contracts documented in `docs/`. Task requirements and acceptance criteria live in the separate task pack / LMS, not in this repo.
