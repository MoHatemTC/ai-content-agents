"""Batch-generation tests for Mentor and Concept Agents."""

import pytest

from src.agents.concept_agent import ConceptAgent
from src.agents.mentor_agent import MentorAgent
from src.validation.schemas import ConceptOutput, ContentReference, MentorOutput
from tests.conftest import CompliantAgentsClient


def _mentor_output(content: str) -> MentorOutput:
    """Build a distinct valid Mentor output for a test input."""
    return MentorOutput(
        explanation=content,
        key_points=[content],
        next_steps=["Practice."],
        references=[ContentReference(segment_id="chunk-1", text=content)],
    )


def _concept_output(content: str) -> ConceptOutput:
    """Build a distinct valid Concept output for a test input."""
    return ConceptOutput(
        definition=content,
        explanation=content,
        key_points=[content],
        references=[ContentReference(segment_id="chunk-1", text=content)],
    )


@pytest.mark.parametrize(
    ("agent_class", "output_factory"),
    [
        (MentorAgent, _mentor_output),
        (ConceptAgent, _concept_output),
    ],
)
def test_generate_batch_all_succeed_and_preserve_order(
    monkeypatch,
    agent_class,
    output_factory,
):
    """Every input is generated once and successes retain input order."""
    agent = agent_class(client=CompliantAgentsClient())
    items = [{"content": "first"}, {"content": "second"}, {"content": "third"}]
    calls: list[dict[str, str]] = []

    def generate(**item):
        calls.append(item)
        return output_factory(item["content"])

    monkeypatch.setattr(agent, "generate", generate)

    result = agent.generate_batch(items)

    assert calls == items
    assert [output.explanation for output in result.successful_outputs] == [
        "first",
        "second",
        "third",
    ]
    assert result.failed_items == []
    assert result.total_processed == 3
    assert result.total_succeeded == 3
    assert result.total_failed == 0
    assert result.elapsed_seconds >= 0.0


@pytest.mark.parametrize(
    ("agent_class", "output_factory"),
    [
        (MentorAgent, _mentor_output),
        (ConceptAgent, _concept_output),
    ],
)
def test_generate_batch_continues_after_partial_failure(
    monkeypatch,
    agent_class,
    output_factory,
):
    """A failed item is recorded while later inputs still run."""
    agent = agent_class(client=CompliantAgentsClient())
    items = [{"content": "first"}, {"content": "bad"}, {"content": "third"}]
    calls: list[dict[str, str]] = []

    def generate(**item):
        calls.append(item)
        if item["content"] == "bad":
            raise ValueError("generation failed")
        return output_factory(item["content"])

    monkeypatch.setattr(agent, "generate", generate)

    result = agent.generate_batch(items)

    assert calls == items
    assert [output.explanation for output in result.successful_outputs] == [
        "first",
        "third",
    ]
    assert result.failed_items[0].index == 1
    assert result.failed_items[0].input_item == {"content": "bad"}
    # The type prefix is deliberate: a batch records only this string, so a
    # bare "generation failed" left a failed item undiagnosable.
    assert result.failed_items[0].error == "ValueError: generation failed"
    assert result.total_processed == 3
    assert result.total_succeeded == 2
    assert result.total_failed == 1


@pytest.mark.parametrize("agent_class", [MentorAgent, ConceptAgent])
def test_generate_batch_handles_empty_input(agent_class):
    """An empty batch returns an empty result without calling generation."""
    agent = agent_class(client=CompliantAgentsClient())
    result = agent.generate_batch([])

    assert result.successful_outputs == []
    assert result.failed_items == []
    assert result.total_processed == 0
    assert result.total_succeeded == 0
    assert result.total_failed == 0
    assert result.elapsed_seconds >= 0.0
