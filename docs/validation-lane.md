# Review, Validation, Orchestration & Export Lane

The quality-and-trust layer of Content Agents, and the layer that connects the
other four. It owns everything between *an agent produced something* and *a human
released it*: running the agents, judging what they return, storing it, showing it
to a reviewer, and letting approved content out — in that order, with no shortcuts.

One rule is load-bearing:

> Nothing an agent generates reaches a user until a person has explicitly approved
> it. `assert_exportable()` is the only thing that decides, and every export path
> calls it.

Code lives in `src/validation/` (plus `src/exports/` for the exporters). Tests are
`tests/features/test_platform_core.py`, `tests/features/test_review.py`,
`tests/features/test_platform_integration.py`, and the original
`tests/test_validation.py`.

---

## 1. Data flow

```
Uploaded material
   │  ContentLoader.load_text/load_file          (ingestion lane)
   ▼
Document + Chunks in SQLite
   │  to_retrieval_chunks() → ChunkIndex.add_document()   ← integration.py
   ▼
Chroma index
   │  build_grounded_context(query, scope)       (retrieval lane)
   ▼
GroundedContext ──────────────────────────────┐
   │  as_prompt_content() → the agent prompt   │ chunk_ids
   ▼                                           │
Agent (mentor / concept / question_bank / test_help)
   │  raw response text                        │
   ▼                                           │
ValidatorBase.validate() ←─────────────────────┘
   │   schema check, then guardrails (incl. the citation check)
   ▼
AgentRun + GeneratedOutput  (status: pending)   ← store.py
   │  ReviewService.approve / edit / reject / comment
   ▼
Review records (append-only)  +  status transition
   │  assert_exportable()   ← the gate
   ▼
JSON / CSV / Markdown / PDF                     ← src/exports/
```

`orchestrator.py` drives the middle of that diagram; `integration.py` drives the
whole of it; `automation.py` runs it in bulk; `evaluation.py` scores the result;
`ui.py` is where a human stands.

---

## 2. Modules

### `review_schema.py` — the contract

The lifecycle is `pending → edited → approved | rejected`, with `pending →
approved` and `pending → rejected` allowed directly.

- **`OutputStatus`** — both `approved` and `rejected` are **terminal for status
  changes**. There is no re-open path, so a rejected output can never become
  approved and therefore can never become exportable. Status-neutral `COMMENT`
  actions stay legal from either terminal state, so the audit trail never closes.
- **Models** — `AgentRun` (one per invocation, carrying `source_chunk_ids`
  provenance), `GeneratedOutput` (one per artifact, carrying `payload`, the
  `validation_report` and the current `status`, defaulting to `pending`),
  `Review` (**immutable**, `frozen`, one per human action) and `SystemEvent`
  (the operational log).
- **`apply_review(...)`** — pure logic, no storage. Validates the transition,
  advances the output, returns the `Review` to persist. It raises *before*
  mutating anything, so a refused action leaves no trace.
- **`assert_exportable(output)`** — the gate. Raises `ExportBlockedError` unless
  the output is `approved`.

### `validator_base.py` + `guardrails.py` — the judgement

`ValidatorBase.validate(raw_output, schema, rules=None, context=None)` runs a
schema check and then the guardrails, and **never raises** — a bad output becomes
a structured verdict, not an exception.

Three rules ship by default:

| Rule | Question it answers |
|---|---|
| `non_empty_text` | Did the agent actually say anything? |
| `references_present` | Did it cite its sources at all? |
| `grounded_references` | **Are those citations real?** |

`grounded_references` is the hallucination check. It compares every cited
`segment_id` against the chunk ids the agent was genuinely given, so a model
inventing a plausible-looking id is caught before a reviewer ever sees it. It
accepts its evidence either as a full `GroundedContext` (at generation time) or as
a list of chunk ids (when re-validating an edit later, by which point only
`AgentRun.source_chunk_ids` survives), and is a no-op when neither is available —
so ungrounded callers are not penalised for a comparison that cannot be made.

Citation walking reaches **nested** references: `QuestionBankOutput` and
`TestHelpOutput` cite per question rather than at the top level, and would
otherwise be silently exempt from both citation rules.

### `store.py` — persistence

`PlatformStore` owns four tables — `agent_runs`, `generated_outputs`, `reviews`,
`system_events` — and shares its SQLite file with the ingestion lane by default, so
documents, chunks, runs, outputs and reviews all sit together and provenance can be
followed end to end.

`reviews` is **insert-only**: the store deliberately exposes no update or delete
for it, which makes the audit trail append-only at the API rather than by
convention. Runs and outputs use `INSERT OR REPLACE` because both legitimately
change — a run gains its outcome, an output's status advances.

### `orchestrator.py` — running agents

`Orchestrator.run_agent()` builds the prompt content from a `GroundedContext`,
calls the agent, validates the response, and persists a run plus an output.

Two behaviours matter more than the rest:

- **Malformed output is flagged, not lost.** The agents' own `generate()` raises
  on invalid JSON and discards the model's text, which would make a bad response
  impossible to review — it would simply vanish. Adapters capture the **raw
  string** instead and hand it to the validator, which never raises. Unparseable
  text is stored under `payload["raw_output"]` so a reviewer sees exactly what the
  model said. This reaches into `_build_prompt` / `_call_llm`, a deliberate seam
  pending a public `generate_raw()` from the agents lane.
- **Failures are recorded, never raised.** A dead upstream, a timeout, or missing
  grounding produces an `AgentRun(status=failure)` with the error text, visible in
  History rather than aborting a batch. Transient errors (connection, timeout,
  rate limit, 5xx) are retried with exponential backoff first; deterministic ones
  are not retried.

New agents plug in by implementing `AgentSpec` (`name`, `schema`,
`run_raw(content, **params)`); the orchestrator knows about no specific agent.

### `review_service.py` — the human decisions

`list_pending`, `get`, `approve`, `edit`, `reject`, `comment`, `history`.

**Editing re-validates.** A reviewer rewriting a payload could otherwise leave a
stale "passed" verdict on content that no longer satisfies its schema, or quietly
introduce a citation that was never retrieved. The verdict is recomputed either
way — an edit can repair a failing output or break a passing one, and the record
must say which. When the schema cannot be resolved the old verdict is kept but
marked `revalidated: false`, rather than being passed off as fresh.

### `src/exports/` — getting content out

`export_outputs`, `export_output`, `export_approved_run` in JSON, CSV, Markdown and
PDF. The gate runs over **every** output before a single byte is rendered: a file
containing some approved content and then an error is worse than no file.
`export_approved_run` also filters by status when reading, but the gate still runs
afterwards — the query is convenience, the gate is the invariant.

CSV keeps the payload as one JSON column, because agent payloads are nested and
differently shaped per agent; flattening would give every export a different
header. PDF uses `fpdf2`, whose core fonts are latin-1, so typographic characters
are mapped to ASCII and anything still unrepresentable degrades to `?` rather than
failing the export.

### `history.py` — what happened

The event vocabulary (`run_started`, `validation_failed`, `export_blocked`, …) plus
`HistoryService`: `list_runs`, `run_detail`, and `output_timeline`, which merges the
generating run, every human review and every system event into one chronological
answer to "why is this output in the state it is in?".

### `integration.py` — the pipeline

`Pipeline.build()` assembles ingestion, indexing, retrieval, orchestration and
persistence; `run()` and `ingest_and_run()` drive them. Retrieval that finds
nothing in scope **stops the pipeline before any agent runs** — answering without
grounding is the thing this platform exists to prevent — and returns the reason
rather than raising.

It also carries the ingestion→retrieval bridge (`to_retrieval_chunks`), which is a
rename of `id` → `chunk_id` plus dropping the character offsets retrieval does not
use. This is the ingestion/retrieval join the retrieval lane had left open.

### `automation.py` — the batch

`run_batch()` plus a CLI. Runs the pipeline over a demo dataset, survives
individual failures, and scores the result. **Nothing is exported and nothing is
approved** — a batch that approved its own work would defeat the gate.

### `evaluation.py` — the measurement

Reads only the persisted record — no model calls, so numbers are reproducible.
Reports per agent and overall:

| Metric | Definition |
|---|---|
| schema pass rate | outputs passing schema **and** guardrails / all outputs |
| groundedness rate | outputs with no fabricated citation / outputs whose citations *could* be checked |
| review edit rate | outputs a human changed / outputs a human decided on |
| approval, rejection rate | approved or rejected / outputs a human decided on |

Two denominators are deliberately narrow. Groundedness counts only *checkable*
outputs: a run with no retrieval had nothing to check, and a schema failure means
the guardrails never ran. Review edit rate counts only outputs a human actually
decided on — a comment is not a decision. Undefined rates render as `n/a`, never
`0.0`: "nothing was ever grounded" and "nothing was ever checked" are different
facts.

### `ui.py` — the human surface

Four Streamlit pages: **Review** (the queue and the four actions), **History**
(runs, events, timelines), **Export** (download approved outputs), **Metrics** (the
evaluation report). The page holds no logic of its own.

Review actions stay disabled until a reviewer names themselves, because every
review record is attributed. The export gate's refusal is shown rather than hidden
— seeing it work is the point of having it.

---

## 3. Running it

```bash
pip install -r requirements.txt

# the whole suite (live integration tests skip without a key)
python -m pytest tests/ -q

# this lane
python -m pytest tests/features/test_platform_core.py \
                tests/features/test_review.py \
                tests/features/test_platform_integration.py -v

python -m ruff check src/validation src/exports tests/features
python -m mypy src/validation src/exports --ignore-missing-imports

# batch demo, then the review surface
python -m src.validation.automation --offline    # no API calls
python -m src.validation.automation              # live
streamlit run src/validation/ui.py
```

See [deployment.md](deployment.md) for configuration and running it for real.

---

## 4. Decisions that are load-bearing — don't "fix" these by accident

| Decision | Why it exists |
|---|---|
| `approved` **and** `rejected` are terminal | A rejected output that could be re-approved is not a rejection. Terminal states are what make the gate meaningful. |
| Validation failure does **not** block review | Failed outputs still persist as `pending` so a human can see what the agent produced. Only *export* is gated, and only on human approval. |
| The gate runs before any rendering | A partial export containing approved content plus an error is worse than no export. |
| The store has no `update_review` / `delete_review` | Append-only enforced by the API, not by discipline. |
| Orchestrator captures raw text, not `generate()`'s parsed result | `generate()` raises on malformed JSON and throws the text away; you cannot flag what you did not keep. |
| Agent failures become failed runs, not exceptions | A batch must survive a dead upstream, and the failure is itself information worth showing. |
| Undefined metrics are `None`/`n/a`, never `0.0` | Never measured ≠ measured and scored zero. |
| Every test index uses a unique Chroma collection name | Chroma's `EphemeralClient` is shared per process, so two same-named indexes see each other's chunks. |

---

## 5. What is deliberately NOT built

- **No semantic entailment checking.** `grounded_references` verifies that a
  citation points at a chunk that was really retrieved. It does *not* check that
  the chunk actually supports the claim. That is the honest limit of this lane's
  hallucination detection.
- **No re-open path.** Approved and rejected are final by design. If a sprint
  needs supersede-with-a-new-version, that is a new record, not a mutated one.
- **No authentication.** The reviewer is a name typed into a box. Real identity
  belongs to whatever auth the deployment adds.
- **No retrieval-quality measurement.** This lane measures whether citations are
  *real*, not whether retrieval found the *best* chunks. Recall and ranking
  quality remain unmeasured, and are the retrieval lane's open work.
- **No consolidation of the duplicate evaluation/batch modules** that other lanes
  ship (`src/evaluation/`, `src/study/`). Flagged for next sprint, not silently
  duplicated away.

---

## 6. Who to ask about what

- **Ingestion / chunk production** → Ahmed (`src/ingestion/`)
- **Agents & prompts** → Youssef (`src/agents/`, `src/prompts/`)
- **Retrieval & grounding** → [retrieval-lane.md](retrieval-lane.md), then Nour
- **This lane** → Nour
