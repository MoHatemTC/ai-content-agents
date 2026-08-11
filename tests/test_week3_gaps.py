"""Focused tests for Week 3 grounding, difficulty, metadata, and API errors."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from src.agents.concept_agent import ConceptAgent
from src.agents.mentor_agent import MentorAgent
from src.retrieval.models import Chunk, GroundedContext, RetrievalScope, RetrievedChunk
from src.validation.schemas import ConceptOutput, ContentReference, MentorOutput
from src.validation.support_validator import extract_claim_text, validate_support
from tests.conftest import CompliantAgentsClient


def _context(text: str) -> GroundedContext:
    return GroundedContext(
        query="loops",
        scope=RetrievalScope(document_id="doc-1"),
        chunks=[
            RetrievedChunk(
                chunk=Chunk(
                    chunk_id="chunk-1",
                    document_id="doc-1",
                    ordinal=0,
                    text=text,
                ),
                score=1.0,
                rank=1,
            )
        ],
    )


def test_support_validation_flags_an_unsupported_key_point() -> None:
    """The fabricated claim sits in key_points, not next_steps.

    next_steps is no longer a claim field: advice about what to study next is
    by construction absent from the source, so checking it rejected every
    correct mentor answer (5 of 5 measured). The cost is real and accepted -
    a fabricated fact smuggled into next_steps is no longer caught - so this
    test now pins the check where it genuinely works.
    """
    output = MentorOutput(
        explanation="Python has for loops.",
        key_points=["Python automatically parallelizes loops."],
        next_steps=["Re-read the loop section."],
        references=[ContentReference(segment_id="chunk-1", text="loops")],
    )

    result = validate_support(
        extract_claim_text(output), _context("Python has for loops.")
    )

    assert result.supported is False
    assert result.unsupported_claims == ["Python automatically parallelizes loops."]


def test_support_validation_flags_unsupported_concept_definition() -> None:
    output = ConceptOutput(
        definition="Loops are compiled into machine code automatically.",
        explanation="Python has for loops.",
        key_points=["for loops"],
        references=[ContentReference(segment_id="chunk-1", text="loops")],
    )

    result = validate_support(
        extract_claim_text(output), _context("Python has for loops.")
    )

    assert result.supported is False
    assert result.unsupported_claims == [
        "Loops are compiled into machine code automatically."
    ]


def test_support_validation_returns_each_unsupported_claim() -> None:
    output = MentorOutput(
        explanation="Python has for loops. Python has no while loops.",
        key_points=["Quantum loops run on a QPU."],
        next_steps=["Re-read the loop section."],
        references=[ContentReference(segment_id="chunk-1", text="loops")],
    )

    result = validate_support(
        extract_claim_text(output), _context("Python has for loops.")
    )

    assert result.supported is False
    assert result.unsupported_claims == [
        "Python has no while loops.",
        "Quantum loops run on a QPU.",
    ]


def test_support_validation_accepts_fully_supported_output() -> None:
    output = ConceptOutput(
        definition="Python has for loops.",
        explanation="Python has for loops.",
        key_points=["for loops"],
        references=[ContentReference(segment_id="chunk-1", text="loops")],
    )

    result = validate_support(
        extract_claim_text(output), _context("Python has for loops.")
    )

    assert result.supported is True
    assert result.unsupported_claims == []


def test_support_validation_accepts_paraphrased_supported_claim() -> None:
    """Meaning-preserving wording with sufficient token overlap remains supported."""
    result = validate_support(
        ["A loop repeats commands."],
        _context("A loop repeats instructions."),
    )

    assert result.supported is True
    assert result.unsupported_claims == []


@pytest.mark.parametrize("agent_class", [MentorAgent, ConceptAgent])
def test_agents_accept_supported_difficulty(agent_class: type) -> None:
    result = agent_class(client=CompliantAgentsClient()).generate(
        content="Python has for loops.",
        user_question="Explain loops.",
        difficulty="advanced",
    )

    assert result.requires_human_review is True


@pytest.mark.parametrize("agent_class", [MentorAgent, ConceptAgent])
def test_agents_reject_invalid_difficulty(agent_class: type) -> None:
    with pytest.raises(ValueError, match="Invalid difficulty"):
        agent_class(client=CompliantAgentsClient()).generate(
            content="Python has for loops.",
            user_question="Explain loops.",
            difficulty="expert",
        )


@pytest.mark.parametrize("output_class", [MentorOutput, ConceptOutput])
def test_explanation_outputs_always_require_human_review(output_class: type) -> None:
    """Mentor and Concept outputs cannot disable the review requirement."""
    fields = {
        MentorOutput: {
            "explanation": "Python has for loops.",
            "key_points": ["for loops"],
            "next_steps": ["Practice loops."],
            "references": [{"segment_id": "chunk-1", "text": "loops"}],
        },
        ConceptOutput: {
            "definition": "Python has for loops.",
            "explanation": "Python has for loops.",
            "key_points": ["for loops"],
            "references": [{"segment_id": "chunk-1", "text": "loops"}],
        },
    }[output_class]

    output = output_class.model_validate(fields)
    assert output.requires_human_review is True

    with pytest.raises(ValidationError):
        output_class.model_validate({**fields, "requires_human_review": False})

    with pytest.raises(ValidationError):
        output.requires_human_review = False


@pytest.mark.parametrize("agent_class", [MentorAgent, ConceptAgent])
@pytest.mark.parametrize(
    ("response", "message"),
    [
        (None, "LLM returned no response"),
        (SimpleNamespace(choices=[]), "LLM returned no choices"),
        (SimpleNamespace(choices=[SimpleNamespace(message=None)]), "empty message"),
        (
            SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=None))]
            ),
            "empty response",
        ),
    ],
)
def test_agents_report_clear_empty_api_responses(
    agent_class: type,
    response: object,
    message: str,
) -> None:
    agent = agent_class(
        client=SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=lambda **_: response)
            )
        )
    )

    with pytest.raises(RuntimeError, match=message):
        agent._call_llm("prompt")


# --------------------------------------------------------------------------- #
# BUG-12: support validation reaches question outputs, and only just far enough
#
# The narrowness is the whole design. Claiming too much is not a smaller bug
# than claiming nothing: question stems trip the negation heuristic, and
# distractors are deliberately false, so an over-broad extractor would report
# every well-formed question bank as unsupported.
# --------------------------------------------------------------------------- #


def _question_output(**overrides):
    from src.validation.schemas import QuestionBankOutput

    item = {
        "question": "Which of the following is NOT a Python loop type?",
        "options": ["for", "while", "DISTRACTOR: a goto loop", "repeat"],
        "correct_answer": "for",
        "rationale": "A while loop repeats while its condition is true.",
        "difficulty": "beginner",
        "type": "mcq",
        "references": [
            {"segment_id": "chunk_001", "text": "REFERENCE TEXT, NOT A CLAIM"}
        ],
    }
    item.update(overrides)
    return QuestionBankOutput.model_validate(
        {"questions": [item], "requires_human_review": True}
    )


def test_a_question_rationale_is_now_a_claim() -> None:
    """Before BUG-12 was fixed this returned [], so validate_support passed
    anything at all - a check that cannot fail, which reads as coverage."""
    claims = extract_claim_text(_question_output())

    assert claims == ["A while loop repeats while its condition is true."]


def test_the_question_stem_is_not_a_claim() -> None:
    """Stems read "Which of the following is NOT ..." routinely.

    ``_contains_negation`` fires on that, and a stem shares few tokens with the
    source, so treating it as a claim reports a correct question as both
    contradictory and unsupported - two false positives from one field.
    """
    claims = extract_claim_text(_question_output())

    assert not any("Which of the following" in claim for claim in claims)


def test_distractors_are_not_claims() -> None:
    """Distractors are deliberately false. Checking them for support against
    the source would fail every well-formed question bank."""
    claims = extract_claim_text(_question_output())

    assert not any("DISTRACTOR" in claim for claim in claims)


def test_reference_text_is_not_a_claim() -> None:
    """Provenance is verify_references' job, as extract_claim_text's own
    docstring has always said."""
    claims = extract_claim_text(_question_output())

    assert not any("REFERENCE TEXT" in claim for claim in claims)


@pytest.mark.parametrize("agent_class", [MentorAgent, ConceptAgent])
def test_extending_the_extractor_did_not_disturb_mentor_or_concept(
    agent_class: type,
) -> None:
    """The containers walk is keyed to `questions`, which neither schema has.

    Their groundedness ratios are pinned elsewhere (tests/test_evaluation.py),
    so a generic "collect every string leaf" rewrite would have shifted numbers
    other tests depend on.
    """
    from src.validation.schemas import ConceptOutput, MentorOutput

    if agent_class is MentorAgent:
        output = MentorOutput.model_validate(
            {
                "explanation": "Loops repeat instructions.",
                "key_points": ["for loops"],
                "next_steps": ["Practice."],
                "references": [
                    {"segment_id": "c1", "text": "REFERENCE TEXT, NOT A CLAIM"}
                ],
            }
        )
    else:
        output = ConceptOutput.model_validate(
            {
                "definition": "A loop repeats instructions.",
                "explanation": "Loops repeat instructions.",
                "key_points": ["for loops"],
                "references": [
                    {"segment_id": "c1", "text": "REFERENCE TEXT, NOT A CLAIM"}
                ],
            }
        )

    claims = extract_claim_text(output)

    assert claims, "mentor/concept claims disappeared"
    assert not any("REFERENCE TEXT" in claim for claim in claims)
