"""Offline tests for deterministic Mentor and Concept output evaluation."""

from src.evaluation import evaluate_output
from src.retrieval.models import Chunk, GroundedContext, RetrievalScope, RetrievedChunk
from src.validation.schemas import ConceptOutput, ContentReference, MentorOutput


def _context() -> GroundedContext:
    """Build a source context supporting the test explanations."""
    return GroundedContext(
        query="What is a loop?",
        scope=RetrievalScope(document_id="document-1"),
        chunks=[
            RetrievedChunk(
                chunk=Chunk(
                    chunk_id="chunk-1",
                    document_id="document-1",
                    ordinal=0,
                    text=(
                        "A loop repeats instructions. Loops repeat instructions. "
                        "Practice loops."
                    ),
                ),
                score=1.0,
                rank=1,
            )
        ],
    )


def test_evaluate_output_reports_fully_grounded_mentor_output():
    """A valid citation and supported explanation produce a full score."""
    output = MentorOutput(
        explanation="A loop repeats instructions.",
        key_points=["Loops repeat instructions."],
        next_steps=["Practice loops."],
        references=[ContentReference(segment_id="chunk-1", text="Loops.")],
    )

    result = evaluate_output(output, _context())

    assert result.grounded is True
    assert result.references_valid is True
    assert result.supported is True
    assert result.validation_passed is True
    assert result.unsupported_claims == 0
    assert result.groundedness_score == 1.0
    assert result.quality_score == 1.0
    assert result.notes == []


def test_evaluate_output_marks_groundedness_as_not_evaluated_without_context():
    """A missing source context is distinct from a zero grounding score."""
    output = ConceptOutput(
        definition="A loop repeats instructions.",
        explanation="A loop repeats instructions.",
        key_points=["Loops repeat instructions."],
        references=[ContentReference(segment_id="chunk-1", text="Loops.")],
    )

    result = evaluate_output(output)

    assert result.groundedness_score is None
    assert "No grounded context was supplied for evaluation." in result.notes


def test_evaluate_output_flags_invalid_reference_ids():
    """Unknown citation ids make an otherwise supported output ungrounded."""
    output = ConceptOutput(
        definition="A loop repeats instructions.",
        explanation="A loop repeats instructions.",
        key_points=["Loops repeat instructions."],
        references=[ContentReference(segment_id="unknown", text="Loops.")],
    )

    result = evaluate_output(output, _context())

    assert result.grounded is False
    assert result.references_valid is False
    assert result.supported is True
    assert result.validation_passed is True
    assert result.groundedness_score == 0.5
    assert "Unknown reference ids: unknown" in result.notes


def test_evaluate_output_flags_unsupported_explanations():
    """An explanation absent from the source context loses support credit."""
    output = ConceptOutput(
        definition="A loop repeats instructions.",
        explanation="A loop compiles Python code.",
        key_points=["Loops repeat instructions."],
        references=[ContentReference(segment_id="chunk-1", text="Loops.")],
    )

    result = evaluate_output(output, _context())

    assert result.grounded is False
    assert result.references_valid is True
    assert result.supported is False
    assert result.validation_passed is True
    assert result.unsupported_claims == 1
    assert result.groundedness_ratio == 2 / 3
    assert result.groundedness_score == 0.5
    assert "Unsupported claims detected: 1." in result.notes


def test_evaluate_output_reports_validation_failure():
    """Existing guardrail failures prevent a groundedness score."""
    output = MentorOutput(
        explanation="A loop repeats instructions.",
        key_points=["Loops repeat instructions."],
        next_steps=["Practice loops."],
        references=[],
    )

    result = evaluate_output(output, _context())

    assert result.grounded is False
    assert result.references_valid is True
    assert result.supported is True
    assert result.validation_passed is False
    assert result.groundedness_score == 0.0
    assert any("no source references" in note.lower() for note in result.notes)


def test_evaluate_output_scores_difficulty_alignment() -> None:
    """Short claims align with beginner difficulty under the deterministic heuristic."""
    output = ConceptOutput(
        definition="A loop repeats instructions.",
        explanation="A loop repeats instructions.",
        key_points=["Loops repeat instructions."],
        references=[ContentReference(segment_id="chunk-1", text="Loops.")],
    )

    beginner = evaluate_output(output, _context(), difficulty="beginner")
    advanced = evaluate_output(output, _context(), difficulty="advanced")

    assert beginner.difficulty_alignment_score == 1.0
    assert advanced.difficulty_alignment_score < beginner.difficulty_alignment_score
