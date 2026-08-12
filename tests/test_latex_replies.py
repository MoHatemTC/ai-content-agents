r"""The agents must survive the LaTeX their own prompts ask the model for.

``concept.yaml`` and ``mentor.yaml`` instruct the model to write mathematics as
LaTeX, and the interface now renders it. The model duly writes
``$x_1, \dots, x_n$`` inside a JSON string, where ``\d`` is not a valid escape -
so for a while every Mentor reply against the Linear Algebra textbook failed
with "The LLM returned invalid JSON", 3 times in 6 identical requests.

None of the 1040 tests passing at the time could have caught it:
``CompliantAgentsClient`` builds its replies with ``json.dumps``, so its
backslashes are always escaped correctly. The double was better behaved than
the thing it stood in for. :class:`LatexAgentsClient` is not, and these tests
are the ones that would have failed.
"""

from __future__ import annotations

import json

import pytest

from src.agents.concept_agent import ConceptAgent
from src.agents.mentor_agent import MentorAgent
from src.agents.question_bank_agent import QuestionBankAgent
from src.retrieval.models import (
    Chunk,
    GroundedContext,
    RetrievalScope,
    RetrievedChunk,
)
from src.testing.compliant import LatexAgentsClient, unescape_backslashes


@pytest.fixture
def context() -> GroundedContext:
    return GroundedContext(
        query="What is a vector space?",
        scope=RetrievalScope(document_id="document-1"),
        chunks=[
            RetrievedChunk(
                chunk=Chunk(
                    chunk_id="document-1-c0027",
                    document_id="document-1",
                    ordinal=27,
                    text=(
                        "A system of linear equations is a collection of one or "
                        "more linear equations involving the same variables."
                    ),
                ),
                score=1.0,
                rank=1,
            )
        ],
    )


def test_the_double_really_does_emit_invalid_json() -> None:
    """Guard the guard.

    If this ever starts producing valid JSON, the tests below stop testing
    anything and would pass for the wrong reason.
    """
    body = unescape_backslashes(json.dumps({"t": r"$\dots$"}))

    assert r"\dots" in body
    with pytest.raises(json.JSONDecodeError):
        json.loads(body)


def test_mentor_survives_latex(context: GroundedContext) -> None:
    agent = MentorAgent(client=LatexAgentsClient(), model="test-model")

    result = agent.generate(
        content=context,
        user_question="explain chapter 1",
        difficulty="intermediate",
        context=context,
    )

    # The notation reaches the reader intact - repairing the escape must not
    # cost the backslash the maths is made of.
    assert r"\dots" in result.explanation
    assert r"\mathbb{R}^n" in result.explanation
    assert r"\underline{x}" in result.explanation


@pytest.mark.parametrize(
    ("command", "eaten_as"),
    [(r"\times", "\t"), (r"\beta", "\b"), (r"\frac", "\f"), (r"\neq", "\n"),
     (r"\rho", "\r")],
)
def test_commands_that_decode_to_control_characters_survive(
    context: GroundedContext, command: str, eaten_as: str
) -> None:
    r"""The silent failure: ``\t`` and ``\b`` are *valid* JSON escapes.

    ``\dots`` raises and gets noticed. ``\times`` decodes to TAB + "imes" and
    sails through parsing, schema validation, grounding and persistence to
    reach the learner as "8imes300".
    """
    agent = MentorAgent(client=LatexAgentsClient(), model="test-model")

    result = agent.generate(
        content=context,
        user_question="explain chapter 1",
        difficulty="intermediate",
        context=context,
    )

    assert command in result.explanation
    assert eaten_as not in result.explanation


def test_concept_survives_latex(context: GroundedContext) -> None:
    agent = ConceptAgent(client=LatexAgentsClient(), model="test-model")

    result = agent.generate(
        content=context,
        user_question="explain chapter 1",
        difficulty="intermediate",
        context=context,
    )

    assert r"\dots" in result.explanation
    assert result.references[0].segment_id == "document-1-c0027"


def test_question_bank_survives_latex(context: GroundedContext) -> None:
    """The question lane shares the parse point, so it shares the failure."""
    agent = QuestionBankAgent(client=LatexAgentsClient(), model="test-model")

    result = agent.generate(
        content=context,
        question_type="mcq",
        difficulty="intermediate",
        num_questions=1,
        context=context,
    )

    assert r"\dots" in result.questions[0].rationale


def test_latex_replies_are_still_grounded(context: GroundedContext) -> None:
    """Repair must not smuggle a broken citation past verification.

    The escape repair rewrites the reply body, so it is worth pinning that the
    segment ids inside it come through byte for byte - a mangled id would be
    refused, and a silently mangled one would be worse.
    """
    agent = MentorAgent(client=LatexAgentsClient(), model="test-model")

    result = agent.generate(
        content=context,
        user_question="explain chapter 1",
        difficulty="intermediate",
        context=context,
    )

    assert [r.segment_id for r in result.references] == ["document-1-c0027"]
