"""Tests for the Mentor and Concept application review boundary."""

from unittest.mock import Mock

import pytest

from src.services.mentor_concept import MentorConceptService
from src.validation.review_schema import GeneratedOutput, OutputStatus


def _reviewable(output_type: str) -> GeneratedOutput:
    return GeneratedOutput(
        agent_run_id="run-1",
        output_type=output_type,
        payload={"content": "generated"},
        schema_name="Output",
    )


@pytest.mark.parametrize(
    ("method_name", "agent_attribute", "output_type"),
    [
        ("generate_mentor_reviewable", "mentor_agent", "mentor_explanation"),
        ("generate_concept_reviewable", "concept_agent", "concept_explanation"),
    ],
)
def test_service_delegates_to_reviewable_generation(
    method_name: str,
    agent_attribute: str,
    output_type: str,
) -> None:
    """Application generation uses the reviewable agent method exactly once."""
    service = MentorConceptService(mock_mode=True)
    agent = getattr(service, agent_attribute)
    reviewable = _reviewable(output_type)
    agent.generate_reviewable = Mock(return_value=reviewable)
    agent.generate = Mock(side_effect=AssertionError("generate() bypassed review"))

    result = getattr(service, method_name)(
        content="Python loops repeat instructions.",
        user_question="Explain loops.",
        difficulty="beginner",
    )

    assert result is reviewable
    assert isinstance(result, GeneratedOutput)
    assert result.status is OutputStatus.PENDING
    agent.generate_reviewable.assert_called_once()
    agent.generate.assert_not_called()
