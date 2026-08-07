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

from src.agents.question_bank_agent import QuestionBankAgent
from src.agents.test_help_agent import TestHelpAgent
from src.validation.schemas import QuestionBankOutput, TestHelpOutput
from src.llm_gateway import UpstreamResponseError
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
    agent = agent_with(agent_class, reply([question()] * 3))

    with pytest.raises(ValueError, match="exactly 1"):
        agent.generate(SOURCE, "mcq", "beginner", 1)


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
    agent = agent_class(
        client=FakeLLMClient(Reply(error={"message": "provider saturated"})),
        model="test-model",
    )

    with pytest.raises(UpstreamResponseError, match="no choices"):
        agent.generate(SOURCE, "mcq", "beginner", 1)


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
