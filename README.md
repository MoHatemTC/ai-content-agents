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

[Deployment guide](docs/deployment.md) — configuration, running, troubleshooting.

## Folder map

```text
content-agents/
  frontend/          # Streamlit UI (per-lane pages)
  backend/           # FastAPI integration entrypoint
  docs/              # Lane and architecture docs
  tests/             # Test suite (pytest)
  src/
    app.py           # Combined study-assistant Streamlit app
    agents/          # Agent implementations (mentor, concept, ...)
    generation/      # Study-agents generation lane
    ingestion/       # Content ingestion & processing lane
    prompts/         # Prompt templates (YAML)
    registry/        # Study-agents registry
    retrieval/       # Retrieval / grounding lane
    schemas/         # Study-agents output schemas
    services/        # Shared services
    validation/      # Review, validation, orchestration & export platform
    exports/         # Approved-output exporters (JSON / CSV / Markdown / PDF)
```

The `validation/` package is the platform layer that connects the other lanes:
`orchestrator` runs agents, `integration` chains ingest → retrieve → generate →
validate, `review_service` + `ui` are the human review gate, `store` persists
`agent_runs` / `generated_outputs` / `reviews`, `automation` runs it in batch and
`evaluation` measures the result.

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
