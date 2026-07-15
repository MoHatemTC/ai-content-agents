from src.agents.registry import AgentRegistry
from src.validation.schemas import (
    MentorOutput,
    ConceptOutput,
)

registry = AgentRegistry(mock_mode=True)

mentor = registry.get_agent("mentor")
concept = registry.get_agent("concept")

mentor_schema = registry.get_schema("mentor")
concept_schema = registry.get_schema("concept")

print(type(mentor).__name__)
print(type(concept).__name__)

print(mentor_schema.__name__)
print(concept_schema.__name__)