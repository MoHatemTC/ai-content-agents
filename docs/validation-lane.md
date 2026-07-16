# Validation & Review Lane (QA Foundation)

The quality & trust layer of Content Agents. Every AI agent output must pass
structural validation and content guardrails, then a human-review gate, before it
can be exported. Nothing an agent generates reaches a user without being explicitly
marked `approved` by a human.

Code lives under `src/validation/`; tests under `tests/test_validation.py`.

## review_schema

`src/validation/review_schema.py` — the shared review contract.

- **`OutputStatus`** — output lifecycle: `pending → edited → approved` (and
  `pending → approved` directly). `approved` is **terminal for status changes** in
  Sprint 1: there is no re-open path and no further approve/edit action.
  Status-neutral audit **comments remain allowed** on approved outputs so the
  review history can keep recording observations. `is_legal_transition(old, new)`
  encodes the legal moves.
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

**`build_generated_output(...)`** bridges validation and persistence: it builds the
`GeneratedOutput` record from a `ValidationResult`, copying the verdict onto the
record (`validation_passed` / `validation_report`) so the two can never drift.
Failed outputs are still recorded (as `pending`, like everything else) so reviewers
can see what an agent produced.

## guardrails_foundation

`src/validation/guardrails.py` — the rule mechanism plus the Sprint 1 rules.

- **`GuardrailRule`** (ABC) — each rule has a unique `name` and a
  `check(output, context) -> GuardrailViolation | None` method.
- **`Severity`** — violations carry a severity: `error` (default) fails
  validation; `warning` is surfaced in the result for the reviewer but does not
  fail it.
- **`ReferencesPresentRule`** (`references_present`) — grounding/provenance: an
  output that declares a `references` field must carry a non-empty one. Schemas
  without `references` are not subject to the rule. Deep semantic hallucination
  checking against source content is a later-sprint concern; this rule only
  verifies provenance is present.
- **`NonEmptyTextRule`** (`non_empty_text`) — required text fields must not be
  blank or shorter than `context.min_text_length`. **By default every string field
  on the output is checked** — agents whose schemas include optional/legitimately
  blank text fields should pass `context.required_text_fields` to restrict the
  check.
- **`DEFAULT_RULES`** — the default set (`[ReferencesPresentRule, NonEmptyTextRule]`).
  New rules can be added without touching the validator base.

## tests

`tests/test_validation.py` — module-level suite (pure in-memory model instances).
Covers:

- status lifecycle: default `pending`; legal transitions succeed; illegal ones and
  approve/edit actions on an `approved` output are rejected, while audit comments
  on approved outputs are allowed;
- validator: valid payload passes; schema-invalid payload and invalid JSON report
  errors without raising; guardrail violation is reported, not raised;
- guardrails: each shipped rule has a pass and a fail case; severity defaults to
  `error`; a `warning`-severity violation is reported without failing validation;
- factory: `build_generated_output` copies passing and failing verdicts onto the
  record exactly;
- **export gate: `pending` and `edited` are blocked; `approved` passes** (the
  single most important behaviour);
- audit: review actions produce immutable records and a reconstructable history.

Run from the repo root:

```bash
pip install pydantic pytest
python -m pytest tests/test_validation.py -v
```
