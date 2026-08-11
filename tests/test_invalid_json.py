from unittest.mock import MagicMock

import pytest

from src.agents.concept_agent import ConceptAgent
from src.agents.mentor_agent import MentorAgent
from tests.conftest import CompliantAgentsClient, FakeLLMClient


def test_invalid_json_names_the_agent_that_produced_it():
    """This asserted json.loads raises on bad JSON - i.e. it tested CPython.

    It named no agent and could not fail for any reason connected to this
    codebase. What is worth pinning is that an agent turns a malformed reply
    into an error a person can act on.
    """
    agent = MentorAgent(client=FakeLLMClient('{ "explanation": "cut off'), model="m")

    with pytest.raises(ValueError, match="invalid JSON"):
        agent.generate("Loops repeat.", "Explain loops.")


def test_mentor_agent_invalid_llm_json_raises_clear_error():
    """MentorAgent translates malformed LLM JSON into a clear ValueError."""
    agent = MentorAgent(client=CompliantAgentsClient())
    response = MagicMock()
    response.choices[0].message.content = "this is not valid json"
    agent.client = MagicMock()
    agent.client.chat.completions.create.return_value = response

    with pytest.raises(ValueError, match="invalid JSON"):
        agent.generate(
            content="Python loops example",
            user_question="Explain loops",
            difficulty="beginner",
        )


def test_concept_agent_invalid_llm_json_raises_clear_error():
    """ConceptAgent translates malformed LLM JSON into a clear ValueError."""
    agent = ConceptAgent(client=CompliantAgentsClient())
    response = MagicMock()
    response.choices[0].message.content = "this is not valid json"
    agent.client = MagicMock()
    agent.client.chat.completions.create.return_value = response

    with pytest.raises(ValueError, match="invalid JSON"):
        agent.generate(
            content="Python loops example",
            user_question="Explain loops",
            difficulty="beginner",
        )
