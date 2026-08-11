"""Tests for the Mentor and Concept application review boundary."""

import ast
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.services.mentor_concept import MentorConceptService
from src.validation.review_schema import GeneratedOutput, OutputStatus
from tests.conftest import CompliantAgentsClient

APP_LAYER_FILES = (Path(__file__).parents[1] / "src" / "app.py",) + tuple(
    (Path(__file__).parents[1] / "frontend").glob("*.py")
)


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
    service = MentorConceptService(client=CompliantAgentsClient())
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


def test_app_layer_does_not_bypass_mentor_concept_service() -> None:
    """UI/application modules must not import or expose raw Mentor/Concept APIs."""
    forbidden_modules = {
        "src.agents.mentor_agent",
        "src.agents.concept_agent",
    }
    forbidden_names = {
        "MentorAgent",
        "ConceptAgent",
        "MentorOutput",
        "ConceptOutput",
    }

    service_imported = False
    service_methods: set[str] = set()

    for path in APP_LAYER_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "src.services.mentor_concept"
                and any(alias.name == "MentorConceptService" for alias in node.names)
            ):
                service_imported = True
            if isinstance(node, ast.ImportFrom) and node.module in forbidden_modules:
                raise AssertionError(
                    f"{path} bypasses MentorConceptService via {node.module}"
                )
            if isinstance(node, ast.Name) and node.id in forbidden_names:
                raise AssertionError(
                    f"{path} directly exposes the raw {node.id} contract"
                )
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                if node.value.id == "mentor_concept_service":
                    service_methods.add(node.attr)

    assert service_imported, "src/app.py must import MentorConceptService"
    assert {
        "generate_mentor_reviewable",
        "generate_concept_reviewable",
    } <= service_methods
