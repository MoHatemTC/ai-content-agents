import pytest

from src.agents.mentor_agent import MentorAgent


def test_missing_environment_variables(monkeypatch):
    """
    Verify that the agent raises an error
    when mock mode is disabled and the API
    configuration is missing.
    """

    monkeypatch.delenv("LITELLM_API_KEY", raising=False)

    with pytest.raises(
        ValueError,
        match="Missing LITELLM_API_KEY"
    ):
        MentorAgent(mock_mode=False)