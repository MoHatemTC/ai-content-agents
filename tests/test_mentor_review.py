"""Review-pipeline integration tests for the Mentor Agent."""

from src.agents.mentor_agent import MentorAgent
from src.validation.review_schema import GeneratedOutput, OutputStatus
from src.validation.schemas import MentorOutput
from tests.conftest import CompliantAgentsClient


def test_generate_reviewable_creates_pending_mentor_output():
    """A mentor response is recorded for review instead of being finalized."""
    agent = MentorAgent(client=CompliantAgentsClient())
    content = "Python has two loop types: for and while."

    generated = agent.generate(
        content=content,
        user_question="Explain loops.",
        difficulty="beginner",
    )
    reviewable = agent.generate_reviewable(
        content=content,
        user_question="Explain loops.",
        difficulty="beginner",
    )

    assert isinstance(generated, MentorOutput)
    assert isinstance(reviewable, GeneratedOutput)
    assert reviewable.status is OutputStatus.PENDING
    assert reviewable.validation_passed is True
    assert reviewable.validation_report["passed"] is True
    assert reviewable.payload == generated.model_dump()


def test_generate_reviewable_delegates_to_generate_once(monkeypatch):
    """The review path delegates generation exactly once."""
    agent = MentorAgent(client=CompliantAgentsClient())
    generated = MentorOutput.model_validate(
        {
            "explanation": "A loop repeats instructions.",
            "key_points": ["Loops repeat instructions."],
            "next_steps": ["Practice loops."],
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
