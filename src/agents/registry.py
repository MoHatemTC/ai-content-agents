"""
Agent Registry

Central registry for all available AI agents.

The registry creates and stores agent instances together
with their corresponding output schemas, allowing other
parts of the application to retrieve them by name.
"""

from __future__ import annotations

from typing import Any

from src.agents.concept_agent import ConceptAgent
from src.agents.mentor_agent import MentorAgent
from src.validation.schemas import (
    ConceptOutput,
    MentorOutput,
)


class AgentRegistry:
    """
    Registry for all available agents.

    Responsibilities:
    - Initialize agent instances.
    - Store agents together with their output schemas.
    - Return agents and schemas by name.
    """

    def __init__(self, mock_mode: bool | None = None) -> None:
        """
        Initialize the registry.

        Args:
            mock_mode:
                Controls whether agents use mock responses.
                If None, each agent uses the MOCK_MODE
                environment variable.
        """

        self._agents: dict[str, dict[str, Any]] = {
            "mentor": {
                "agent": MentorAgent(mock_mode=mock_mode),
                "schema": MentorOutput,
            },
            "concept": {
                "agent": ConceptAgent(mock_mode=mock_mode),
                "schema": ConceptOutput,
            },
        }

    def get_agent(self, name: str):
        """
        Retrieve an agent by name.

        Args:
            name:
                Agent name.

        Returns:
            The requested agent instance.

        Raises:
            KeyError:
                If the requested agent does not exist.
        """

        entry = self._agents.get(name.lower())

        if entry is None:
            available = ", ".join(self._agents.keys())

            raise KeyError(
                f"Unknown agent '{name}'. "
                f"Available agents: {available}"
            )

        return entry["agent"]

    def get_schema(self, name: str):
        """
        Retrieve the output schema for an agent.

        Args:
            name:
                Agent name.

        Returns:
            The corresponding Pydantic schema.

        Raises:
            KeyError:
                If the requested agent does not exist.
        """

        entry = self._agents.get(name.lower())

        if entry is None:
            available = ", ".join(self._agents.keys())

            raise KeyError(
                f"Unknown agent '{name}'. "
                f"Available agents: {available}"
            )

        return entry["schema"]

    def list_agents(self) -> list[str]:
        """
        Return the names of all registered agents.
        """

        return list(self._agents.keys())