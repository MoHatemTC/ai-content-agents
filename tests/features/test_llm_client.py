"""Tests for the shared study-agent LLM plumbing.

Everything here guards a defect that shipped. The three study agents each held a
private copy of the same eight-line call and the same three-step parse, so they
shared every one of these failures, and the app generated placeholder text for
weeks without anyone seeing an error.

No test may touch the network: every one injects a fake client.
"""

from __future__ import annotations

import json

import pytest

from src.schemas import FlashcardSet
from src.study.llm_client import (
    DEFAULT_MAX_TOKENS,
    UpstreamResponseError,
    call_llm,
    max_tokens_default,
    parse_json,
    schema_block,
    sentence_about,
    strip_fences,
)

CONTENT = (
    "Conduction moves energy through a material by direct molecular contact. "
    "Convection carries heat in the bulk motion of a fluid. "
    "Radiation needs no medium: energy crosses a vacuum as electromagnetic waves."
)

VALID_SET = {
    "title": "Heat Transfer Basics",
    "cards": [
        {"front": "Conduction", "back": "Energy moves by direct molecular contact."}
    ],
}


class _Reply:
    """Minimal stand-in for an OpenAI SDK response."""

    def __init__(self, content: str | None = None, choices=None, error=None):
        if choices is None and content is not None:
            message = type("M", (), {"content": content})
            choices = [type("C", (), {"message": message})]
        self.choices = choices
        self.error = error


class FakeClient:
    """Returns queued replies and records every request."""

    def __init__(self, *replies: _Reply):
        self._replies = list(replies)
        self.calls: list[dict] = []
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._replies.pop(0) if self._replies else _Reply(content="{}")


# --------------------------------------------------------------------------- #
# max_tokens is always sent
# --------------------------------------------------------------------------- #


def test_max_tokens_is_always_sent() -> None:
    """The gateway refuses on the *requested* ceiling, not on usage.

    An uncapped call fails outright with "you requested up to 65536 tokens, but
    can only afford 3333", however short the answer would have been.
    """
    client = FakeClient(_Reply(content="ok"))

    call_llm(client, "some-model", "prompt")

    assert "max_tokens" in client.calls[0]
    assert client.calls[0]["max_tokens"] == DEFAULT_MAX_TOKENS


def test_max_tokens_is_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MAX_TOKENS", "512")

    assert max_tokens_default() == 512


def test_a_nonsense_max_tokens_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """A typo in .env must not take the agents down."""
    monkeypatch.setenv("LLM_MAX_TOKENS", "lots")

    assert max_tokens_default() == DEFAULT_MAX_TOKENS


# --------------------------------------------------------------------------- #
# A success status carrying an error payload
# --------------------------------------------------------------------------- #


def test_missing_choices_raises_something_legible() -> None:
    """OpenAI-compatible gateways answer 200 with choices=null when saturated.

    The agents dereferenced choices[0] unguarded, so this surfaced as
    "TypeError: 'NoneType' object is not subscriptable" - an error naming
    neither the cause nor a remedy, and not recognisably retryable.
    """
    error = {"message": "Upstream error from Nvidia: ResourceExhausted", "code": 502}
    client = FakeClient(
        _Reply(choices=None, error=error),
        _Reply(choices=None, error=error),
    )

    with pytest.raises(UpstreamResponseError) as excinfo:
        call_llm(client, "m", "prompt", attempts=2)

    message = str(excinfo.value)
    assert "no choices" in message
    assert "ResourceExhausted" in message, "the gateway's own reason is lost"


def test_an_empty_message_is_not_mistaken_for_success() -> None:
    client = FakeClient(_Reply(content="   "), _Reply(content="  "))

    with pytest.raises(UpstreamResponseError, match="empty message"):
        call_llm(client, "m", "prompt", attempts=2)


def test_a_transient_failure_is_retried() -> None:
    """Free-tier models return an error payload for a prompt that then works."""
    client = FakeClient(
        _Reply(choices=None, error="saturated"),
        _Reply(content="second try"),
    )

    assert call_llm(client, "m", "prompt", attempts=2) == "second try"
    assert len(client.calls) == 2


def test_retry_is_bounded() -> None:
    client = FakeClient(*[_Reply(choices=None) for _ in range(5)])

    with pytest.raises(UpstreamResponseError):
        call_llm(client, "m", "prompt", attempts=3)

    assert len(client.calls) == 3


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "wrapped",
    ['```json\n{"a": 1}\n```', '```\n{"a": 1}\n```', '  {"a": 1}  '],
)
def test_code_fences_are_stripped(wrapped: str) -> None:
    """Models wrap JSON in fences despite being told not to."""
    assert json.loads(strip_fences(wrapped)) == {"a": 1}


def test_a_fenced_reply_parses() -> None:
    client = FakeClient(_Reply(content=f"```json\n{json.dumps(VALID_SET)}\n```"))

    text = call_llm(client, "m", "prompt")

    assert parse_json(text, FlashcardSet).title == "Heat Transfer Basics"


def test_a_missing_required_key_is_named() -> None:
    """The real failure: the model returned {"cards": [...]} with no title.

    The old message was "LLM JSON failed FlashcardSet schema", which does not
    say which key, so the cause could not be found from a log.
    """
    with pytest.raises(ValueError) as excinfo:
        parse_json(json.dumps({"cards": []}), FlashcardSet)

    assert "title" in str(excinfo.value)


def test_invalid_json_quotes_what_arrived() -> None:
    with pytest.raises(ValueError) as excinfo:
        parse_json("Sure! Here are your flashcards:", FlashcardSet)

    assert "Sure!" in str(excinfo.value)


# --------------------------------------------------------------------------- #
# The schema reaches the model
# --------------------------------------------------------------------------- #


def test_schema_block_names_the_required_keys() -> None:
    """`output_schema: FlashcardSet` in the YAML is a label that is never sent.

    Without the shape the model guessed, omitted `title`, and every live
    generation failed to validate.
    """
    block = schema_block(FlashcardSet)

    assert "title" in block
    assert "cards" in block
    assert "properties" in block, "the JSON schema itself is missing"


# --------------------------------------------------------------------------- #
# Mock output is made of the document
# --------------------------------------------------------------------------- #


def test_sentence_about_quotes_the_source() -> None:
    assert sentence_about(CONTENT, "Convection") == (
        "Convection carries heat in the bulk motion of a fluid."
    )


def test_sentence_about_falls_back_within_the_document() -> None:
    """An unmatched topic still yields real text, not a canned phrase."""
    result = sentence_about(CONTENT, "Thermodynamics")

    assert result in CONTENT


def test_sentence_about_handles_empty_content() -> None:
    assert "no source text" in sentence_about("", "Conduction")
