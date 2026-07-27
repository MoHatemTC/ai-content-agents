"""Focused tests for Week 3 grounding, difficulty, metadata, and API errors."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from src.agents.concept_agent import ConceptAgent
from src.agents.mentor_agent import MentorAgent
from src.retrieval.models import Chunk, GroundedContext, RetrievedChunk, RetrievalScope
from src.validation.schemas import ConceptOutput, ContentReference, MentorOutput
from src.validation.support_validator import extract_claim_text, validate_support


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


def test_support_validation_flags_unsupported_key_point_and_next_step() -> None:
    output = MentorOutput(
        explanation="Python has for loops.",
        key_points=["Python has for loops."],
        next_steps=["Python automatically parallelizes loops."],
        references=[ContentReference(segment_id="chunk-1", text="loops")],
    )

    result = validate_support(extract_claim_text(output), _context("Python has for loops."))

    assert result.supported is False
    assert result.unsupported_claims == [
        "Python automatically parallelizes loops."
    ]


def test_support_validation_flags_unsupported_concept_definition() -> None:
    output = ConceptOutput(
        definition="Loops are compiled into machine code automatically.",
        explanation="Python has for loops.",
        key_points=["for loops"],
        references=[ContentReference(segment_id="chunk-1", text="loops")],
    )

    result = validate_support(extract_claim_text(output), _context("Python has for loops."))

    assert result.supported is False
    assert result.unsupported_claims == [
        "Loops are compiled into machine code automatically."
    ]


def test_support_validation_returns_each_unsupported_claim() -> None:
    output = MentorOutput(
        explanation="Python has for loops. Python has no while loops.",
        key_points=["for loops"],
        next_steps=["Practice quantum loops."],
        references=[ContentReference(segment_id="chunk-1", text="loops")],
    )

    result = validate_support(extract_claim_text(output), _context("Python has for loops."))

    assert result.supported is False
    assert result.unsupported_claims == [
        "Python has no while loops.",
        "Practice quantum loops.",
    ]


def test_support_validation_accepts_fully_supported_output() -> None:
    output = ConceptOutput(
        definition="Python has for loops.",
        explanation="Python has for loops.",
        key_points=["for loops"],
        references=[ContentReference(segment_id="chunk-1", text="loops")],
    )

    result = validate_support(extract_claim_text(output), _context("Python has for loops."))

    assert result.supported is True
    assert result.unsupported_claims == []


@pytest.mark.parametrize("agent_class", [MentorAgent, ConceptAgent])
def test_agents_accept_supported_difficulty(agent_class: type) -> None:
    result = agent_class(mock_mode=True).generate(
        content="Python has for loops.",
        user_question="Explain loops.",
        difficulty="advanced",
    )

    assert result.requires_human_review is True


@pytest.mark.parametrize("agent_class", [MentorAgent, ConceptAgent])
def test_agents_reject_invalid_difficulty(agent_class: type) -> None:
    with pytest.raises(ValueError, match="Invalid difficulty"):
        agent_class(mock_mode=True).generate(
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
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=None))]),
            "empty response",
        ),
    ],
)
def test_agents_report_clear_empty_api_responses(
    agent_class: type,
    response: object,
    message: str,
) -> None:
    agent = agent_class(mock_mode=True)
    agent.client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **_: response,
            )
        )
    )
    agent.mock_mode = False

    with pytest.raises(RuntimeError, match=message):
        agent._call_llm("prompt")
