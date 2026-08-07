# Test Report — Question Bank & Test Help agents

**Sprint:** 4 · **Owner:** Nour Atef · **Date:** 2026-08-06
**Commit under test:** `8c601b7` on `qa/question-agents-sprint4`, branched from `main` `6a60568`
**Bug list:** [`docs/test_reports/qbank_testhelp_bugs_2026-08-06.md`](test_reports/qbank_testhelp_bugs_2026-08-06.md)

---

---

> ## Update, 2026-08-07: all 13 bugs fixed
>
> On branch `fix/question-agents-contract`, stacked on the QA branch. The
> results below are the **pre-fix** findings and are kept as the record; the
> table that said 9 of 32 checks passed now reads **32 of 32**, plus 22 new
> tests.
>
> | | before | after |
> |---|---|---|
> | Deterministic checks | 9 pass, 23 fail | **32 pass, 0 fail** |
> | Suite | 546 passed, 32 xfailed | **600 passed, 0 xfailed** |
> | LLM-judged | 4 metrics pass | 4 metrics pass |
>
> The count control is now honoured by the *agent*, not merely by the model —
> which is the distinction the pre-fix report drew and could not act on.
> Verified live: 3 asked, 3 returned, on 6 runs post-fix.
>
> **BLOCKER-01 is unchanged.** The Test Hub still does not exist (issue #30).
> Note that BUG-04 was its stated prerequisite — an answer key outside the
> options — and that is now enforced in the schema, so a scorer built on
> `QuestionItem` can trust the key is selectable.
>
> Two known gaps are recorded rather than closed:
>
> * **Control conformance does not run on the production path.** Count, type and
>   difficulty checks need the request, which only `generate()` has, and
>   `RegistryAgentAdapter.run_raw` never calls it. Everything in the *schema*
>   does apply there, and four new tests prove it. Filed as follow-up.
> * `temperature=0.3` is hardcoded and no `max_tokens` is sent by any
>   `src/agents` agent, where the study lane documents a real gateway 402 from
>   an unbounded ceiling. Not in the bug list; not measured.
> * **Observed once, live:** an `mcq` request returned malformed JSON
>   (`"The LLM returned invalid JSON."`). Re-measured 6/6 clean afterwards, so
>   it is a model artefact rather than a regression - but the agents do not
>   retry a parse failure, and on the orchestrator path it is recorded as a
>   schema error rather than retried. Worth a decision if it recurs.
>
> Post-fix live coverage now spans all three question types, not just `mcq`:
> `true_false` returns `["True", "False"]` and `short_answer` returns `null`
> options, on both agents. The prompts were updated to state that rule, because
> the schema enforced something the prompt never asked for.

---

## Headline: half the brief has nothing to test

The brief asks me to *"assemble a test, complete an attempt through the UI, and
verify scoring against the answer key, including skipped or partial attempts"*
and to *"check for silent duplicates or dropped items upon re-running
generation."*

**None of that exists.** I searched every one of the 130 commits on every ref
in the repository. The string "hub" does not appear outside "github".

| Capability the brief requires | Present? | Evidence |
|---|---|---|
| Test Hub, in any spelling | **no** | zero hits across all refs |
| Assemble a test from generated questions | **no** | — |
| Attempt / answer-selection UI | **no** | no answer state in any `st.session_state` |
| Scoring against the answer key | **no** | `correct_answer` has 15 references repo-wide; **none reads it for comparison** |
| Attempts / scores persistence | **no** | 6 tables exist (`agent_runs`, `generated_outputs`, `reviews`, `system_events`, `documents`, `chunks`) |
| Question-level de-duplication across runs | **no** | dedup exists for documents, retrieval hits and topics — not questions |
| A Question Bank page at all | **no** | `src/app.py` has 8 pages; neither agent appears |

`QuestionBankAgent` and `TestHelpAgent` are orphaned. They are registered in
`src/agents/registry.py:57-63` and imported by **no UI** — reachable only from
tests and the orchestrator. `frontend/qbank_ui.py` is `def render(): pass`.

The nearest artifact is branch `feature/question-bank-week4`: unmerged, **87
commits behind `main`**, and its page *displays the answer key next to each
question* rather than testing anyone against it. It is a preview, not a hub.

**This is filed as BLOCKER-01.** I did not build the missing feature — that
would be writing the code I was asked to test — and I did not quietly drop the
deliverable. Testing continued against the two agents I was assigned.

---

## Scope of what was tested

| | |
|---|---|
| Under test | `src/agents/question_bank_agent.py`, `src/agents/test_help_agent.py` |
| Deterministic checks | 32, offline, no credentials |
| LLM-judged checks | 4 metrics × 2 agents × 3 questions × 3 repeats |
| Agent model | `gemini/gemini-flash-lite-latest` |
| Judge model | `gemini/gemini-flash-lite-latest` |

### What the agents actually do

`generate(content, question_type, difficulty, num_questions)` formats a prompt,
calls the gateway, then runs `json.loads` and `model_validate`. **That is the
entire pipeline.** For comparison, `mentor` and `concept` additionally run
`validate_difficulty()`, `verify_references()`, `validate_support()` and the
`ValidatorBase` guardrails. These two run none of them.

---

## Commands run

```bash
# Deterministic, offline, no credentials
python -m pytest tests/features/test_question_agents.py -v

# Retry-classification check
python -m pytest tests/features/test_platform_core.py::test_a_guarded_empty_choices_error_is_still_retryable -v

# Full suite, to confirm nothing else was disturbed
python -m pytest tests/ -q

# Live lane (needs .env credentials)
RUN_LIVE_TESTS=true python -m pytest tests/ -q

# LLM-judged (needs `pip install -e ".[eval]"` + credentials)
RUN_DEEPEVAL_TESTS=true python -m pytest tests/features/test_question_agents_deepeval.py -v
python scripts/run_question_agents_deepeval.py --repeats 3
```

### Evidence bundle

- [`test_reports/qbank_testhelp_pytest_2026-08-06.txt`](test_reports/qbank_testhelp_pytest_2026-08-06.txt) — per-test pass/xfail
- [`test_reports/qbank_testhelp_deepeval_2026-08-06.txt`](test_reports/qbank_testhelp_deepeval_2026-08-06.txt) — judge scores, negative controls, and every generated question

---

## Results — Question Bank & Test Help

**32 deterministic checks: 9 pass, 23 fail.**

Failures are recorded as `xfail(strict=True)` carrying the BUG id, so the suite
is green while documenting every defect. `strict=True` means a fix turns the
test XPASS — which pytest reports as a failure — forcing the marker to be
removed deliberately. The bug list cannot rot.

> **Read the green tick carefully.** `pytest tests/ -q` reports
> `546 passed, 32 xfailed, 0 failed`. The 23 defects are inside that
> "xfailed" number. CI is green *because* the bugs are documented, not because
> they are absent.

### Grounding & scope

| Check | Result | Ref |
|---|---|---|
| Questions derived from the source passage (LLM-judged) | **PASS** | derivability 1.00 / 1.00 / 1.00 |
| Questions do not contradict the source (LLM-judged) | **PASS** | faithfulness 1.00 / 1.00 / 1.00 |
| Topics absent from source are flagged by validation | **FAIL** | no grounding step exists at all |
| `verify_references()` is applied | **FAIL** | never called by these agents |
| `validate_support()` is meaningful | **FAIL** | BUG-12 — returns `[]` claims, so it passes anything |
| A `GroundedContext` reaches the model as text | **FAIL** | BUG-15 — arrives as a Pydantic repr |

The two passes are the model behaving well, not the system enforcing anything.
Nothing in the code inspects whether a generated question relates to the source;
the only grounding signal that exists for these agents is the judge I added.

### Controls & validation

| Check | Result | Ref |
|---|---|---|
| Question count honoured exactly | **FAIL** | BUG-01 — asked 1, accepted 3 |
| Question type honoured | **FAIL** | BUG-02 — reply type never compared to request |
| Difficulty honoured | **FAIL** | BUG-03 — same |
| `correct_answer` is among `options` | **FAIL** | BUG-04 |
| MCQ has options | **FAIL** | BUG-05 — `None` and `[]` both accepted |
| Empty question set rejected | **FAIL** | BUG-06 |
| Invalid `question_type` / `difficulty` rejected on input | **FAIL** | BUG-02/03 |
| `num_questions <= 0` rejected | **FAIL** | BUG-14 |
| Distractors are plausible (LLM-judged) | **PASS** | 0.90 / 1.00 / 1.00 |
| Answer key is defensible from the source (LLM-judged) | **PASS** | 1.00 / 1.00 / 1.00 |
| Controls reach the model in the prompt | **PASS** | — |
| Invalid JSON reported as such | **PASS** | — |
| Missing required field reported as schema failure | **PASS** | — |
| Fenced JSON parses | **FAIL** | BUG-10 |

Against the live gateway the model returned exactly 3 questions on all 6 runs
(3 repeats × 2 agents). **The count control was honoured by the model, never by
the agent** — the deterministic check proves the agent accepts any count.

### Human-review gate

| Check | Result | Ref |
|---|---|---|
| Output defaults to `requires_human_review=True` | **PASS** | live runs, all 6 |
| Model cannot set it to `False` | **FAIL** | BUG-07 |
| Flag cannot be flipped after construction | **FAIL** | BUG-07 |
| Export blocked until approved | **PASS (out of these agents' path)** | `assert_exportable` gates on `GeneratedOutput.status`, not on this flag |

The gate itself is sound — `src/exports/export.py:104-115` checks every output
before rendering anything. But it keys on `GeneratedOutput.status`, and **these
agents never build a `GeneratedOutput`**. `QuestionBankAgent.generate()` returns
a plain Pydantic object that a caller can serialize and ship. The
`requires_human_review` field on the schema is decoration unless the output goes
through the orchestrator.

### System stability

| Check | Result | Ref |
|---|---|---|
| Error-shaped HTTP 200 handled legibly | **FAIL (test_help only)** | BUG-08 — `TypeError` |
| Transient gateway errors retried consistently | **FAIL** | BUG-09 |
| Silent duplicates on re-run | **NOT TESTABLE** | no de-duplication exists |
| Dropped items on re-run | **NOT TESTABLE** | nothing tracks questions across runs |

BUG-09 is the subtlest finding and the one most likely to be made worse by a
careless fix: `question_bank`'s **correct** guard raises `ValueError`, which is
not in `transient_errors` and is therefore never retried, while `test_help`'s
**buggy** unguarded dereference raises `TypeError`, which the orchestrator
translates to `UpstreamResponseError` and *does* retry. Copying the good guard
into `test_help` would silently switch its retries off.

---

## Results — Test Hub end to end

**Not executed. No implementation exists.** See BLOCKER-01.

| Brief requirement | Status |
|---|---|
| Assemble a test | blocked |
| Complete an attempt through the UI | blocked |
| Scoring matches the answer key | blocked |
| Skipped / partial attempts | blocked |
| Silent duplicates on regeneration | blocked |

Worth noting for whoever picks this up: **BUG-04 is a prerequisite.** A scorer
compares a selection against `correct_answer`, and nothing currently guarantees
that value is one of the options. Building scoring on top of the schema as it
stands produces questions that mark every attempt wrong.

---

## On the LLM-judged results

Two of the three metrics I wrote were **wrong on the first attempt**, and only
negative controls revealed it. Recorded here because the same trap will catch
the next person.

**`FaithfulnessMetric` does not measure grounding.** It scored a wholly
fabricated question **1.00**:

> *"Which Python loop runs on the GPU by default? The correct answer is: the
> parallel-for loop. Because: Python compiles for loops to CUDA kernels
> automatically."*
>
> — judge's reason: *"completely faithful to the retrieval context with no
> contradictions found. Great job!"*

The passage says nothing about GPUs, so the invention contradicts nothing.
Faithfulness is a **contradiction detector**; "derived from the source" needs
absence penalised explicitly. I added a `Source derivability` GEval for that and
kept Faithfulness for what it does catch. Had I not controlled it, this report
would have claimed grounding was verified on the strength of a metric that
passes fabrication.

**The answer-key metric contradicted itself.** It returned `0.1` while its own
stated reason read *"correctly marks 'break' as the correct answer … this aligns
with a score of 1"*. Prescribing literal numbers ("Score 1 if… Score 0 if…") in
`evaluation_steps` fights GEval's continuous scoring. Rephrased as qualities, it
now scores correctly-keyed questions 1.0 and a mis-keyed one 0.0.

**All six negative controls pass** and are re-run by
`scripts/run_question_agents_deepeval.py` on every invocation, so the controls
travel with the evidence rather than being a one-off claim.

### Reading these numbers

Scores are **LLM-judged and non-deterministic**. The threshold of 0.7 is a
floor, not a grade — a smoke alarm. Reported as min/median/max over 3 repeats,
never as a bare mean. Both models are `-latest` ids, which float: these numbers
are tied to 2026-08-06 and will drift.

The judge is the same lite model that generates the content. That is a weak
check — a stronger judge can be pinned via `DEEPEVAL_JUDGE_MODEL` without
touching `DEFAULT_MODEL` — and it is the main reason to treat the passes as
"nothing obviously wrong" rather than "verified".

---

## How to run this

```bash
pip install -r requirements.txt          # deterministic checks; deepeval NOT included
python -m pytest tests/ -q

pip install -e ".[eval]"                 # adds deepeval
RUN_DEEPEVAL_TESTS=true python -m pytest tests/features/test_question_agents_deepeval.py -v
```

The LLM-judged layer is excluded from CI **by construction**: `requirements.txt`
installs `.[ocr,dev]` and deepeval lives in `.[eval]`, so no workflow edit can
accidentally let non-deterministic, billable checks into the build.

Be aware that installing `.[eval]` pulls `pytest-asyncio`, `pytest-xdist`,
`pytest-repeat` and `pytest-rerunfailures`, which pytest auto-loads into *every*
local run. Use a separate virtualenv if that is a problem.

---

## Summary

| | |
|---|---|
| Deterministic checks | 32 — **9 pass, 23 fail** |
| LLM-judged checks | 4 metrics × 2 agents × 3 repeats — **all pass** |
| Negative controls on the judge | 6 — **all behave correctly** |
| Bugs filed | 13 (3 high, 6 medium, 4 low) |
| Blockers filed | 1 — the Test Hub does not exist |
| Fixed in this branch | BUG-11/13, the dead live-test lane |
| Test Hub deliverable | **not executable** |

The agents produce good content when the model behaves — grounded questions,
plausible distractors, correct answer keys, all judged 0.90–1.00. What they do
not do is **check any of it**. Every control the brief asks about is passed to
the model as a request and accepted back on trust.

Recommended fix order: **BUG-08 + BUG-09 together** (a crash, plus a retry
regression waiting to be introduced by the obvious fix), then **BUG-04/05/06/01**
(the deliverable is wrong), then **BUG-07** (a governance control the model can
switch off). None of the fixes are in this branch: this is a QA deliverable, and
mixing fixes in would destroy the evidence.
