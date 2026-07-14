# Validation & Review Lane (QA Foundation)

The quality & trust layer of Content Agents. Every AI agent output must pass
structural validation and content guardrails, then a human-review gate, before it
can be exported. Nothing an agent generates reaches a user without being explicitly
marked `approved` by a human.

Code lives under `src/validation/`; tests under `tests/test_validation.py`.

## review_schema

`src/validation/review_schema.py` — the shared review contract.

- **`OutputStatus`** — output lifecycle: `pending → edited → approved` (and
  `pending → approved` directly). `approved` is **terminal** in Sprint 1: there is
  no re-open path. `is_legal_transition(old, new)` encodes the legal moves.
- **Models** — `AgentRun` (one per agent invocation; carries provenance via
  `source_chunk_ids`), `GeneratedOutput` (one per artifact; carries `payload`, the
  `validation_report`, and the current `status`, defaulting to `pending`), and
  `Review` (an **immutable, append-only** record of one human action — it is
  `frozen`, never mutated or deleted).
- **`apply_review(output, reviewer, action, *, edited_payload=None, notes=None)`** —
  pure logic (no storage): validates the transition, advances `output.status`
  (and `output.payload` on an edit), and returns the `Review` record. Illegal
  transitions raise `IllegalTransitionError`.
- **Export gate** — `assert_exportable(output)` raises `ExportBlockedError` unless
  the output is `approved`. Every export path must call it; there is no bypass.
- **Logging** — status transitions and blocked-export attempts are logged via the
  module logger; the append-only `Review` records are the durable audit trail.

## validation_base

`src/validation/validator_base.py` — the reusable, agent-agnostic validator every
output runs through. `ValidatorBase.validate(raw_output, output_schema, rules=None,
context=None)` runs two steps and **never raises**:

1. **Schema check** — parse `raw_output` (JSON string or mapping) and validate it
   against the declared Pydantic schema; Pydantic errors are collected into
   `ValidationResult.schema_errors`.
2. **Guardrails** — only if the schema check passed, run each rule and collect
   `guardrail_violations`.

It returns `(ValidationResult, model | None)`: the parsed instance when the schema
check passes, else `None`. The validator has no knowledge of any specific agent —
the caller supplies the schema type — so the same base validates any agent output.

## guardrails_foundation

`src/validation/guardrails.py` — the rule mechanism plus the Sprint 1 rules.

- **`GuardrailRule`** (ABC) — each rule has a unique `name` and a
  `check(output, context) -> GuardrailViolation | None` method.
- **`ReferencesPresentRule`** (`references_present`) — grounding/provenance: an
  output that declares a `references` field must carry a non-empty one. Schemas
  without `references` are not subject to the rule. Deep semantic hallucination
  checking against source content is a later-sprint concern; this rule only
  verifies provenance is present.
- **`NonEmptyTextRule`** (`non_empty_text`) — required text fields must not be
  blank or shorter than `context.min_text_length`.
- **`DEFAULT_RULES`** — the default set (`[ReferencesPresentRule, NonEmptyTextRule]`).
  New rules can be added without touching the validator base.

## tests

`tests/test_validation.py` — module-level suite (pure in-memory model instances).
Covers:

- status lifecycle: default `pending`; legal transitions succeed; illegal ones and
  any action on an `approved` output are rejected;
- validator: valid payload passes; schema-invalid payload and invalid JSON report
  errors without raising; guardrail violation is reported, not raised;
- guardrails: each shipped rule has a pass and a fail case;
- **export gate: `pending` and `edited` are blocked; `approved` passes** (the
  single most important behaviour);
- audit: review actions produce immutable records and a reconstructable history.

Run from the repo root:

```bash
pip install pydantic pytest
python -m pytest tests/test_validation.py -v
```
