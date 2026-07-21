from src.agents.registry import AgentRegistry
from src.agents.mentor_agent import MentorAgent
from src.agents.concept_agent import ConceptAgent
from src.validation.schemas import (
    MentorOutput,
    ConceptOutput,
)


def test_registry_returns_correct_agents():
    """
    Verify that the registry returns
    the correct agent implementations.
    """

    registry = AgentRegistry(mock_mode=True)

    mentor = registry.get_agent("mentor")
    concept = registry.get_agent("concept")

    assert isinstance(mentor, MentorAgent)
    assert isinstance(concept, ConceptAgent)


def test_registry_returns_correct_schemas():
    """
    Verify that each registered agent
    is mapped to its correct output schema.
    """

    registry = AgentRegistry(mock_mode=True)

    mentor_schema = registry.get_schema("mentor")
    concept_schema = registry.get_schema("concept")

    assert mentor_schema is MentorOutput
    assert concept_schema is ConceptOutput


def test_registry_lists_all_agents():
    """
    Verify that all available agents
    are listed by the registry.
    """

    registry = AgentRegistry(mock_mode=True)

    agents = registry.list_agents()

    assert "mentor" in agents
    assert "concept" in agents