# Agent parity matrix

Seven agents, built by three people in three lanes. Fixes landed lane by lane,
and several never crossed over — so the same bug was fixed in one place and left
live in another, sometimes for months. Nobody noticed, because nothing compares
the lanes.

This page is that comparison. **If you fix something in one lane, put it in this
table and say whether the other two need it.** The table is the point; the rest
is context.

The three lanes:

| Lane | Agents | Base class / module |
|---|---|---|
| Content — explanation | Mentor, Concept | `src/agents/explanation_agent_base.py` |
| Content — questions | Question Bank, Test Help | `src/agents/question_agent_base.py` |
| Study | Flashcards, Study Plan, Revision | `src/study/*_agent.py` |

## Where each lane stands

| Behaviour | Mentor / Concept | Question Bank / Test Help | Study three |
|---|---|---|---|
| Output persisted for review | ✅ | ✅ | ✅ |
| Failed run recorded, not lost | ✅ | ✅ | ✅ |
| Cited ids verified against retrieval | ✅ blocks | ✅ blocks | ❌ no citations at all |
| Uncited output refused | ✅ | ✅ | ❌ n/a |
| Support heuristic is advisory | ✅ | ✅ | ❌ n/a |
| Warnings reach the review record | ✅ | ✅ | ❌ n/a |
| Model cannot switch off its own review | ✅ | ✅ | ✅ |
| Review flag frozen against later callers | ✅ | ✅ | ✅ |
| Unknown fields refused | ✅ | ✅ | ✅ |
| Empty output refused | ✅ | ✅ | ✅ |
| Retry on the page path | ✅ | ✅ | ✅ |
| Retry on the orchestrator path | ✅ (orchestrator's) | ✅ (orchestrator's) | n/a — no orchestrator |
| One shared response guard | ✅ | ✅ | ✅ |
| JSON-mode fallback narrowed to 400/422 | ✅ | ✅ | ✅ |
| Output budget sized to the request | ❌ flat cap | ✅ | ✅ |
| Batch generation | ✅ `generate_batch` | ❌ | ✅ `src/study/batch.py` |
| Prompt shape (7 sections, `prompt_template`) | ✅ | ✅ | ✅ |

## The other axis: which entry path drives the agents

The table above compares three lanes. It does not compare the two ways those
agents get invoked, and that is where the same class of bug came back.

| Path | Reaches agents via | Used by |
|---|---|---|
| Orchestrator | `_call_llm` + `validator.validate`, retries itself | Streamlit pages, batch, `src/validation/automation.py` |
| HTTP services | `generate()` directly, which retries itself | `backend/` → the React UI |

| Behaviour | Orchestrator | HTTP services |
|---|---|---|
| Cited ids verified against retrieval | ✅ | ✅ *(was ❌ for question bank / test help — see below)* |
| Failed run recorded, not lost | ✅ | ✅ *(was ❌ on every service)* |
| `run_started` / `run_failed` / `run_completed` events | ✅ | ✅ |
| Warnings reach the review record | ✅ `generate_reviewable` | ✅ carried by the service |
| Output persisted for review | ✅ | ✅ |
| Retry | ✅ its own | ✅ `generate()`'s — never both |
| Schema validation | `validator.validate` | inside `generate()` |

**Two guards were missing on the HTTP path and are now closed.** The services
called `agent.generate()` with a plain string and no `context=`, which switches
`_enforce_grounding` off (`question_agent_base._generate_once`) — so question
bank and test help accepted invented `segment_id`s that Streamlit refused. And
every service saved its `AgentRun` only after a success, so a failed generation
left no trace. `backend/runs.py:recorded_run` now mirrors the orchestrator's
sequence, and `generate_or_422` is shared by both service modules.

**The HTTP path does not use `validator.validate`, and should not.** The
orchestrator needs it because it calls `_call_llm` and gets raw text back. The
services call `generate()`, which already parses, schema-validates, enforces the
request and enforces grounding. Running the validator over an
already-validated model would duplicate the schema check, not add a guarantee.
What the validator *also* did — putting warnings in the review record — the
services now do directly.

**Neither path may fabricate a citation.** A citation chip states the model
cited that passage. The services used to attach the whole retrieved context to
an output that cited nothing, and to match a flashcard's `source_topic` against
chunk text by substring. Both are gone: the exact/fuzzy split in "Two rules
worth keeping" applies to what gets *displayed*, not only to what blocks.

## The gaps that remain, and why

**The study lane has no citation verification.** Its three schemas carry no
`references` field, so there is nothing to verify — the agents are grounded by a
topic allow-list instead, which is a real constraint but a weaker one. Recorded
in [study-lane-sprint3.md](study-lane-sprint3.md); closing it is a schema change
plus a prompt change, not a parity fix.

**Chapter-shaped questions cannot be answered** - chunks carry no chapter or
section metadata, so retrieval cannot serve them and the agents correctly refuse.
Recorded in [retrieval-lane.md](retrieval-lane.md).

**The explanation agents use a flat output cap** where the other two lanes size
it to the request. One explanation is one explanation, so a flat cap is
defensible — unlike a request for 20 flashcards, which is what `output_budget`
exists for.

**The question agents have no batch mode.** Nothing needs one yet. Do not build
a third batch mechanism to fill in a tick.

## Two rules worth keeping

**Retry belongs to whoever owns the path, and to only one of them.** The
orchestrator retries and reaches agents through `_call_llm`; the pages call
`generate()` and the orchestrator never touches them. Retrying in both places
turned `max_retries=2` into six calls against a provider that had just said it
was saturated. So `chat_json` defaults to one attempt and `generate()` opts in.

**Exact checks block; fuzzy ones inform.** `verify_references` is set membership
over chunk ids — zero false positives across 20 live generations, so it raises.
`validate_support` is a 0.6 token-overlap heuristic that rejected 5 of those
same 20 correct generations, so it warns and the warning goes to the reviewer.
Raising on a fuzzy signal withholds one correct answer in four, which is what
got grounding switched off wholesale the first time.

## How the divergences were found

Reading the code found most of them. Two were found only by **running the app
against a live gateway** — the Revision page failed outright while the other
four worked, and the failure had nothing to do with what was being changed at
the time. A green test suite proves the doubles still agree with the code; it
does not prove the agents work.
