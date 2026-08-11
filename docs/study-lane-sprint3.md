# Sprint 3 — Flashcards, Study Plan & Revision Assistant Lane

**Owner:** Study Agents lane (end-to-end)
**Module path:** `src/study/` (flat lane layout, matches `src/ingestion/` and `src/retrieval/`)
**Merges via:** shared contracts only — no modifications to Sprint 1 schemas or other engineers' lanes.

This vertical slice owns three grounded, schema-validated, human-review-gated
learner-facing agents:

1. **Flashcard agent** (`flashcard_agent.py`) — term-definition / Q-A cards
   from selected content, with format + count controls, every card's
   `source_topic` constrained to a deterministic extraction allow-list.
2. **Study Plan agent** (`study_plan_agent.py`) — plan from real content
   topics + learner goals (difficulty / time budget), scheduled topics are
   validated against the same extraction allow-list (never fabricated).
3. **Revision Assistant** (`revision_agent.py`) — targeted revision items
   from weak/selected topics, using spaced-repetition heuristic
   (easy=+7d, medium=+3d, hard=+1d), validating selected topics against
   the allow-list.

Supporting pieces:

- **`formatters.py`** — JSON-safe dict renderers for UI / export.
- **`prompts/*.yaml`** — explicit YAML prompt templates per agent.
- **`batch.py`** — batched generation across a 3-item demo dataset.
- **`evaluation.py`** — deterministic groundedness + quality benchmark for
  the AI evaluation workstream (no network, no LLM trust).
- **`ui.py`** — polished Streamlit pages (Flashcards / Plan / Revision /
  Batch & Benchmark) that wire every output through the human-review gate.
- **Tests** — `tests/features/test_flashcards.py`,
  `tests/features/test_study_plan.py`,
  `tests/features/test_study_eval.py`.

---

## Sections

### 1. `flashcard_generation`

The flashcard agent in [flashcard_agent.py](file:///D:/Sprint/Sprint_Task1/ai-content-agents/src/study/flashcard_agent.py) follows the four-step
repo-wide pattern:

1. `extract_topics(content)` produces a **deterministic** allow-list from
   content (capitalised n-grams, stopwords dropped, frequency-ranked).
   This step never invokes an LLM.
2. `_build_prompt` injects that allow-list into the YAML prompt template
   that *commands* the LLM to only pick from the list.
3. `generate(...)` calls LiteLLM in live mode and returns a mock in
   `MOCK_MODE`.
4. `_validate_grounding` and `_wrap_for_review_gate` enforce the
   contracts:
   - every card's `source_topic` is in the allow-list, otherwise
     `GroundingError`;
   - the returned `FlashcardSet` is always `needs_human_review=True`.

### 2. `grounding`

Grounding is implemented at two levels:

- **Content-in → allow-list:** a pure, deterministic substring extraction
  (see `FlashcardAgent.extract_topics`). No LLM trust, no hallucinations
  possible at this step.
- **Allow-list → output:** each agent runs a post-LLM validator that
  *rejects* any output referencing topics outside the allow-list:
  - `FlashcardAgent._validate_grounding`
  - `StudyPlanAgent._validate_plan` (topic membership + dates + difficulty)
  - `RevisionAgent._validate_revision` (allow-list ∩ selected-topics
    intersection + difficulty values + date ordering)
- **Benchmark-side audit:** `evaluation.py` re-runs the full grounding
  check on every batch row and reports a `grounded_rate` per agent.

### 3. `format_count_controls`

`FlashcardAgent.generate(content, card_format, card_count, ...)` exposes:

- `card_format` ∈ `{"term-definition", "qa"}` with enum validation.
- `card_count` ∈ `[1, 25]` (UI slider). Mock and LLM prompt both respect
  the count exactly when the content has enough material; otherwise they
  return the maximum grounded cards available (never silence an error).

The UI in [ui.py](file:///D:/Sprint/Sprint_Task1/ai-content-agents/src/study/ui.py) additionally surfaces a
multi-select for the *extracted topic allow-list* so the user can see the
precise set of topics the agent is permitted to build cards on.

### 4. `tests`

Three feature-test files cover unit + integration paths:

| Test file | Coverage |
|---|---|
| `tests/features/test_flashcards.py` | Topic extraction determinism, format/count validation, grounding-rejection, JSON-safe formatters, flashcard batch. |
| `tests/features/test_study_plan.py` | Plan date/difficulty rules, plan grounding-rejection on fabricated topics, revision-topic-not-in-content rejection, both formatters, both batches. |
| `tests/features/test_study_eval.py` | Full 3-item default batch end-to-end, benchmark `grounded_rate` = 1.0, benchmark JSON serialisability, "every output is `needs_human_review=True`" invariant. |

### 5. `study_plan_build`

The planner in [study_plan_agent.py](file:///D:/Sprint/Sprint_Task1/ai-content-agents/src/study/study_plan_agent.py) takes
`learner_goal, difficulty ∈ {easy, medium, hard}, start_date, end_date,
hours_per_week?` and schedules only allow-list topics.

Design rules:

- Topic extraction reuses the flashcard agent's heuristic so the allow-list
  is consistent across agents.
- Dates enforce per-topic windows stay within the overall window.
- Difficulty and `hours_per_week` drive proportional duration allocation
  in the mock; the LLM prompt encodes the same rules.
- Returned `StudyPlan.source_topics` is the *sorted intersection* of
  scheduled topics and the allow-list — reviewers see exactly what the
  planner used.

### 6. `revision_build`

The revision assistant in [revision_agent.py](file:///D:/Sprint/Sprint_Task1/ai-content-agents/src/study/revision_agent.py) takes
`selected_topics: list[str]` + `session_date` and returns one
`RevisionItem` per selected topic.

- **Precondition:** every `selected_topic` must be in the extraction
  allow-list; otherwise `RevisionGroundingError` is raised *before* the
  LLM is even consulted. This enforces "don't ask the LLM about topics
  you cannot prove are in the content".
- **Spaced-repetition heuristic:** easy → +7d, medium → +3d, hard → +1d.
- **Confidence prompt** per item to drive active-recall self-checks in
  review sessions.

### 7. `plan_validation`

Two layers:

1. **Pydantic structural validation** — date types, numeric bounds, enum
   difficulty (`easy/medium/hard`).
2. **Semantic / grounding validation** —
   `StudyPlanAgent._validate_plan` and `RevisionAgent._validate_revision`
   reject plans / sessions that cite topics outside the content-derived
   allow-list, plus structural invariants (dates in window, ordered
   dates, strictly-positive durations). When injected with a fabricated
   topic (see tests), both agents raise *grounding* errors rather than
   returning a hallucinated output.

### 8. `batch_generation`

`src/study/batch.py` exposes:

- `default_demo_dataset()` — 3 self-contained items: *Python Programming
  Basics*, *Intro to Machine Learning*, *Cell Biology*, each with a
  `learner_goal`, difficulty, weekly budget, and 2 hand-picked weak
  topics.
- `run_flashcard_batch`, `run_study_plan_batch`, `run_revision_batch` —
  per-agent parallelisable (currently serial) runners that never let a
  single row's exception poison the whole batch.
- `run_full_batch(...)` — composes the three into a single `BatchReport`.

### 9. `quality_benchmark`

`src/study/evaluation.py` runs five checks per agent against the batch
report and the original dataset:

| Flashcards | Plans | Revisions |
|---|---|---|
| Schema valid | Schema valid | Schema valid |
| Gate flag set (`needs_human_review=True`) | Gate flag set | Gate flag set |
| Grounded (card.source_topic ⊆ extracted) | Grounded (schedule.topic ⊆ extracted) | Grounded (item.topic ⊆ extracted∩selected) |
| Matches requested count | All extracted topics scheduled, dates in window | Covers all selected topics |
| Matches requested format | — | Spaced-repetition offsets ∈ {1, 3, 7} |

It reports per-agent `grounded_rate` + `overall_quality` plus a summary
`overall` score (mean of the three per-agent qualities). On the default
mock dataset the score is deterministically ≈ 1.0.

### 10. `demo_polish`

[src/study/ui.py](file:///D:/Sprint/Sprint_Task1/ai-content-agents/src/study/ui.py) provides four sidebar views:

1. **🃏 Flashcards:** format radio, count slider, extracted-topics preview
   sidebar, pending-review badge on every generated set, card expanders,
   JSON payload view.
2. **📅 Study Plan:** goal input, difficulty radio, hours-per-week slider,
   date range, extracted-topic allow-list preview, per-topic expanders.
3. **🔄 Revision Assistant:** weak-topics multi-select *from* the
   allow-list, session date, per-item expanders with confidence prompts.
4. **📦 Batch & Benchmark:** one-click full batch + benchmark score card,
   sample flashcard set preview.

The main unified `src/app.py` integrates these pages via the sidebar
radio pattern and reuses the existing ingestion `current_doc` state.

---

## Deliverable files (this slice)

```
src/study/
├── __init__.py
├── README.md
├── flashcard_agent.py
├── study_plan_agent.py
├── revision_agent.py
├── formatters.py
├── schemas.py
├── batch.py
├── evaluation.py
├── ui.py
└── prompts/
    ├── flashcards.yaml
    ├── study_plan.yaml
    └── revision.yaml

tests/features/
├── test_flashcards.py
├── test_study_plan.py
└── test_study_eval.py
```

## Quick start

```powershell
# Run full lane tests
python -m pytest tests/features/test_flashcards.py tests/features/test_study_plan.py tests/features/test_study_eval.py -v

# Run the standalone study-lane UI
streamlit run src/study/ui.py

# Run the unified app (Home + Upload + Study agents)
streamlit run src/app.py
```

## Known gap: the planner and the reviser never see the passages

`src/app.py` and `src/study/ui.py` both retrieve before generating, and both
pass the retrieved text in as `content`. The flashcard agent puts it in the
prompt. **The study-plan and revision agents do not**: they use `content` only
to derive the topic allow-list via `FlashcardAgent.extract_topics()`, and the
prompt they send carries topic *names*, dates and the learner's goal - no
passage text at all.

So "grounded study plan" currently means grounded in a word-frequency allow-list
extracted from the document, not in retrieved content. That is a real and
useful constraint - the planner provably cannot invent a topic, and
`_validate_plan` enforces it - but it is weaker than what the flashcard, mentor,
concept, question-bank and test-help agents do, and weaker than the phrase
suggests.

Consequences worth knowing before relying on it:

* Topic *ordering and duration* are guesses. The model is choosing how long
  "Kinetic Energy" needs without having read what the document says about it.
* `source_chunk_ids` recorded on the review record describe what was retrieved
  for the query, not what the plan was built from.

Closing it means adding `{content}` to `study_plan.yaml` and `revision.yaml`
and passing the passages through `_build_prompt` - a behaviour change with a
real token-budget cost on long documents, which is why it was recorded here
rather than folded into the prompt-restructuring pass that found it. The prompt
`notes:` in both YAML files point back at this section.
