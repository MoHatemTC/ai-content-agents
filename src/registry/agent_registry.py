from pathlib import Path

import yaml
from pydantic import BaseModel

from src.schemas import (
    FlashcardSet,
    RevisionSession,
    StudyPlan,
)


class AgentConfig(BaseModel):
    name: str
    description: str
    input_variables: list
    system_prompt: str
    output_schema: str


class AgentRegistry:
    def __init__(self, prompts_dir: Path | None = None):
        if prompts_dir is None:
            # Resolve prompts directory relative to this file
            self.prompts_dir = Path(__file__).parent.parent / "prompts"
        else:
            self.prompts_dir = prompts_dir
        self.agents: dict[str, AgentConfig] = {}
        self.schemas: dict[str, type[BaseModel]] = {
            "FlashcardSet": FlashcardSet,
            "StudyPlan": StudyPlan,
            "RevisionSession": RevisionSession,
        }
        self._load_agents()

    def _load_agents(self):
        for prompt_file in self.prompts_dir.glob("*_prompt.yaml"):
            with open(prompt_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                agent_config = AgentConfig(**data)
                self.agents[agent_config.name] = agent_config

    def get_agent(self, name: str) -> AgentConfig | None:
        return self.agents.get(name)

    def get_schema(self, schema_name: str) -> type[BaseModel] | None:
        return self.schemas.get(schema_name)

    def get_schema_for_agent(self, agent_name: str) -> type[BaseModel] | None:
        agent = self.get_agent(agent_name)
        if agent:
            return self.get_schema(agent.output_schema)
        return None

    def list_agents(self) -> list:
        return list(self.agents.values())
