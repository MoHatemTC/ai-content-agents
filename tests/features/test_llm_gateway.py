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
    UpstreamResponseError,
    build_client,
    chat_json,
    default_model,
    gateway_availability,
    response_text,
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


# --------------------------------------------------------------------------- #
# JSON mode
#
# Every caller parses the reply with json.loads, and study material contains
# backslashes. Explaining a physics chapter the model writes LaTeX - $\vec{E}$,
# \Delta V, \lambda - and \v, \D and \l are not valid JSON escapes, so a
# syntactically *complete* reply is rejected by the parser and reaches the
# learner as "The LLM returned invalid JSON".
#
# Measured on the Mentor page against the physics textbook: 3 of 8 identical
# requests failed. With the LaTeX forced to make it deterministic: 0 of 8 plain
# requests parsed, 8 of 8 in JSON mode.
# --------------------------------------------------------------------------- #


class _ApiError(Exception):
    """Shaped like an OpenAI SDK error: carries the HTTP status."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


class _Recorder:
    """Records requests. Optionally fails the first one with a given status."""

    def __init__(
        self,
        *,
        reject_json_mode: bool = False,
        reject_status: int = 400,
        content: str = '{"a": 1}',
    ):
        self._reject = reject_json_mode
        self._reject_status = reject_status
        self._content = content
        self.calls: list[dict] = []
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._reject and "response_format" in kwargs:
            raise _ApiError(
                self._reject_status, "this model does not support response_format"
            )
        message = type("M", (), {"content": self._content})
        choice = type("C", (), {"message": message, "finish_reason": "stop"})
        return type("R", (), {"choices": [choice], "error": None})


def test_json_mode_is_requested() -> None:
    """The fix for the reported bug, in one assertion.

    Without this the model is free to emit raw LaTeX backslashes, which are
    invalid JSON escapes.
    """
    client = _Recorder()

    chat_json(client, "some-model", "prompt")

    assert client.calls[0]["response_format"] == {"type": "json_object"}


def test_a_model_that_refuses_json_mode_still_answers() -> None:
    """Not every model behind a LiteLLM proxy supports JSON mode.

    A rejected request is worse than an unescaped one, so the call is retried
    without it rather than taking the whole lane down for a capability probe.
    """
    client = _Recorder(reject_json_mode=True)

    assert chat_json(client, "some-model", "prompt") == '{"a": 1}'

    assert len(client.calls) == 2, "the request was not retried"
    assert "response_format" in client.calls[0]
    assert "response_format" not in client.calls[1]


@pytest.mark.parametrize("status", [401, 429, 500, 503])
def test_a_failure_that_is_not_about_the_request_shape_is_not_retried(status) -> None:
    """The capability probe used to sit behind a bare ``except Exception``.

    So a 429 - the provider saying it is saturated - fired a second identical
    request immediately, with no backoff: double the load on a provider that
    had just asked for less, and on a timeout, double the user's wait. Only 400
    and 422 mean "this request is malformed for this model".
    """
    client = _Recorder(reject_json_mode=True, reject_status=status)

    with pytest.raises(_ApiError):
        chat_json(client, "some-model", "prompt")

    assert len(client.calls) == 1, "a non-shape failure was retried without backoff"


@pytest.mark.parametrize("status", [400, 422])
def test_a_rejected_request_shape_is_retried(status) -> None:
    """Control: narrowing the except must not disable the probe itself."""
    client = _Recorder(reject_json_mode=True, reject_status=status)

    assert chat_json(client, "some-model", "prompt") == '{"a": 1}'
    assert len(client.calls) == 2


def test_the_output_ceiling_is_sent() -> None:
    """The gateway refuses on the *requested* ceiling, not on usage."""
    client = _Recorder()

    chat_json(client, "some-model", "prompt", max_tokens=1234)

    assert client.calls[0]["max_tokens"] == 1234


def test_a_truncated_reply_says_so_rather_than_blaming_the_json() -> None:
    """A reply cut off mid-object is complete-looking JSON that will not parse.

    Reported as "invalid JSON" it sends you to the prompt; the cause is the one
    number in the request. src/agents had no such check at all - only the study
    lane did.
    """
    message = type("M", (), {"content": '{"explanation": "half a sen'})
    choice = type("C", (), {"message": message, "finish_reason": "length"})
    truncated = type("R", (), {"choices": [choice], "error": None})

    with pytest.raises(UpstreamResponseError) as excinfo:
        response_text(truncated)

    text = str(excinfo.value)
    assert "cut off" in text
    assert "LLM_MAX_TOKENS" in text


def test_a_complete_reply_is_not_mistaken_for_truncation() -> None:
    message = type("M", (), {"content": '{"a": 1}'})
    choice = type("C", (), {"message": message, "finish_reason": "stop"})
    complete = type("R", (), {"choices": [choice], "error": None})

    assert response_text(complete) == '{"a": 1}'
