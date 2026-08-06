"""Tests for the shared gateway client factory.

The behaviour worth pinning here is the *refusal*: with no credentials,
:func:`build_client` raises rather than handing back ``None``. That is what
replaces mock mode as the safety net - a test that forgets to inject a fake
client fails loudly instead of quietly reaching the network.
"""

from __future__ import annotations

import pytest

from src.llm_gateway import (
    DEFAULT_MODEL,
    GatewayCredentialsError,
    build_client,
    default_model,
    gateway_availability,
)


def _clear_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)
    monkeypatch.delenv("LITELLM_BASE_URL", raising=False)


def test_no_credentials_refuses_to_build_a_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An agent with no client is not a working agent.

    Mock mode used to absorb this: the agent constructed happily with
    ``client = None`` and only failed later, wherever generation happened to
    be. Failing at construction says what is wrong while the cause is still
    on screen.
    """
    _clear_credentials(monkeypatch)

    with pytest.raises(GatewayCredentialsError) as excinfo:
        build_client()

    message = str(excinfo.value)
    assert "LITELLM_API_KEY" in message, "the message does not name what to set"
    assert "client=" in message, "the message does not mention injection"


def test_the_refusal_is_still_a_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Callers already catch ValueError; the rename must not break them."""
    _clear_credentials(monkeypatch)

    with pytest.raises(ValueError):
        build_client()


def test_partial_credentials_are_not_enough(monkeypatch: pytest.MonkeyPatch) -> None:
    """A key with no base URL points the SDK at the wrong host entirely."""
    _clear_credentials(monkeypatch)
    monkeypatch.setenv("LITELLM_API_KEY", "sk-test")

    available, reason = gateway_availability()

    assert not available
    assert "LITELLM_BASE_URL" in reason


def test_availability_reports_ready_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LITELLM_API_KEY", "sk-test")
    monkeypatch.setenv("LITELLM_BASE_URL", "https://gateway.example/v1")

    available, reason = gateway_availability()

    assert available
    assert reason == ""


def test_the_model_is_read_at_call_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set in .env after import, it still has to take effect."""
    monkeypatch.setenv("DEFAULT_MODEL", "some-other-model")

    assert default_model() == "some-other-model"


def test_the_model_falls_back_to_the_shared_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEFAULT_MODEL", raising=False)

    assert default_model() == DEFAULT_MODEL
