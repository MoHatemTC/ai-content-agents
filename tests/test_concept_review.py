"""Review-pipeline integration tests for the Concept Agent."""

from src.agents.concept_agent import ConceptAgent
from src.validation.review_schema import GeneratedOutput, OutputStatus
from src.validation.schemas import ConceptOutput
from tests.conftest import CompliantAgentsClient


def test_generate_reviewable_creates_pending_concept_output():
    """A concept explanation is recorded for review instead of finalized."""
    agent = ConceptAgent(client=CompliantAgentsClient())
    content = "Python provides two main loop types: for and while."

    generated = agent.generate(
        content=content,
        user_question="What is a loop?",
        difficulty="beginner",
    )
    reviewable = agent.generate_reviewable(
        content=content,
        user_question="What is a loop?",
        difficulty="beginner",
    )

    assert isinstance(generated, ConceptOutput)
    assert isinstance(reviewable, GeneratedOutput)
    assert reviewable.status is OutputStatus.PENDING
    assert reviewable.validation_passed is True
    assert reviewable.validation_report["passed"] is True
    assert reviewable.payload == generated.model_dump()


def test_generate_reviewable_delegates_to_generate_once(monkeypatch):
    """The review path delegates generation exactly once."""
    agent = ConceptAgent(client=CompliantAgentsClient())
    generated = ConceptOutput.model_validate(
        {
            "definition": "A loop repeats instructions.",
            "explanation": "A loop repeats instructions.",
            "key_points": ["Loops repeat instructions."],
            "references": [{"segment_id": "chunk-1", "text": "Loops."}],
        }
    )
    calls: list[dict[str, object]] = []

    def generate(**kwargs):
        calls.append(kwargs)
        return generated

    monkeypatch.setattr(agent, "generate", generate)

    reviewable = agent.generate_reviewable(
        content="Loops repeat instructions.",
        user_question="What is a loop?",
        difficulty="beginner",
    )

    assert calls == [
        {
            "content": "Loops repeat instructions.",
            "user_question": "What is a loop?",
            "difficulty": "beginner",
            "context": None,
        }
    ]
    assert reviewable.payload == generated.model_dump()
