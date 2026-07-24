from src.agents.registry import AgentRegistry
from src.agents.mentor_agent import MentorAgent
from src.agents.concept_agent import ConceptAgent
from src.agents.question_bank_agent import QuestionBankAgent
from src.agents.test_help_agent import TestHelpAgent

from src.validation.schemas import (
    MentorOutput,
    ConceptOutput,
    QuestionBankOutput,
    TestHelpOutput,
)


def test_registry_returns_correct_agents():
    """
    Verify that the registry returns
    the correct agent implementations.
    """

    registry = AgentRegistry(mock_mode=True)

    mentor = registry.get_agent("mentor")
    concept = registry.get_agent("concept")
    question_bank = registry.get_agent("question_bank")
    test_help = registry.get_agent("test_help")

    assert isinstance(mentor, MentorAgent)
    assert isinstance(concept, ConceptAgent)
    assert isinstance(question_bank, QuestionBankAgent)
    assert isinstance(test_help, TestHelpAgent)


def test_registry_returns_correct_schemas():
    """
    Verify that each registered agent
    is mapped to its correct output schema.
    """

    registry = AgentRegistry(mock_mode=True)

    mentor_schema = registry.get_schema("mentor")
    concept_schema = registry.get_schema("concept")
    question_bank_schema = registry.get_schema("question_bank")
    test_help_schema = registry.get_schema("test_help")

    assert mentor_schema is MentorOutput
    assert concept_schema is ConceptOutput
    assert question_bank_schema is QuestionBankOutput
    assert test_help_schema is TestHelpOutput


def test_registry_lists_all_agents():
    """
    Verify that all available agents
    are listed by the registry.
    """

    registry = AgentRegistry(mock_mode=True)

    agents = registry.list_agents()

    assert "mentor" in agents
    assert "concept" in agents
    assert "question_bank" in agents
    assert "test_help" in agents