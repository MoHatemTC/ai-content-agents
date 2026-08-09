"""What ``_call_llm`` sends and what it does with what comes back.

The original ``test_api_mock_response`` built a MagicMock, assigned a JSON
string to ``mock_response.choices[0].message.content``, handed it to the agent
and asserted the string came back. MagicMock returns whatever you assign, so it
asserted that ``unittest.mock`` works - it passed with the agent's body deleted.
"""

import pytest

from src.agents.concept_agent import ConceptAgent
from src.agents.mentor_agent import MentorAgent
from src.llm_gateway import UpstreamResponseError
from tests.conftest import FakeLLMClient, Reply

AGENTS = [
    pytest.param(MentorAgent, id="mentor"),
    pytest.param(ConceptAgent, id="concept"),
]


@pytest.mark.parametrize("agent_class", AGENTS)
def test_the_prompt_reaches_the_provider_as_a_single_user_message(agent_class):
    client = FakeLLMClient('{"ok": true}')
    agent = agent_class(client=client, model="test-model")

    agent._call_llm("Explain loops")

    (request,) = client.calls
    assert request["model"] == "test-model"
    assert [m["role"] for m in request["messages"]] == ["user"]
    assert request["messages"][0]["content"] == "Explain loops"


@pytest.mark.parametrize("agent_class", AGENTS)
def test_json_mode_is_requested(agent_class):
    """LaTeX in a physics textbook produced backslash escapes that are legal in
    the prose and illegal in JSON. ``response_format`` is what stopped it."""
    client = FakeLLMClient('{"ok": true}')

    agent_class(client=client, model="m")._call_llm("Explain loops")

    assert client.calls[0]["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize("agent_class", AGENTS)
def test_a_truncated_reply_is_an_error_not_a_parse_failure(agent_class):
    """``finish_reason='length'`` means the budget cut the reply off. Reporting
    it as invalid JSON sent people looking at the model instead of at
    LLM_MAX_TOKENS."""
    client = FakeLLMClient(Reply('{"explanation": "cut o', finish_reason="length"))

    with pytest.raises(UpstreamResponseError, match="LLM_MAX_TOKENS"):
        agent_class(client=client, model="m")._call_llm("Explain loops")


@pytest.mark.parametrize("agent_class", AGENTS)
def test_an_error_envelope_is_not_treated_as_content(agent_class):
    """The gateway returns HTTP 200 with an ``error`` body when it is saturated;
    read as content that becomes a confusing JSON parse failure."""
    client = FakeLLMClient(Reply(error={"message": "provider saturated"}))

    with pytest.raises(UpstreamResponseError, match="saturated"):
        agent_class(client=client, model="m")._call_llm("Explain loops")
