"""A missing prompt template must fail loudly at construction.

Previously this ``rename``d the real ``src/prompts/mentor.yaml`` to
``mentor.bak`` and renamed it back in a ``finally``; an interrupted run left the
repository with no mentor prompt at all. See ``test_invalid_yaml`` for the
same fix.
"""

import pytest

from src.agents import explanation_agent_base
from src.agents.concept_agent import ConceptAgent
from src.agents.mentor_agent import MentorAgent
from tests.conftest import CompliantAgentsClient

AGENTS = [
    pytest.param(MentorAgent, "mentor.yaml", id="mentor"),
    pytest.param(ConceptAgent, "concept.yaml", id="concept"),
]


@pytest.mark.parametrize("agent_class,prompt_file", AGENTS)
def test_a_missing_prompt_names_the_path(
    agent_class, prompt_file, tmp_path, monkeypatch
):
    monkeypatch.setattr(explanation_agent_base, "PROMPTS_DIR", tmp_path)

    with pytest.raises(FileNotFoundError, match=prompt_file):
        agent_class(client=CompliantAgentsClient())


@pytest.mark.parametrize("agent_class,prompt_file", AGENTS)
def test_the_real_prompt_loads(agent_class, prompt_file):
    """Control: the three failure tests above would all pass against an agent
    whose constructor raised unconditionally."""
    agent = agent_class(client=CompliantAgentsClient())

    assert agent.prompt_file == prompt_file
    assert agent.prompt.get("prompt_template")
