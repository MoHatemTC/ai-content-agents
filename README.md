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

```bash
streamlit run src/app.py               # combined study-assistant UI
streamlit run src/validation/ui.py     # review / history / export / metrics
python -m src.validation.automation    # batch run + quality report
python -m pytest tests/                # full test suite
```

## Collaboration

Mentors and interns work in this repo in parallel — one lane per engineer, integrated only through the shared contracts documented in `docs/`. Task requirements and acceptance criteria live in the separate task pack / LMS, not in this repo.
