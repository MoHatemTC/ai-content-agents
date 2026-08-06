from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from src.registry import AgentRegistry


class BaseGenerator(ABC):
    def __init__(self, registry: AgentRegistry):
        self.registry = registry

    @abstractmethod
    def generate(self, agent_name: str, inputs: dict[str, Any]) -> BaseModel:
        pass
