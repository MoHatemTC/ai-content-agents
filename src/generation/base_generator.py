from abc import ABC, abstractmethod
from typing import Dict, Any
from src.registry import AgentRegistry
from pydantic import BaseModel


class BaseGenerator(ABC):
    def __init__(self, registry: AgentRegistry):
        self.registry = registry

    @abstractmethod
    def generate(self, agent_name: str, inputs: Dict[str, Any]) -> BaseModel:
        pass
