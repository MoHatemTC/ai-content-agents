# Sprint 2 – Question Bank & Test Help Agents Foundation

This sprint extends the educational AI agent framework by introducing two structured generation agents:
* **Question Bank Agent**
* **Test Help Agent**

The purpose of this sprint is to create reliable educational assessment agents capable of generating structured questions from provided educational content while ensuring grounded responses, strict output formatting, and high reliability.

---

## Key Guarantees
* **Content Grounding:** Responses are strictly based on provided material.
* **Strict Formatting:** Schema validation enforced via **Pydantic**.
* **Flexible LLM Backend:** Configurable LLM providers alongside a development-friendly **Mock Mode**.
* **Test Coverage:** Full automated test suite for error handling, schemas, and integration.

---

## Generation Pipeline

```text
  [ Educational Content ]
             │
             ▼
[ Agent Prompt Template (YAML) ]
             │
             ▼
    [ Prompt Construction ]
             │
             ▼
     [ LLM Provider ]  ───► (Mock Mode / Live API)
             │
             ▼
    [ Raw Model Response ]
             │
             ▼
      [ JSON Parsing ]
             │
             ▼
   [ Pydantic Validation ]
             │
             ▼
  [ Validated Output Object ]
```

---

## Sprint Objectives

### 1. Implement Question Bank Agent
Generates structured educational questions directly from provided learning material.
* Supports multiple-choice question (MCQ) generation.
* Controls difficulty levels and question counts.
* Embeds rationale explanations and source content references.
* Performs end-to-end schema validation.

### 2. Implement Test Help Agent
Provides targeted support by generating practice and assessment questions to assist learner preparation.
* Generates tailored assessment practice items.
* Supplies clear answer explanations while maintaining strict content grounding.
* Outputs guaranteed structured data.

### 3. Create Typed Output Schemas
All LLM output passes through validated Pydantic models:
* `QuestionBankOutput`
* `TestHelpOutput`

> **Benefits:** Guarantees required fields, prevents malformed API responses, ensures consistent output structures, and makes models safe for downstream UI/API consumption.

---

## Project Structure

```ascii
ai-content-agents/
│
│
├── docs/
│   └── question-bank-test-help-lane.md
├── src/
│   ├── agents/
│   │   ├── question_bank_agent.py
│   │   └── test_help_agent.py
│   ├── prompts/
│   │   ├── question_bank.yaml
│   │   └── test_help.yaml
│   ├── validation/
│   │   └── schemas.py
│   ├── services/
│   │   └── formatters.py
│   └── registry.py
│
├── frontend/
│   └── qbank_ui.py
│
├── tests/
│   ├── test_question_bank.py
│   ├── test_test_help.py
│   ├── test_agents_integration.py
│   ├── test_schema_validation.py
│   ├── test_prompt_loading.py
│   └── test_formatters.py
│

```

---

## Agent Implementation & Workflows

### `src/agents/question_bank_agent.py`
1. Loads instructions from `src/prompts/question_bank.yaml`.
2. Constructs the prompt and queries the configured provider.
3. Parses raw JSON output into the `QuestionBankOutput` model.

```text
[ Input Content ] ──► [ question_bank.yaml ] ──► [ Generated Prompt ]
                                                        │
[ QuestionBankOutput ] ◄── [ JSON Parsing ] ◄── [ LLM Response ]
```

### `src/agents/test_help_agent.py`
1. Loads test preparation instructions from `src/prompts/test_help.yaml`.
2. Generates educational support items and explanations.
3. Validates output against the `TestHelpOutput` model.

```text
[ Input Content ] ──► [ test_help.yaml ] ──► [ Generated Prompt ]
                                                    │
  [ TestHelpOutput ] ◄── [ JSON Parsing ] ◄── [ LLM Response ]
```

---

## Prompt System & Validation

Prompts are stored inside `src/prompts/` as YAML files to decouple prompt engineering from core application logic.

* **`question_bank.yaml`:** Role definitions, MCQ rules, difficulty tags, source grounding rules, and JSON schema targets.
* **`test_help.yaml`:** Educational assistant parameters, explanation depth constraints, and test preparation formats.

### Validation Pipeline (`src/validation/schemas.py`)

```text
[ LLM JSON Response ] ──► json.loads() ──► Pydantic model_validate() ──► [ Validated Python Object ]
```

The Pydantic models verify that:
* Questions, options, and correct answers are non-empty.
* Explanations and references are appropriately mapped.
* Formatting constraints are satisfied prior to returning data.

---

## Configuration & Execution Modes

### Live LLM Provider Mode
Set `MOCK_MODE=false` in `.env` to connect to an OpenAI-compatible API backend (via LiteLLM).
```env
MOCK_MODE=false
LITELLM_API_KEY=your_api_key
LITELLM_BASE_URL=provider_url
DEFAULT_MODEL=model_name
```

---

## Formatting Services & UI Layer

### Formatting Utilities (`src/services/formatters.py`)
Prepares Pydantic outputs into dictionary payloads for downstream consumption:
* `format_question_bank()`
* `format_test_help()`

**Example Transformation:**
```json
// Formatted dictionary output sample
{
  "questions": [ ... ],
  "requires_human_review": true
}
```

### UI Layer (`frontend/qbank_ui.py`)
Currently serves as an architecture placeholder (`render() -> None`) reserved for upcoming Streamlit interface integrations.

---

## Testing Strategy

Run the full suite using `pytest`:

```bash
# Run individual agent tests with stdout enabled
python -m pytest tests/test_question_bank.py -s -v
python -m pytest tests/test_test_help.py -s -v
```

### Coverage Overview
* **Agent Generation:** Verifies structural completeness, field validity, and grounding.
* **Integration Tests:** Asserts multi-agent interactions and import health.
* **Schema Tests:** Validates rejection of bad schemas and acceptance of good ones.
* **Prompt Tests:** Confirms YAML parsing, key existence, and fallback behavior.
* **Error Tests:** Tests empty responses, malformed JSON, and missing variables.

---

## Sprint Summary

### Completed Objectives
- Question Bank Agent implementation
- Test Help Agent implementation
- Externalized YAML prompt templates
- Pydantic validation layer
- Error handling & formatting utility pipeline
- UI placeholder setup
- Full automated test suite
