# Content Agents

Starter boilerplate for the **Content Agents Intermediate** internship track.

Non-gating folder map only — no sprint solutions, agent logic, retrieval, DB, or UI implementation. Mentors and interns clone (or fork) this repo and implement deliverables under the folders below. Task requirements live in the separate task pack / LMS, not in this repo.

## Stack

- **Python**
- **Streamlit** (frontend)
- **FastAPI** + **Pydantic** (backend)
- **SQLite** (persistence)

## Folder map

```text
content-agents/
  frontend/          # Streamlit UI
  backend/           # FastAPI integration entrypoint
  docs/              # Architecture and integration docs
  tests/             # Tests
  src/
    agents/          # Agent implementations
    prompts/         # Prompt templates
    services/        # Shared services
    retrieval/       # Retrieval / grounding
    validation/      # Validation / guardrails
    exports/         # Export utilities
```

Implement sprint deliverables in the matching folders (`docs/`, `src/prompts/`, `backend/`, etc.). Do not treat this repo as a completed solution.

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

Fill in `.env` with your own keys. Never commit secrets.

## Collaboration

Mentors and interns work in this repo (or forks) in parallel. Use the task pack for acceptance criteria; use this tree only as the shared project layout.