"""The gateway refuses to build a client when it is not configured."""

import pytest

from src.agents.mentor_agent import MentorAgent


def test_missing_environment_variables(monkeypatch):
    """An agent with no credentials and no injected client must not construct.

    This is what replaced mock mode as the safety net. Previously the agent
    happily constructed with ``client = None`` whenever the flag was on, so a
    misconfigured deployment surfaced later and somewhere else. Now it fails
    here, with a message naming what to set.
    """
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)
    monkeypatch.delenv("LITELLM_BASE_URL", raising=False)

    with pytest.raises(ValueError, match="LITELLM_API_KEY"):
        MentorAgent()
