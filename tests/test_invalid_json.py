import json
from unittest.mock import MagicMock

import pytest

from src.agents.concept_agent import ConceptAgent
from src.agents.mentor_agent import MentorAgent
from tests.conftest import CompliantAgentsClient


def test_invalid_json():
    """
    Verify that invalid JSON raises a JSONDecodeError.
    """

    invalid_response = """
    {
        "explanation": "Python loops"
    """

    with pytest.raises(json.JSONDecodeError):
        json.loads(invalid_response)


def test_mentor_agent_invalid_llm_json_raises_clear_error():
    """MentorAgent translates malformed LLM JSON into a clear ValueError."""
    agent = MentorAgent(client=CompliantAgentsClient())
    agent.mock_mode = False
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
    agent.mock_mode = False
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
