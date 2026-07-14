"""
Agent Registry

Central registry for all available AI agents.

The registry creates and stores agent instances,
allowing other parts of the application to retrieve
them by name instead of importing them directly.
"""

from __future__ import annotations

from typing import Dict

from src.agents.concept_agent import ConceptAgent
from src.agents.mentor_agent import MentorAgent


class AgentRegistry:
    """
    Registry for all available agents.

    Responsibilities:
    - Initialize agent instances.
    - Store agents in a dictionary.
    - Return agents by name.
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

        self._agents: Dict[str, object] = {
            "mentor": MentorAgent(mock_mode=mock_mode),
            "concept": ConceptAgent(mock_mode=mock_mode),
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

        agent = self._agents.get(name.lower())

        if agent is None:
            available = ", ".join(self._agents.keys())

            raise KeyError(
                f"Unknown agent '{name}'. "
                f"Available agents: {available}"
            )

        return agent

    def list_agents(self) -> list[str]:
        """
        Return the names of all registered agents.
        """

        return list(self._agents.keys())