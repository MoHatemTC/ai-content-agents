from src.registry import AgentRegistry
from src.generation import MockGenerator
from datetime import date, timedelta
from src.schemas import FlashcardSet, StudyPlan, RevisionSession


def test_registry_loads_three_agents():
    registry = AgentRegistry()
    agents = registry.list_agents()
    assert len(agents) == 3
    agent_names = [agent.name for agent in agents]
    assert "flashcard_generator" in agent_names
    assert "study_plan_generator" in agent_names
    assert "revision_plan_generator" in agent_names


def test_get_schema_returns_correct_class():
    registry = AgentRegistry()
    assert registry.get_schema("FlashcardSet") is FlashcardSet
    assert registry.get_schema("StudyPlan") is StudyPlan
    assert registry.get_schema("RevisionSession") is RevisionSession
    assert registry.get_schema("UnknownSchema") is None


def test_get_schema_for_agent():
    registry = AgentRegistry()
    assert registry.get_schema_for_agent("flashcard_generator") is FlashcardSet
    assert registry.get_schema_for_agent("study_plan_generator") is StudyPlan
    assert registry.get_schema_for_agent("revision_plan_generator") is RevisionSession
    assert registry.get_schema_for_agent("unknown_agent") is None


def test_unknown_agent_raises_nothing():
    registry = AgentRegistry()
    assert registry.get_agent("unknown_agent") is None


def test_mock_generator_flashcards_valid():
    registry = AgentRegistry()
    generator = MockGenerator(registry)
    flashcards = generator.generate("flashcard_generator", {
        "material": "Python Programming Fundamentals",
        "count": 3
    })
    assert isinstance(flashcards, FlashcardSet)
    assert len(flashcards.cards) == 3


def test_mock_generator_study_plan_valid():
    registry = AgentRegistry()
    generator = MockGenerator(registry)
    study_plan = generator.generate("study_plan_generator", {
        "goal": "Prepare for Python Certification Exam",
        "topics": ["Data Types", "Control Flow", "Functions", "OOP"],
        "start_date": str(date.today()),
        "end_date": str(date.today() + timedelta(days=30))
    })
    assert isinstance(study_plan, StudyPlan)
    assert len(study_plan.topic_schedule) == 4


def test_mock_generator_revision_valid():
    registry = AgentRegistry()
    generator = MockGenerator(registry)
    revision = generator.generate("revision_plan_generator", {
        "topics": ["Data Types", "Functions"],
        "start_date": str(date.today())
    })
    assert isinstance(revision, RevisionSession)
    assert len(revision.items) == 2
