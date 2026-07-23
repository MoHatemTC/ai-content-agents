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
- [Validation & Review Gate](docs/validation-lane.md)

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
    validation/      # Validation / guardrails / review lane
    exports/         # Export utilities
```

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

Fill in `.env` with your own keys. Never commit secrets. `MOCK_MODE=true` (the default) keeps every agent offline.

## Run

```bash
streamlit run src/app.py    # combined study-assistant UI
python -m pytest tests/     # full test suite
```

## Collaboration

Mentors and interns work in this repo in parallel — one lane per engineer, integrated only through the shared contracts documented in `docs/`. Task requirements and acceptance criteria live in the separate task pack / LMS, not in this repo.
