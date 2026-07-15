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

---

# Sprint 1 – Mentor & Concept Agents Foundation

This sprint introduces the foundation for two educational AI agents:

- **Mentor Agent**
- **Concept Explanation Agent**

The implementation provides:

- Typed Pydantic output schemas
- YAML-based prompt templates
- Configurable mock mode
- Live LLM provider support
- Shared Agent Registry
- JSON parsing and schema validation
- Comprehensive error handling
- Unit tests for the main success and failure scenarios

---

## Project Components

### `src/agents/`

Contains the implementation of each educational agent.

| File | Description |
|------|-------------|
| `mentor_agent.py` | Generates guided educational responses, highlights key learning points, and suggests next learning steps while avoiding giving complete solutions. |
| `concept_agent.py` | Produces structured concept explanations focused on understanding rather than mentoring. |

---

### `src/prompts/`

Contains external YAML prompt templates.

| File | Description |
|------|-------------|
| `mentor.yaml` | Prompt template for the Mentor Agent including role, instructions, grounding rules, and output contract. |
| `concept.yaml` | Prompt template for the Concept Explanation Agent with a structured explanation format and difficulty-aware instructions. |

Keeping prompts outside the Python code allows prompt updates without changing the implementation.

---

### Output Schemas

Each agent validates every generated response using a dedicated Pydantic schema.

- `MentorOutput`
- `ConceptOutput`

Validation guarantees that every response matches the expected JSON structure before being returned.

---

### Agent Registry

Implemented in:

```text
src/registry.py
```

Responsibilities:

- Register available agents
- Register the corresponding output schema for each agent
- Retrieve agents by name
- Retrieve schemas by agent name
- Reject unknown agent names with descriptive errors

---

## Mock Mode

Mock Mode allows development and testing without connecting to an external LLM provider.

Enable Mock Mode:

```env
MOCK_MODE=true
```

When enabled:

- No API requests are sent.
- Responses are generated locally.
- JSON parsing and Pydantic validation are still executed.
- The same validation pipeline used in production is preserved.

This is useful during development and while an LLM provider is unavailable.

---

## Live Provider Configuration

To use a real language model:

```env
MOCK_MODE=false
```

During Sprint 1 validation, the implementation was tested using:

**Provider**

```
OpenRouter
```

**Model**

```
nvidia/nemotron-3-ultra-550b-a55b:free
```

The implementation is provider-independent and can later be switched back to LiteLLM or any OpenAI-compatible endpoint without changing the agent logic.

---

## Environment Configuration

Create a `.env` file in the project root.

Example:

```env
OPENAI_API_KEY=your_api_key
OPENAI_BASE_URL=https://openrouter.ai/api/v1
DEFAULT_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free

MOCK_MODE=false
```

For local development without an LLM provider:

```env
MOCK_MODE=true
```

Never commit your API keys or secrets.

---

## Generation Pipeline

Both agents follow the same workflow:

```text
YAML Prompt
      │
      ▼
Prompt Construction
      │
      ▼
LLM Generation
(Mock or Live Provider)
      │
      ▼
JSON Parsing
      │
      ▼
Pydantic Validation
      │
      ▼
Typed Output
```

---

## Testing

Run the available tests:

```bash
python -m tests.test_mentor_agent
python -m tests.test_concept_agent
python -m tests.test_registry
python -m tests.test_invalid_json
python -m tests.test_invalid_yaml
python -m tests.test_missing_yaml
python -m tests.test_missing_env
```

These tests verify:

- Successful Mentor Agent generation
- Successful Concept Agent generation
- Registry functionality
- Schema validation
- Invalid JSON handling
- Invalid YAML handling
- Missing YAML detection
- Missing environment configuration
- Unknown agent handling

---

## Collaboration

Mentors and interns work in this repo (or forks) in parallel. Use the task pack for acceptance criteria; use this tree only as the shared project layout.