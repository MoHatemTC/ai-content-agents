# Bug list — Question Bank & Test Help agents

**Date:** 2026-08-06 · **Sprint:** 4 · **Owner:** Nour Atef
**Commit under test:** `8c601b7` (branch `qa/question-agents-sprint4`, off `main` `6a60568`)
**Related report:** [`docs/test_report_question_bank_test_help.md`](../test_report_question_bank_test_help.md)

---

> ## Status: all 13 fixed
>
> Fixed on branch `fix/question-agents-contract`, stacked on the QA branch.
> Every reproduction command below was **re-run against the fixed code** and now
> produces its documented "Expected" result instead of the "Observed" one — the
> Observed lines are kept as the record of what was wrong.
>
> The 32 `xfail(strict=True)` markers that encoded these bugs are all gone.
> `strict=True` is what forced them out: a fix turns the test XPASS, which
> pytest reports as a failure until the marker is deliberately removed. Each
> test keeps a `# Closes BUG-nn` comment, so `grep -rn "BUG-" tests/` still maps
> tests to this list.
>
> Suite: **546 passed + 32 xfailed = 578** before, **600 passed** after — the
> delta being 22 new tests (14 negative controls, 8 driving the production path).
>
> Two entries are worth reading even though they are closed:
>
> * **BUG-08/09** had to be fixed *together*. Copying question_bank's guard into
>   test_help — the obvious fix — would have swapped a retried `TypeError` for
>   an un-retried `ValueError` and silently switched retries off. Verified by
>   mutation: making that change fails four tests.
> * **BUG-07** is fixed by *overriding* the flag, not by rejecting the reply.
>   Rejecting would let a prompt injection in an uploaded document fail every
>   generation — trading a review bypass for a denial of service.
>
> One thing deliberately **not** done: requiring at least one reference per
> question in the schema. `ReferencesPresentRule` already checks it, and moving
> it into the schema would reclassify the failure from a guardrail violation to
> a schema error — which drops the output from the groundedness *denominator*,
> so an ungrounded question would **improve** the groundedness rate. A metric
> that lies is worse than a missing validator.

---

Every reproduction below is a self-contained command run from the repository
root. The offline ones need no credentials and make no network call.

Set up once:

```bash
pip install -r requirements.txt
```

A shared preamble is used by several repros. Save it as `repro.py`:

```python
import json, sys
sys.path.insert(0, ".")
from tests.conftest import FakeLLMClient
from src.agents.question_bank_agent import QuestionBankAgent
from src.agents.test_help_agent import TestHelpAgent

def q(**over):
    item = {"question": "Which loop repeats while a condition is true?",
            "options": ["for", "while", "if", "switch"],
            "correct_answer": "while", "rationale": "A while loop repeats.",
            "difficulty": "beginner", "type": "mcq",
            "references": [{"segment_id": "chunk_001", "text": "src"}]}
    return {**item, **over}

def reply(items, review=True):
    return json.dumps({"questions": items, "requires_human_review": review})

def agent(cls, *replies):
    return cls(client=FakeLLMClient(*replies), model="test-model")

SOURCE = "Python provides two loop types: for and while."
```

---

## Severity: high

### BUG-08 — `TestHelpAgent` crashes with `TypeError` on an error-shaped HTTP 200

**Where:** `src/agents/test_help_agent.py:152`
**Affects:** `TestHelpAgent` only. `QuestionBankAgent` guards this correctly at
`src/agents/question_bank_agent.py:149`.

OpenAI-compatible gateways answer `200` with `{"choices": null, "error": {...}}`
when a provider is saturated. This is documented in
`src/validation/orchestrator.py:55-70` as the reason `UpstreamResponseError`
exists, so it is a known, expected condition — not a hypothetical.

`test_help_agent.py` does `response.choices[0].message.content` unconditionally.

**Reproduce:**

```bash
python -c "
exec(open('repro.py').read())
from tests.conftest import Reply
for cls in (QuestionBankAgent, TestHelpAgent):
    c = cls(client=FakeLLMClient(Reply(error={'message':'provider saturated'})), model='m')
    try:
        c.generate(SOURCE, 'mcq', 'beginner', 1)
    except Exception as e:
        print(f'{cls.__name__:20} {type(e).__name__}: {e}')
"
```

**Observed:**

```
QuestionBankAgent    ValueError: The LLM returned no choices.
TestHelpAgent        TypeError: 'NoneType' object is not subscriptable
```

**Expected:** both raise a legible error naming the gateway condition.

**Impact:** the error names neither the cause nor a remedy, and is not
recognisably retryable. **Read BUG-09 before fixing this one** — the obvious
fix makes retries worse.

**Automated check:**
`tests/features/test_question_agents.py::test_an_error_shaped_success_is_a_legible_error[test_help]`

---

### BUG-09 — the correct empty-choices guard is *not* retried; the buggy one is

**Where:** `src/validation/orchestrator.py:168` and `:271-273` (the
`transient_errors` set), against `src/agents/question_bank_agent.py:149`.

`Orchestrator.transient_errors` is `(APIConnectionError, APITimeoutError,
InternalServerError, RateLimitError, UpstreamResponseError)`. The adapter
catches `TypeError` and translates it to `UpstreamResponseError`, which *is*
transient.

So the agent with the **bug** (BUG-08, raises `TypeError`) gets retried, and
the agent with the **correct guard** (raises `ValueError`) does not.

**Reproduce:**

```bash
python -c "
import sys; sys.path.insert(0, '.')
from src.validation.orchestrator import _default_transient_errors
print('transient:', [e.__name__ for e in _default_transient_errors()])
print('ValueError is transient?', any(e is ValueError for e in _default_transient_errors()))
"
```

**Observed:** `ValueError is transient? False`

**Impact:** fixing BUG-08 by copying question_bank's guard into test_help — the
obvious fix — swaps a retried `TypeError` for an un-retried `ValueError`, and
**silently turns off retries for a genuinely transient provider condition.**
The guard and the transient-error set must change together. Preferred fix:
raise `UpstreamResponseError` from both agents.

**Automated check:**
`tests/features/test_platform_core.py::test_a_guarded_empty_choices_error_is_still_retryable`

---

### BUG-07 — the model can switch off the human-review gate

**Where:** `src/validation/schemas.py:113` (`QuestionBankOutput`) and `:138`
(`TestHelpOutput`).

Both declare `requires_human_review: bool = True` — a plain, mutable field the
model fills in. `MentorOutput` (`schemas.py:175`) and `ConceptOutput`
(`schemas.py:210`) declare
`requires_human_review: Literal[True] = Field(default=True, frozen=True)`,
which rejects `False` and cannot be reassigned.

**Reproduce:**

```bash
python -c "
exec(open('repro.py').read())
out = agent(QuestionBankAgent, reply([q()], review=False)).generate(SOURCE, 'mcq', 'beginner', 1)
print('model returned false ->', out.requires_human_review)
out.requires_human_review = False
print('mutable after construction ->', out.requires_human_review)
"
```

**Observed:**

```
model returned false -> False
mutable after construction -> False
```

**Expected:** `True` in both cases, as for mentor and concept.

**Impact:** a governance control the system is supposed to enforce is
delegated to the thing being controlled. A model that omits or negates the
field — by accident, or because a prompt injection in an uploaded document
asked it to — marks its own output as not needing review.

**Automated checks:**
`test_the_model_cannot_switch_off_human_review`,
`test_the_review_flag_cannot_be_flipped_after_the_fact`

---

## Severity: medium

### BUG-01 — `num_questions` is a suggestion, not a contract

**Where:** `src/agents/question_bank_agent.py:216-228`,
`src/agents/test_help_agent.py:200-212`.

The requested count is interpolated into the prompt and never checked against
the reply.

**Reproduce:**

```bash
python -c "
exec(open('repro.py').read())
out = agent(QuestionBankAgent, reply([q()]*3)).generate(SOURCE, 'mcq', 'beginner', 1)
print('asked 1, got', len(out.questions))
"
```

**Observed:** `asked 1, got 3` · **Expected:** rejection, or documented truncation.

**Note:** against the live gateway the model complied on every observed run
(3 asked, 3 returned, ×3 runs, both agents — see the evidence bundle). That is
the model behaving, not the agent enforcing. The control is unenforced either
way.

**Automated check:** `test_the_requested_question_count_is_enforced`

---

### BUG-04 — `correct_answer` is never checked against `options`

**Where:** `src/validation/schemas.py:56-97` (`QuestionItem`). The file contains
no `@field_validator` or `@model_validator` at all.

**Reproduce:**

```bash
python -c "
exec(open('repro.py').read())
out = agent(QuestionBankAgent, reply([q(correct_answer='a fifth option entirely')])).generate(SOURCE, 'mcq', 'beginner', 1)
item = out.questions[0]
print('options       :', item.options)
print('correct_answer:', item.correct_answer)
print('answer in options?', item.correct_answer in (item.options or []))
"
```

**Observed:** `answer in options? False`, accepted.

**Impact:** the question is unanswerable — nobody can select the key, and any
scorer comparing a selection against it marks every attempt wrong. This is
directly load-bearing for the scoring the Sprint-4 brief asks about.

**Automated check:** `test_the_correct_answer_is_one_of_the_options`

---

### BUG-05 — an MCQ can have no options

**Where:** `src/validation/schemas.py:66` — `options: Optional[List[str]] = None`
with no conditional on `type`.

**Reproduce:**

```bash
python -c "
exec(open('repro.py').read())
for empty in (None, []):
    out = agent(QuestionBankAgent, reply([q(options=empty)])).generate(SOURCE, 'mcq', 'beginner', 1)
    print(f'type={out.questions[0].type.value} options={out.questions[0].options!r} -> accepted')
"
```

**Observed:** both accepted. **Expected:** rejection for `type == "mcq"`.

**Automated check:** `test_a_multiple_choice_question_has_options`

---

### BUG-06 — an empty question set is a success

**Reproduce:**

```bash
python -c "
exec(open('repro.py').read())
out = agent(QuestionBankAgent, reply([])).generate(SOURCE, 'mcq', 'beginner', 5)
print('asked 5, got', len(out.questions), '- no error raised')
"
```

**Observed:** `asked 5, got 0 - no error raised`

**Automated check:** `test_an_empty_question_set_is_rejected`

---

### BUG-12 — support validation is silently vacuous for these agents

**Where:** `src/validation/support_validator.py:21-26` (`_CLAIM_FIELDS`) and
`:83-101` (`extract_claim_text`).

`_CLAIM_FIELDS` is `("definition", "explanation", "key_points", "next_steps")`.
`QuestionItem` has none of them.

**Reproduce:**

```bash
python -c "
import sys; sys.path.insert(0, '.')
from src.validation.support_validator import _CLAIM_FIELDS, extract_claim_text
from src.validation.schemas import QuestionBankOutput
o = QuestionBankOutput.model_validate({'questions':[{'question':'Q?','options':['a','b'],
    'correct_answer':'a','rationale':'r','difficulty':'beginner','type':'mcq',
    'references':[{'segment_id':'s','text':'t'}]}]})
print('_CLAIM_FIELDS =', _CLAIM_FIELDS)
print('claims extracted from a question bank ->', extract_claim_text(o))
"
```

**Observed:** `claims extracted from a question bank -> []`

**Impact:** `validate_support([], ctx)` returns `supported=True`, so if anyone
wires support validation into these agents believing it protects them, it will
pass everything. A check that cannot fail is worse than no check, because it
looks like coverage. Fixing it requires extending `_CLAIM_FIELDS` **and**
teaching the extractor to descend into `questions[]`.

---

### BUG-15 — a `GroundedContext` is stringified into the prompt

**Where:** `src/agents/question_bank_agent.py:87` / `test_help_agent.py:90`.
Neither has the `isinstance(content, GroundedContext)` branch that
`src/agents/mentor_agent.py:119` has, and neither accepts a `context=`
parameter.

**Reproduce:**

```bash
python -c "
exec(open('repro.py').read())
from src.retrieval.models import Chunk, GroundedContext, RetrievalScope, RetrievedChunk
ch = Chunk(chunk_id='doc1-c0000', document_id='doc1', ordinal=0, text='Loops repeat instructions.')
ctx = GroundedContext(query='loops', scope=RetrievalScope(document_id='doc1'),
                      chunks=[RetrievedChunk(chunk=ch, score=1.0, rank=1)])
c = FakeLLMClient(reply([q()]))
QuestionBankAgent(client=c, model='m').generate(ctx, 'mcq', 'beginner', 1)
print('RetrievalScope( in prompt ->', 'RetrievalScope(' in c.prompt)
"
```

**Observed:** `RetrievalScope( in prompt -> True`

**Impact:** the model receives Python object syntax wrapped around the passage.
The orchestrator avoids this by calling `as_prompt_content()` itself before
handing over a plain string, so the defect only bites callers who pass the
context directly — which is the natural thing to try.

**Automated check:** `test_a_grounded_context_is_not_silently_stringified`

---

## Severity: low

### BUG-02 / BUG-03 — `question_type` and `difficulty` are never validated

Neither on the way in nor against the reply. `validate_difficulty()` exists at
`src/validation/schemas.py:35` and is called by `mentor_agent.py:197`; these
two agents never call it.

**Reproduce:**

```bash
python -c "
exec(open('repro.py').read())
c = FakeLLMClient(reply([q()]))
QuestionBankAgent(client=c, model='m').generate(SOURCE, 'ESSAY_BANANA', 'impossible', 1)
p = c.prompt
print('bad type reached the model      :', 'ESSAY_BANANA' in p)
print('bad difficulty reached the model:', 'impossible' in p)
"
```

**Observed:** both `True`.

**Impact:** when the model echoes the bad value back, `DifficultyLevel` rejects
it and the failure surfaces as the generic *"The LLM response does not match
QuestionBankOutput schema"* — pointing at the model instead of at the caller who
passed nonsense.

**Automated checks:** `test_unknown_control_values_are_rejected`,
`test_the_requested_question_type_is_enforced`,
`test_the_requested_difficulty_is_enforced`

---

### BUG-14 — `num_questions` has no lower bound

```bash
python -c "
exec(open('repro.py').read())
c = FakeLLMClient(reply([q()]))
QuestionBankAgent(client=c, model='m').generate(SOURCE, 'mcq', 'beginner', -5)
print('prompt contains \"exactly -5\":', 'exactly -5' in c.prompt)
"
```

**Observed:** `True` — the prompt reads *"Generate exactly -5 questions."*

**Automated check:** `test_a_nonsensical_question_count_is_rejected`

---

### BUG-10 — no code-fence stripping

Models wrap JSON in ``` blocks despite being told not to. `strip_fences()`
already exists at `src/study/llm_client.py:143` and is not reused here.

```bash
python -c "
exec(open('repro.py').read())
try:
    agent(QuestionBankAgent, '\`\`\`json\n' + reply([q()]) + '\n\`\`\`').generate(SOURCE, 'mcq', 'beginner', 1)
except ValueError as e:
    print('ValueError:', e)
"
```

**Observed:** `ValueError: The LLM returned invalid JSON.` — for output that was
otherwise perfect.

**Automated check:** `test_a_fenced_reply_still_parses`

---

### BUG-11 / BUG-13 — the live test lane was dead *(fixed in this branch)*

**Where:** `tests/test_question_bank_live.py:20`, `tests/test_test_help_live.py:20`,
`tests/test_live_output_preview.py:27,46,65,89`,
`tests/test_mentor_agent_live.py:17`, `tests/test_concept_agent_live.py:17`,
`tests/test_invalid_json.py:28,48`.

PR #29 removed `mock_mode` from the agents but left `Agent(mock_mode=False)` at
these call sites, plus reads of the removed `agent.mock_mode` attribute. Every
one raised `TypeError`.

Nothing caught it: the files are `skipif RUN_LIVE_TESTS`, so CI never collects
them, and `ruff --select F` sees only undefined names, not runtime `TypeError`s.

**This one is mine** — my verification for #29 grepped `src/` only, which is the
one directory the defect was not in.

**Fixed in commit `3faae1e`.** Verified: `RUN_LIVE_TESTS=true pytest -q` now
collects 543 tests and the four live agent files pass against the real gateway.

---

## Not a bug in these agents — a missing feature

### BLOCKER-01 — the Test Hub does not exist

Covered in full in the test report. Summary: no test assembly, no attempt UI,
no scoring, no attempts/scores persistence, no question-level de-duplication,
and on `main` not even a page that generates questions. `correct_answer` has 15
references across the repository and **none of them reads it for comparison**.

Half the Sprint-4 brief has no implementation to test.
