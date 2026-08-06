"""Sprint-4 QA: contract checks for the Question Bank and Test Help agents.

Every test here asserts the behaviour the Sprint-4 brief requires - questions
grounded in the source, question type and count honoured *exactly*, valid
correct answers and distractors, outputs held behind the human-review gate.

**Most of them are ``xfail(strict=True)``, because the agents do not do those
things.** `generate()` is a `str.format` into a prompt, a `json.loads`, and a
`model_validate`; there is no input validation, no count enforcement, no
cross-field checking of answers against options, and no grounding step. The
mentor and concept agents run four extra checks these two skip entirely.

Writing the tests this way round is deliberate. Asserting today's broken
behaviour would encode the bugs as the contract and quietly bless them. These
assert the *correct* behaviour, fail as expected, and carry the BUG id in the
reason, so the suite is the bug list in executable form.

``strict=True`` matters: when someone fixes a bug the test XPASSes, which
pytest reports as a failure, forcing them to delete the marker. The bug list
cannot silently rot.

No test here touches the network. All of them drive `FakeLLMClient` from
`tests/conftest.py`.
"""

from __future__ import annotations

import json

import pytest

from src.agents.question_bank_agent import QuestionBankAgent
from src.agents.test_help_agent import TestHelpAgent
from src.validation.schemas import QuestionBankOutput, TestHelpOutput
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


@pytest.mark.xfail(
    strict=True,
    reason="BUG-01: num_questions is a prompt suggestion, not a contract. The "
    "agent returns whatever the model sent - asking for 1 and receiving 3 is "
    "accepted silently.",
)
@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_the_requested_question_count_is_enforced(agent_class, schema) -> None:
    """Asking for one question and getting three is a defect, not a preference.

    The brief requires the count control to be honoured *exactly*. A model that
    over- or under-delivers is normal; silently passing that through to the
    learner is not.
    """
    agent = agent_with(agent_class, reply([question()] * 3))

    with pytest.raises(ValueError, match="1"):
        agent.generate(SOURCE, "mcq", "beginner", 1)


@pytest.mark.xfail(
    strict=True,
    reason="BUG-02: the reply's question type is never compared with the "
    "requested one, so asking for mcq and receiving short_answer is accepted.",
)
@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_the_requested_question_type_is_enforced(agent_class, schema) -> None:
    agent = agent_with(
        agent_class, reply([question(type="short_answer", options=None)])
    )

    with pytest.raises(ValueError, match="mcq"):
        agent.generate(SOURCE, "mcq", "beginner", 1)


@pytest.mark.xfail(
    strict=True,
    reason="BUG-03: the reply's difficulty is never compared with the "
    "requested one.",
)
@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_the_requested_difficulty_is_enforced(agent_class, schema) -> None:
    agent = agent_with(agent_class, reply([question(difficulty="advanced")]))

    with pytest.raises(ValueError, match="beginner"):
        agent.generate(SOURCE, "mcq", "beginner", 1)


# --------------------------------------------------------------------------- #
# Answer keys and distractors must be usable
# --------------------------------------------------------------------------- #


@pytest.mark.xfail(
    strict=True,
    reason="BUG-04: correct_answer is never checked against options, so an "
    "MCQ can ship with an answer key that is not one of the choices.",
)
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


@pytest.mark.xfail(
    strict=True,
    reason="BUG-05: options is Optional with no conditional on type, so an "
    "mcq with options=None validates cleanly.",
)
@pytest.mark.parametrize("agent_class,schema", AGENTS)
@pytest.mark.parametrize("empty", [None, []], ids=["none", "empty-list"])
def test_a_multiple_choice_question_has_options(agent_class, schema, empty) -> None:
    agent = agent_with(agent_class, reply([question(options=empty)]))

    with pytest.raises(ValueError, match="options"):
        agent.generate(SOURCE, "mcq", "beginner", 1)


@pytest.mark.xfail(
    strict=True,
    reason="BUG-06: questions=[] satisfies the schema, so a request for "
    "questions can succeed while producing none.",
)
@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_an_empty_question_set_is_rejected(agent_class, schema) -> None:
    agent = agent_with(agent_class, reply([]))

    with pytest.raises(ValueError):
        agent.generate(SOURCE, "mcq", "beginner", 1)


# --------------------------------------------------------------------------- #
# The human-review gate
# --------------------------------------------------------------------------- #


@pytest.mark.xfail(
    strict=True,
    reason="BUG-07: requires_human_review is a plain mutable bool the model "
    "fills in. MentorOutput and ConceptOutput use Literal[True] + frozen=True; "
    "these two do not, so the model can switch the governance flag off.",
)
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


@pytest.mark.xfail(
    strict=True,
    reason="BUG-07: the field is not frozen, so it can be flipped after "
    "construction by any caller.",
)
@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_the_review_flag_cannot_be_flipped_after_the_fact(agent_class, schema) -> None:
    agent = agent_with(agent_class, reply([question()]))
    result = agent.generate(SOURCE, "mcq", "beginner", 1)

    with pytest.raises(Exception):
        result.requires_human_review = False


# --------------------------------------------------------------------------- #
# Input validation
# --------------------------------------------------------------------------- #


@pytest.mark.xfail(
    strict=True,
    reason="BUG-02/03: question_type and difficulty are never validated on the "
    "way in. validate_difficulty() exists at schemas.py:35 and is simply never "
    "called by these two agents, though mentor calls it.",
)
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

    with pytest.raises(ValueError):
        agent.generate(SOURCE, question_type, difficulty, 1)


@pytest.mark.xfail(
    strict=True,
    reason="BUG-14: num_questions has no lower bound; -5 renders into the "
    "prompt as 'Generate exactly -5 questions.'",
)
@pytest.mark.parametrize("agent_class,schema", AGENTS)
@pytest.mark.parametrize("count", [0, -5], ids=["zero", "negative"])
def test_a_nonsensical_question_count_is_rejected(agent_class, schema, count) -> None:
    agent = agent_with(agent_class, reply([question()]))

    with pytest.raises(ValueError):
        agent.generate(SOURCE, "mcq", "beginner", count)


# --------------------------------------------------------------------------- #
# Gateway and parsing failures
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "agent_class,schema",
    [
        pytest.param(QuestionBankAgent, QuestionBankOutput, id="question_bank"),
        pytest.param(
            TestHelpAgent,
            TestHelpOutput,
            id="test_help",
            marks=pytest.mark.xfail(
                strict=True,
                raises=TypeError,
                reason="BUG-08: test_help_agent.py indexes response.choices[0] "
                "unguarded, so an error-shaped HTTP 200 raises TypeError: "
                "'NoneType' object is not subscriptable. question_bank_agent.py "
                "guards the same case and raises a legible ValueError.",
            ),
        ),
    ],
)
def test_an_error_shaped_success_is_a_legible_error(agent_class, schema) -> None:
    """OpenAI-compatible gateways answer 200 with choices=null when saturated.

    Not hypothetical: it is documented in orchestrator.py as the reason
    UpstreamResponseError exists. The two agents disagree about what to do
    with it, which is the asymmetry this parametrisation exists to surface.
    """
    agent = agent_class(
        client=FakeLLMClient(Reply(error={"message": "provider saturated"})),
        model="test-model",
    )

    with pytest.raises(ValueError):
        agent.generate(SOURCE, "mcq", "beginner", 1)


@pytest.mark.xfail(
    strict=True,
    reason="BUG-10: no fence stripping. Models wrap JSON in ``` despite being "
    "told not to; src/study/llm_client.py:strip_fences already solves this for "
    "the study lane and is not reused here.",
)
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
    client = FakeLLMClient(reply([question()]))
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


@pytest.mark.xfail(
    strict=True,
    reason="BUG-15: no `context` parameter and no GroundedContext branch, so a "
    "GroundedContext is str.format-ed into the prompt as a Pydantic repr. "
    "mentor_agent.py:119 has the branch these two lack.",
)
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
