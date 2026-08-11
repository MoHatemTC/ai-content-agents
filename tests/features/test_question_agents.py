"""Sprint-4 QA: contract checks for the Question Bank and Test Help agents.

Every test here asserts the behaviour the Sprint-4 brief requires - questions
grounded in the source, question type and count honoured *exactly*, valid
correct answers and distractors, outputs held behind the human-review gate.

**These were written as ``xfail(strict=True)`` against an implementation that
did none of it**, so the suite was the bug list in executable form. Every one
of those markers is now gone: the fixes landed in
:mod:`src.agents.question_agent_base` and :mod:`src.validation.schemas`, and
``strict=True`` is what forced the markers out - a fix turns the test XPASS,
which pytest reports as a failure until someone deliberately removes it.

Each test keeps a ``# Closes BUG-nn`` comment so ``grep -rn "BUG-" tests/``
still maps it to the bug list in
``docs/test_reports/qbank_testhelp_bugs_2026-08-06.md``.

No test here touches the network. All of them drive `FakeLLMClient` from
`tests/conftest.py`.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from src.agents.question_agent_base import (
    QUESTION_ITEM_TOKENS,
    QuestionCountError,
)
from src.agents.question_bank_agent import QuestionBankAgent
from src.agents.test_help_agent import TestHelpAgent
from src.retrieval.models import (
    Chunk,
    GroundedContext,
    RetrievalScope,
    RetrievedChunk,
)
from src.validation.review_schema import OutputStatus, RunStatus
from src.validation.schemas import QuestionBankOutput, TestHelpOutput
from src.validation.store import PlatformStore
from src.llm_gateway import UpstreamResponseError
from src.study.llm_client import (
    MAX_OUTPUT_TOKENS,
    OUTPUT_OVERHEAD_TOKENS,
    max_tokens_default,
    output_budget,
)
from tests.conftest import FakeLLMClient, Reply

# Both agents are near-identical copies of each other, so every check runs
# against both. That is the point: where they diverge (BUG-08) the divergence
# shows up here rather than hiding in two separate files nobody diffs.
AGENTS = [
    pytest.param(QuestionBankAgent, QuestionBankOutput, id="question_bank"),
    pytest.param(TestHelpAgent, TestHelpOutput, id="test_help"),
]

SOURCE = (
    "Python provides two loop types: for and while. "
    "A for loop iterates over a sequence. "
    "A while loop repeats until its condition becomes false."
)


def question(**overrides) -> dict:
    """A schema-valid MCQ item; override one field to make it invalid."""
    item = {
        "question": "Which loop repeats while a condition is true?",
        "options": ["for", "while", "if", "switch"],
        "correct_answer": "while",
        "rationale": "A while loop repeats while its condition evaluates to true.",
        "difficulty": "beginner",
        "type": "mcq",
        "references": [{"segment_id": "chunk_001", "text": SOURCE}],
    }
    return {**item, **overrides}


def reply(items: list[dict], *, review: bool = True) -> str:
    return json.dumps({"questions": items, "requires_human_review": review})


def agent_with(agent_class, *replies):
    """An agent wired to a fake gateway. Never reaches the network.

    Note this uses ``FakeLLMClient``, not ``CompliantAgentsClient``. The
    compliant double reads ``num_questions`` back out of the prompt and returns
    exactly that many, so a count test built on it would pass whether or not
    the agent enforced anything - it would be testing the double.
    """
    return agent_class(client=FakeLLMClient(*replies), model="test-model")


# --------------------------------------------------------------------------- #
# Controls: type and count must be honoured exactly
# --------------------------------------------------------------------------- #


# Closes BUG-01: the count was a prompt suggestion, not a contract.
@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_the_requested_question_count_is_enforced(agent_class, schema) -> None:
    """Asking for one question and getting three is a defect, not a preference.

    The brief requires the count control to be honoured *exactly*. A model that
    over- or under-delivers is normal; silently passing that through to the
    learner is not.
    """
    # Two replies, because a wrong count is retried once now. A model that
    # stays non-compliant is what this test is about; one that complies on the
    # second attempt is covered separately.
    client = FakeLLMClient(reply([question()] * 3), reply([question()] * 3))
    agent = agent_class(client=client, model="test-model")

    with pytest.raises(QuestionCountError, match="exactly 1"):
        agent.generate(SOURCE, "mcq", "beginner", 1)

    assert len(client.calls) == 2, "the wrong count was not retried"


# Closes BUG-02: the reply's type was never compared with the request.
@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_the_requested_question_type_is_enforced(agent_class, schema) -> None:
    agent = agent_with(
        agent_class, reply([question(type="short_answer", options=None)])
    )

    with pytest.raises(ValueError, match="mcq"):
        agent.generate(SOURCE, "mcq", "beginner", 1)


# Closes BUG-03: the reply's difficulty was never compared with the request.
@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_the_requested_difficulty_is_enforced(agent_class, schema) -> None:
    agent = agent_with(agent_class, reply([question(difficulty="advanced")]))

    with pytest.raises(ValueError, match="beginner"):
        agent.generate(SOURCE, "mcq", "beginner", 1)


# --------------------------------------------------------------------------- #
# Answer keys and distractors must be usable
# --------------------------------------------------------------------------- #


# Closes BUG-04: correct_answer was never checked against options.
@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_the_correct_answer_is_one_of_the_options(agent_class, schema) -> None:
    """An answer key outside the options makes the question unanswerable.

    Nobody taking the test can pick it, and any scorer comparing a selection
    against it marks every attempt wrong.
    """
    agent = agent_with(
        agent_class, reply([question(correct_answer="a fifth option entirely")])
    )

    with pytest.raises(ValueError, match="correct_answer"):
        agent.generate(SOURCE, "mcq", "beginner", 1)


# Closes BUG-05: an mcq with options=None validated cleanly.
@pytest.mark.parametrize("agent_class,schema", AGENTS)
@pytest.mark.parametrize("empty", [None, []], ids=["none", "empty-list"])
def test_a_multiple_choice_question_has_options(agent_class, schema, empty) -> None:
    agent = agent_with(agent_class, reply([question(options=empty)]))

    with pytest.raises(ValueError, match="options"):
        agent.generate(SOURCE, "mcq", "beginner", 1)


# Closes BUG-06: questions=[] satisfied the schema.
@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_an_empty_question_set_is_rejected(agent_class, schema) -> None:
    agent = agent_with(agent_class, reply([]))

    with pytest.raises(ValueError, match="at least 1"):
        agent.generate(SOURCE, "mcq", "beginner", 1)


# --------------------------------------------------------------------------- #
# The human-review gate
# --------------------------------------------------------------------------- #


# Closes BUG-07: the flag was a plain mutable bool the model filled in.
@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_the_model_cannot_switch_off_human_review(agent_class, schema) -> None:
    """The review flag is a control over the system, not an output of it.

    A model that returns ``requires_human_review: false`` - by accident, or
    because a prompt injection in the source document asked it to - must not be
    able to mark its own work final.
    """
    agent = agent_with(agent_class, reply([question()], review=False))

    result = agent.generate(SOURCE, "mcq", "beginner", 1)

    assert result.requires_human_review is True


# Closes BUG-07: the flag was not frozen, so any caller could flip it.
@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_the_review_flag_cannot_be_flipped_after_the_fact(agent_class, schema) -> None:
    agent = agent_with(agent_class, reply([question()]))
    result = agent.generate(SOURCE, "mcq", "beginner", 1)

    # ValidationError specifically: a bare Exception would also be satisfied by
    # an AttributeError from a typo in the field name.
    with pytest.raises(ValidationError):
        result.requires_human_review = False


# --------------------------------------------------------------------------- #
# Input validation
# --------------------------------------------------------------------------- #


# Closes BUG-02/03: neither control was validated on the way in.
@pytest.mark.parametrize("agent_class,schema", AGENTS)
@pytest.mark.parametrize(
    "question_type,difficulty",
    [("ESSAY_BANANA", "beginner"), ("mcq", "impossible")],
    ids=["bad-type", "bad-difficulty"],
)
def test_unknown_control_values_are_rejected(
    agent_class, schema, question_type, difficulty
) -> None:
    """Bad input should fail fast, naming the offending value.

    Today it is interpolated into the prompt verbatim and the model is left to
    cope. When it echoes the bad value back, the failure surfaces as the
    generic "does not match schema" - which sends you to the model instead of
    to the caller who passed nonsense.
    """
    agent = agent_with(agent_class, reply([question()]))

    with pytest.raises(ValueError, match="Invalid"):
        agent.generate(SOURCE, question_type, difficulty, 1)


# Closes BUG-14: num_questions had no lower bound.
@pytest.mark.parametrize("agent_class,schema", AGENTS)
@pytest.mark.parametrize("count", [0, -5], ids=["zero", "negative"])
def test_a_nonsensical_question_count_is_rejected(agent_class, schema, count) -> None:
    agent = agent_with(agent_class, reply([question()]))

    with pytest.raises(ValueError, match="num_questions"):
        agent.generate(SOURCE, "mcq", "beginner", count)


# --------------------------------------------------------------------------- #
# Gateway and parsing failures
# --------------------------------------------------------------------------- #


# Closes BUG-08: test_help indexed response.choices[0] unguarded and raised
# TypeError, while question_bank guarded the same case and raised ValueError.
# Both now raise UpstreamResponseError, which is the type the orchestrator's
# retry policy recognises - see BUG-09.
@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_an_error_shaped_success_is_a_legible_error(agent_class, schema) -> None:
    """OpenAI-compatible gateways answer 200 with choices=null when saturated.

    Not hypothetical: it is documented in orchestrator.py as the reason
    UpstreamResponseError exists. The two agents used to disagree about what to
    do with it, which is the asymmetry this parametrisation existed to surface;
    they now share one implementation, so they cannot.

    Note this asserts UpstreamResponseError rather than the ValueError the QA
    branch expected. That is a deliberate contract change, not a relaxation:
    UpstreamResponseError subclasses RuntimeError and is in
    Orchestrator.transient_errors, so raising it is what makes a saturated
    provider retryable instead of being recorded as a permanent failure.
    """
    # Two, because generate() now retries: a provider that recovers on the
    # second call is the case retry exists for, so staying saturated is what
    # this test is actually about.
    client = FakeLLMClient(
        Reply(error={"message": "provider saturated"}),
        Reply(error={"message": "provider saturated"}),
    )
    agent = agent_class(client=client, model="test-model")

    with pytest.raises(UpstreamResponseError, match="no choices"):
        agent.generate(SOURCE, "mcq", "beginner", 1)

    assert len(client.calls) == 2, "a saturated provider was not retried"


# Closes BUG-10: no fence stripping, so a fenced reply failed to parse.
@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_a_fenced_reply_still_parses(agent_class, schema) -> None:
    agent = agent_with(agent_class, f"```json\n{reply([question()])}\n```")

    result = agent.generate(SOURCE, "mcq", "beginner", 1)

    assert len(result.questions) == 1


# --------------------------------------------------------------------------- #
# Regression guards - these pass today and must keep passing
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_invalid_json_is_reported_as_such(agent_class, schema) -> None:
    agent = agent_with(agent_class, "Sure! Here are your questions:")

    with pytest.raises(ValueError, match="invalid JSON"):
        agent.generate(SOURCE, "mcq", "beginner", 1)


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_a_missing_required_field_is_reported_as_a_schema_failure(
    agent_class, schema
) -> None:
    incomplete = question()
    del incomplete["rationale"]
    agent = agent_with(agent_class, reply([incomplete]))

    with pytest.raises(ValueError, match="schema"):
        agent.generate(SOURCE, "mcq", "beginner", 1)


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_the_controls_reach_the_model(agent_class, schema) -> None:
    """Whatever the agent fails to enforce, it must at least *ask* correctly."""
    client = FakeLLMClient(reply([question()] * 3))
    agent_class(client=client, model="test-model").generate(
        SOURCE, "mcq", "beginner", 3
    )

    prompt = client.prompt
    assert SOURCE in prompt, "the source content never reached the model"
    assert "mcq" in prompt
    assert "beginner" in prompt
    assert "3" in prompt


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_the_reply_is_parsed_into_the_agents_own_schema(agent_class, schema) -> None:
    """question_bank and test_help must not be interchangeable by accident."""
    agent = agent_with(agent_class, reply([question()]))

    result = agent.generate(SOURCE, "mcq", "beginner", 1)

    assert isinstance(result, schema)


# Closes BUG-15: a GroundedContext was str.format-ed in as a Pydantic repr.
@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_a_grounded_context_is_not_silently_stringified(agent_class, schema) -> None:
    """These agents have no `context` parameter, unlike mentor and concept.

    Passing a GroundedContext as `content` - the obvious thing to try - dumps a
    Pydantic repr into the prompt, so the model sees object syntax wrapped
    around the passage instead of the passage.

    The assertion is deliberately on the *absence of repr syntax*, not on the
    presence of the passage text. The text appears inside the repr too, so
    `SOURCE in prompt` passes whether or not the defect is present - a test
    that cannot fail for the reason it names.
    """
    from src.retrieval.models import (
        Chunk,
        GroundedContext,
        RetrievalScope,
        RetrievedChunk,
    )

    chunk = Chunk(chunk_id="doc1-c0000", document_id="doc1", ordinal=0, text=SOURCE)
    context = GroundedContext(
        query="loops",
        scope=RetrievalScope(document_id="doc1"),
        chunks=[RetrievedChunk(chunk=chunk, score=1.0, rank=1)],
    )

    client = FakeLLMClient(reply([question()]))
    agent_class(client=client, model="test-model").generate(
        context, "mcq", "beginner", 1
    )

    prompt = client.prompt
    assert "RetrievalScope(" not in prompt, (
        "a Pydantic repr reached the model instead of the passage text"
    )
    assert "chunk_id=" not in prompt


# --------------------------------------------------------------------------- #
# Negative controls
#
# Every fix above is an enforcement, and an enforcement that rejects everything
# also turns its test green. These pin the other side of each rule: the valid
# case must still pass. Without them "the count is enforced" is satisfied by an
# agent that refuses all output.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_the_exact_requested_count_is_accepted(agent_class, schema) -> None:
    """Control for BUG-01: N questions for a request of N must not raise."""
    agent = agent_with(agent_class, reply([question()] * 3))

    result = agent.generate(SOURCE, "mcq", "beginner", 3)

    assert len(result.questions) == 3


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_a_short_answer_question_may_have_no_options(agent_class, schema) -> None:
    """Control for BUG-05: the options rule must not catch short_answer.

    The prompts explicitly instruct the model to send null options for
    short_answer (src/prompts/test_help.yaml), so rejecting it would make the
    agent contradict its own prompt.
    """
    agent = agent_with(
        agent_class,
        reply([question(type="short_answer", options=None, correct_answer="a while loop")]),
    )

    result = agent.generate(SOURCE, "short_answer", "beginner", 1)

    assert result.questions[0].options is None


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_a_true_false_question_needs_options_too(agent_class, schema) -> None:
    """A true/false question with nothing to choose from is as broken as an MCQ."""
    agent = agent_with(
        agent_class,
        reply([question(type="true_false", options=None, correct_answer="True")]),
    )

    with pytest.raises(ValueError, match="options"):
        agent.generate(SOURCE, "true_false", "beginner", 1)


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_an_answer_key_among_the_options_is_accepted(agent_class, schema) -> None:
    """Control for BUG-04: a valid key must not be rejected."""
    agent = agent_with(agent_class, reply([question(correct_answer="for")]))

    result = agent.generate(SOURCE, "mcq", "beginner", 1)

    assert result.questions[0].correct_answer == "for"


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_every_valid_control_value_is_accepted(agent_class, schema) -> None:
    """Control for BUG-02/03/14: the whole allowed set must get through."""
    for difficulty in ("beginner", "intermediate", "advanced"):
        agent = agent_with(agent_class, reply([question(difficulty=difficulty)]))
        result = agent.generate(SOURCE, "mcq", difficulty, 1)
        assert result.questions[0].difficulty.value == difficulty


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_a_compliant_reply_is_not_warned_about(agent_class, schema, caplog) -> None:
    """Control for BUG-07: forcing the flag must be silent when nothing is wrong.

    A warning on every generation would train people to ignore the one that
    matters - a prompt injection actually trying to switch review off.
    """
    agent = agent_with(agent_class, reply([question()], review=True))

    with caplog.at_level("WARNING"):
        result = agent.generate(SOURCE, "mcq", "beginner", 1)

    assert result.requires_human_review is True
    assert "requires_human_review" not in caplog.text


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_switching_off_review_is_warned_about(agent_class, schema, caplog) -> None:
    """…and must be loud when something is."""
    agent = agent_with(agent_class, reply([question()], review=False))

    with caplog.at_level("WARNING"):
        agent.generate(SOURCE, "mcq", "beginner", 1)

    assert "requires_human_review" in caplog.text
    assert "prompt injection" in caplog.text


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_a_true_false_question_with_options_is_accepted(agent_class, schema) -> None:
    """The positive half of the true/false rule.

    Only the rejection case was covered at first, so "true_false needs options"
    was satisfied by an agent that refused every true/false question. The
    prompts now instruct the model to send ["True", "False"] for this type,
    which is what makes the rule fair rather than stricter than the ask.
    """
    agent = agent_with(
        agent_class,
        reply(
            [
                question(
                    type="true_false",
                    options=["True", "False"],
                    correct_answer="True",
                    question="A while loop repeats while its condition is true.",
                )
            ]
        ),
    )

    result = agent.generate(SOURCE, "true_false", "beginner", 1)

    assert result.questions[0].type.value == "true_false"
    assert result.questions[0].options == ["True", "False"]


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_every_question_type_reaches_the_model(agent_class, schema) -> None:
    """Control for BUG-02: the whole allowed set must get through, not just mcq."""
    for question_type, options, answer in (
        ("mcq", ["for", "while"], "while"),
        ("true_false", ["True", "False"], "True"),
        ("short_answer", None, "a while loop"),
    ):
        client = FakeLLMClient(
            reply(
                [question(type=question_type, options=options, correct_answer=answer)]
            )
        )
        result = agent_class(client=client, model="test-model").generate(
            SOURCE, question_type, "beginner", 1
        )
        assert result.questions[0].type.value == question_type
        assert question_type in client.prompt


# --------------------------------------------------------------------------- #
# The review gate
#
# Mentor and concept got a persisted gate in #39, the three study agents in
# #40. These two never had one, and nobody noticed because nothing called them
# - they had no interface at all until the Question Bank and Test Help pages
# were added. Shipping a page that prints "PENDING HUMAN REVIEW" over an output
# no reviewer can see is the same defect both of those PRs existed to fix.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_the_output_reaches_the_review_queue(agent_class, schema, tmp_path) -> None:
    """The generated questions must be findable by a reviewer, not just flagged."""
    store = PlatformStore(db_path=str(tmp_path / "platform.db"))
    agent = agent_with(agent_class, reply([question()]))

    output = agent.generate_reviewable(
        SOURCE,
        question_type="mcq",
        difficulty="beginner",
        num_questions=1,
        store=store,
    )

    queued = store.list_outputs(status=OutputStatus.PENDING)
    assert [item.id for item in queued] == [output.id], (
        "the output never reached the queue"
    )
    assert output.output_type == agent_class.output_type


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_the_run_is_recorded_with_what_the_model_saw(
    agent_class, schema, tmp_path
) -> None:
    """A review record that misstates its input is worse than none."""
    store = PlatformStore(db_path=str(tmp_path / "platform.db"))
    agent = agent_with(agent_class, reply([question()]))

    agent.generate_reviewable(
        SOURCE,
        question_type="mcq",
        difficulty="beginner",
        num_questions=1,
        store=store,
    )

    runs = store.list_agent_runs()
    assert len(runs) == 1
    assert runs[0].agent_name == agent_class.agent_name
    assert runs[0].input_context == SOURCE
    assert runs[0].status is RunStatus.SUCCESS


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_a_failed_run_is_recorded_not_lost(agent_class, schema, tmp_path) -> None:
    """Without this, History shows a failed run hanging in SUCCESS forever."""
    store = PlatformStore(db_path=str(tmp_path / "platform.db"))
    agent = agent_with(agent_class, "not json at all")

    with pytest.raises(ValueError):
        agent.generate_reviewable(
            SOURCE,
            question_type="mcq",
            difficulty="beginner",
            num_questions=1,
            store=store,
        )

    runs = store.list_agent_runs()
    assert len(runs) == 1
    assert runs[0].status is RunStatus.FAILURE
    assert runs[0].error
    assert not store.list_outputs(status=OutputStatus.PENDING), (
        "a failed generation should queue nothing for review"
    )


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_the_two_agents_are_recorded_under_different_names(
    agent_class, schema
) -> None:
    """Question Bank and Test Help must be distinguishable in the queue.

    They share one base class and one output shape; if they also shared an
    agent_name a reviewer could not tell which one produced what.
    """
    assert agent_class.agent_name
    assert agent_class.output_type


def test_question_bank_and_test_help_do_not_collide() -> None:
    assert QuestionBankAgent.agent_name != TestHelpAgent.agent_name
    assert QuestionBankAgent.output_type != TestHelpAgent.output_type


# --------------------------------------------------------------------------- #
# Grounding: exact checks block, the fuzzy one informs
#
# Mentor and concept made this split in #39 after measuring it: validate_support
# is a 0.6 token-overlap heuristic that rejected 5 of 20 *correct* live
# generations. These two agents kept raising on it, because nothing called them
# with a context - they had no UI until #41. The moment they got one, they
# inherited the failure that fix existed to prevent.
# --------------------------------------------------------------------------- #


SOURCE_CHUNK_ID = "doc-1-c0000"


def a_context(chunk_id: str = SOURCE_CHUNK_ID) -> GroundedContext:
    chunk = Chunk(chunk_id=chunk_id, document_id="doc-1", ordinal=0, text=SOURCE)
    return GroundedContext(
        query="loops",
        scope=RetrievalScope(document_id="doc-1"),
        chunks=[RetrievedChunk(chunk=chunk, score=1.0, rank=1)],
    )


def grounded_question(**overrides) -> dict:
    """A question citing the chunk the context actually retrieved."""
    return question(references=[{"segment_id": SOURCE_CHUNK_ID, "text": SOURCE}], **overrides)


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_an_unsupported_claim_is_flagged_not_withheld(agent_class, schema) -> None:
    """The measured failure: one correct answer in four withheld from the learner.

    The rationale here cites a real retrieved chunk but says something the
    passage does not support, which is what the overlap heuristic catches - and
    what it catches wrongly a quarter of the time on genuine output.
    """
    agent = agent_with(
        agent_class,
        reply([grounded_question(
            rationale="Quantum entanglement lets the interpreter skip the loop entirely."
        )]),
    )

    result = agent.generate(SOURCE, "mcq", "beginner", 1, context=a_context())

    assert result.questions, "the output was withheld instead of flagged"
    assert agent._grounding_warnings, "an unsupported claim produced no warning"
    assert any(
        "Could not match this statement" in warning
        for warning in agent._grounding_warnings
    )


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_a_supported_answer_is_not_flagged(agent_class, schema) -> None:
    """The other half: a check that flags everything would satisfy the test above."""
    agent = agent_with(agent_class, reply([grounded_question()]))

    agent.generate(SOURCE, "mcq", "beginner", 1, context=a_context())

    assert agent._grounding_warnings == []


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_an_invented_citation_is_still_refused(agent_class, schema) -> None:
    """The exact check keeps blocking. Zero false positives across 20 live runs."""
    agent = agent_with(
        agent_class,
        reply([question(references=[{"segment_id": "doc-1-c9999", "text": "never retrieved"}])]),
    )

    with pytest.raises(ValueError, match="not grounded"):
        agent.generate(SOURCE, "mcq", "beginner", 1, context=a_context())


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_a_question_set_that_cites_nothing_is_refused(agent_class, schema) -> None:
    """verify_references treats an empty list as trivially valid.

    So without an explicit guard, a set where every question cites nothing at
    all passes grounding untouched - while every prompt in src/prompts/ says
    "every question must contain at least one grounding reference".
    """
    agent = agent_with(agent_class, reply([question(references=[])]))

    with pytest.raises(ValueError, match="cite no sources"):
        agent.generate(SOURCE, "mcq", "beginner", 1, context=a_context())


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_the_warnings_reach_the_review_record(agent_class, schema, tmp_path) -> None:
    """A flag nobody sees is the same as no flag.

    The whole point of downgrading the hard reject is that the signal lands in
    front of the reviewer instead of the learner.
    """
    store = PlatformStore(db_path=str(tmp_path / "platform.db"))
    agent = agent_with(
        agent_class,
        reply([grounded_question(
            rationale="Quantum entanglement lets the interpreter skip the loop entirely."
        )]),
    )

    output = agent.generate_reviewable(
        SOURCE,
        question_type="mcq",
        difficulty="beginner",
        num_questions=1,
        context=a_context(),
        store=store,
    )

    warnings = (output.validation_report or {}).get("grounding_warnings", [])
    assert warnings, "the reviewer gets no sign the claim was unmatched"
    assert output.status is OutputStatus.PENDING


# --------------------------------------------------------------------------- #
# Retry belongs to whoever owns the path, and only to one of them
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_a_transient_failure_is_retried_on_the_page_path(agent_class, schema) -> None:
    """The study lane retried from the start; these four never did.

    The orchestrator has retry, but every Streamlit page calls the agent
    directly and never touches the orchestrator - so a free-tier gateway
    returning one error payload failed the page outright, when a second call
    would have served it.
    """
    client = FakeLLMClient(
        Reply(error={"message": "provider saturated"}),
        Reply(reply([question()])),
    )
    agent = agent_class(client=client, model="test-model")

    result = agent.generate(SOURCE, "mcq", "beginner", 1)

    assert len(result.questions) == 1
    assert len(client.calls) == 2, "the transient failure was not retried"


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_the_orchestrator_path_does_not_retry_twice_over(agent_class, schema) -> None:
    """Two retry layers multiply, and that is worse than none.

    ``RegistryAgentAdapter.run_raw`` calls ``_call_llm`` directly and runs its
    own retry with backoff. Retrying inside the client as well turned an
    orchestrator configured for two retries into six calls against a provider
    that had just said it was saturated - the exact harm the narrow
    ``response_format`` fallback exists to avoid.
    """
    client = FakeLLMClient(*[Reply(error={"message": "saturated"})] * 4)
    agent = agent_class(client=client, model="test-model")

    with pytest.raises(UpstreamResponseError):
        agent._call_llm("a prompt")

    assert len(client.calls) == 1, (
        "_call_llm retried on its own; the orchestrator's max_retries would "
        "then be a multiplier rather than a limit"
    )


# --------------------------------------------------------------------------- #
# The output budget has to fund the question the UI can ask for
#
# Five advanced MCQs from a real 861-chunk textbook came back truncated
# mid-JSON. output_budget's per-item allowance is 200, measured on flashcards -
# a front and a back. A question item is a stem, four options, a rationale and
# a references[].text quoting a retrieved passage, so it costs 2-3x that, and
# for any count of 8 or fewer the scaled value fell below the flat floor and
# the sizing never engaged at all.
# --------------------------------------------------------------------------- #


def a_chunk(chars: int) -> str:
    """A passage the size real ingestion produces (this corpus averages 766)."""
    return ("The column space of A is the span of its columns, a subspace of "
            "R^m whose dimension is the rank of A. " * 40)[:chars]


def a_cited_question(quote_chars: int) -> dict:
    """An advanced MCQ citing a realistically-sized excerpt."""
    return question(
        difficulty="advanced",
        rationale="The transformation is onto exactly when Col A spans R^m, so "
                  "failing to be onto means the rank is strictly less than m.",
        references=[{"segment_id": "doc-1-c0123", "text": a_chunk(quote_chars)}],
    )


@pytest.mark.parametrize("agent_class,schema", AGENTS)
@pytest.mark.parametrize("count", [1, 5, 15, 20], ids=["one", "five", "fifteen", "max"])
def test_the_agent_sends_a_budget_sized_to_the_question(
    agent_class, schema, count
) -> None:
    """Assert on what reached the gateway, not on the helper.

    output_budget always took a per_item override; the defect was that this
    call site never passed one. A test of the helper alone would have passed
    throughout the bug.
    """
    client = FakeLLMClient(reply([question()] * count))
    agent = agent_class(client=client, model="test-model")

    try:
        agent.generate(SOURCE, "mcq", "beginner", count)
    except ValueError:
        pass  # the reply's content is not what this test is about

    sent = client.calls[0]["max_tokens"]
    assert sent >= OUTPUT_OVERHEAD_TOKENS + count * QUESTION_ITEM_TOKENS or (
        sent == max_tokens_default()
    ), f"asked for {count} questions with only {sent} output tokens"


def test_the_full_slider_is_not_clipped_by_the_cap() -> None:
    """20 is what the UI offers; MAX_OUTPUT_TOKENS must not trim the request.

    At the old cap of 8000 a 20-question request asked for 8400 and was
    silently trimmed back - reproducing the truncation this fixes, at the top
    of the range, caused by the guard meant to prevent it.
    """
    budget = output_budget(20, per_item=QUESTION_ITEM_TOKENS)

    assert budget == OUTPUT_OVERHEAD_TOKENS + 20 * QUESTION_ITEM_TOKENS
    assert budget <= MAX_OUTPUT_TOKENS


@pytest.mark.parametrize("count", [5, 20], ids=["five", "max"])
def test_a_full_set_of_cited_questions_fits_the_budget(count: int) -> None:
    """The measurement that started this, as a test.

    A realistic advanced MCQ citing a 766-char excerpt - the mean chunk size of
    the document that failed - must fit, at both ends of the slider.
    """
    payload = json.dumps(
        {"questions": [a_cited_question(766)] * count, "requires_human_review": True}
    )
    estimated_tokens = len(payload) / 4  # the usual English approximation

    assert estimated_tokens < output_budget(count, per_item=QUESTION_ITEM_TOKENS), (
        f"{count} cited questions need ~{estimated_tokens:.0f} tokens but the "
        f"agent asks for {output_budget(count, per_item=QUESTION_ITEM_TOKENS)}"
    )


def test_the_flashcard_budget_is_untouched() -> None:
    """The study lane's allowance is right for the items it was measured on."""
    assert output_budget(25) == OUTPUT_OVERHEAD_TOKENS + 25 * 200


# --------------------------------------------------------------------------- #
# A short set is retried once, not discarded
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_a_short_reply_is_retried_and_accepted(agent_class, schema) -> None:
    """Asking for 20 and getting 19 should not throw away the 19."""
    client = FakeLLMClient(
        reply([question()] * 19),   # short
        reply([question()] * 20),   # complies
    )
    agent = agent_class(client=client, model="test-model")

    result = agent.generate(SOURCE, "mcq", "beginner", 20)

    assert len(result.questions) == 20
    assert len(client.calls) == 2


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_a_grounding_failure_is_not_retried(agent_class, schema) -> None:
    """Only the count is retried.

    A model that invents a citation invents it again, so a second call spends
    money to reprint the same error.
    """
    client = FakeLLMClient(
        *[reply([question(references=[
            {"segment_id": "doc-1-c9999", "text": "never retrieved"}
        ])])] * 3
    )
    agent = agent_class(client=client, model="test-model")

    with pytest.raises(ValueError, match="not grounded"):
        agent.generate(SOURCE, "mcq", "beginner", 1, context=a_context())

    assert len(client.calls) == 1, "a grounding failure was retried"


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_a_schema_failure_is_not_retried(agent_class, schema) -> None:
    """Same reasoning: a malformed reply fails the same way twice."""
    client = FakeLLMClient(*['{"questions": [{"question": "no other fields"}]}'] * 3)
    agent = agent_class(client=client, model="test-model")

    with pytest.raises(ValueError, match="schema"):
        agent.generate(SOURCE, "mcq", "beginner", 1)

    assert len(client.calls) == 1, "a schema failure was retried"
