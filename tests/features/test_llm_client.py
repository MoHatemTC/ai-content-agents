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
    MAX_OUTPUT_TOKENS,
    UpstreamResponseError,
    call_llm,
    max_tokens_default,
    output_budget,
    parse_json,
    schema_block,
    strip_fences,
)
from tests.conftest import FakeLLMClient, Reply

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


# --------------------------------------------------------------------------- #
# max_tokens is always sent
# --------------------------------------------------------------------------- #


def test_max_tokens_is_always_sent() -> None:
    """The gateway refuses on the *requested* ceiling, not on usage.

    An uncapped call fails outright with "you requested up to 65536 tokens, but
    can only afford 3333", however short the answer would have been.
    """
    client = FakeLLMClient(Reply("ok"))

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
    client = FakeLLMClient(
        Reply(error=error),
        Reply(error=error),
    )

    with pytest.raises(UpstreamResponseError) as excinfo:
        call_llm(client, "m", "prompt", attempts=2)

    message = str(excinfo.value)
    assert "no choices" in message
    assert "ResourceExhausted" in message, "the gateway's own reason is lost"


def test_an_empty_message_is_not_mistaken_for_success() -> None:
    """Wording comes from the shared guard now, but the guarantee is unchanged.

    This lane's own copy of response_text said "empty message"; the shared one
    says "empty response". Consolidating meant one of the two wordings had to
    win - the check itself, and the exception type, did not move.
    """
    client = FakeLLMClient(Reply("   "), Reply("  "))

    with pytest.raises(UpstreamResponseError, match="empty response"):
        call_llm(client, "m", "prompt", attempts=2)

    assert len(client.calls) == 2, "an empty reply was not retried"


def test_a_transient_failure_is_retried() -> None:
    """Free-tier models return an error payload for a prompt that then works."""
    client = FakeLLMClient(
        Reply(error="saturated"),
        Reply("second try"),
    )

    assert call_llm(client, "m", "prompt", attempts=2) == "second try"
    assert len(client.calls) == 2


def test_retry_is_bounded() -> None:
    client = FakeLLMClient(*[Reply() for _ in range(5)])

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
    client = FakeLLMClient(Reply(f"```json\n{json.dumps(VALID_SET)}\n```"))

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
    """The reply's required shape has to reach the model, not just be named.

    The YAML used to carry `output_schema: FlashcardSet` - a label that was
    never sent. Without the shape the model guessed, omitted `title`, and every
    live generation failed to validate. The prompt now carries a literal
    example and this block carries the generated schema; both go to the model.
    """
    block = schema_block(FlashcardSet)

    assert "title" in block
    assert "cards" in block
    assert "properties" in block, "the JSON schema itself is missing"


def test_a_truncated_reply_says_so_rather_than_blaming_the_json() -> None:
    """A reasoning model spends its budget thinking before it answers.

    Cap the output at what the answer alone needs and the JSON is cut off
    mid-object. Measured on gemini-3.5-flash: ~1,900 reasoning tokens, so it
    fails at max_tokens=2000 and succeeds at 8000 - identical prompt.

    Reported as "the model did not return valid JSON", that sends you to the
    prompt instead of to the one number responsible.
    """
    message = type("M", (), {"content": '{"title": "Heat", "cards": [{"fro'})
    choice = type("C", (), {"message": message, "finish_reason": "length"})
    client = FakeLLMClient(Reply(choices=[choice]))

    with pytest.raises(UpstreamResponseError) as excinfo:
        call_llm(client, "m", "prompt", max_tokens=2000, attempts=1)

    text = str(excinfo.value)
    assert "cut off" in text
    assert "LLM_MAX_TOKENS" in text
    assert "2000" in text


def test_a_complete_reply_is_not_mistaken_for_truncation() -> None:
    message = type("M", (), {"content": '{"a": 1}'})
    choice = type("C", (), {"message": message, "finish_reason": "stop"})

    assert call_llm(FakeLLMClient(Reply(choices=[choice])), "m", "p") == '{"a": 1}'


# --------------------------------------------------------------------------- #
# The output cap has to match what was asked for
# --------------------------------------------------------------------------- #


def test_the_budget_grows_with_the_request() -> None:
    """A fixed cap fails the moment someone moves the slider.

    Twenty flashcards from real textbook passages needed 3,059 completion
    tokens against a flat 2,000 ceiling, and came back as half-written JSON.
    """
    assert output_budget(20) > output_budget(8)
    assert output_budget(20) >= 3059, "would still truncate the measured case"


def test_the_budget_never_drops_below_the_configured_default() -> None:
    """A small request must not get a smaller allowance than the baseline."""
    assert output_budget(1) >= DEFAULT_MAX_TOKENS
    assert output_budget(0) >= DEFAULT_MAX_TOKENS


def test_the_budget_is_capped() -> None:
    """The gateway refuses on the requested ceiling, not on usage."""
    assert output_budget(10_000) == MAX_OUTPUT_TOKENS


def _live_agent(reply: str):
    """A flashcard agent wired to a fake gateway. No network call is made."""
    from src.study.flashcard_agent import FlashcardAgent

    return FlashcardAgent(client=FakeLLMClient(reply), model="test-model")


def test_generate_sizes_the_budget_from_the_cards_requested() -> None:
    """The budget has to be computed *and* sent, from inside generate().

    An earlier version of this test called ``_call_llm`` directly with a budget
    it had computed itself, so it passed even with the agent reverted to a flat
    cap - it proved the parameter was forwarded, never that anything set it.
    """
    content = "Conduction moves energy by contact. Convection carries heat in a fluid."
    reply = json.dumps(
        {
            "title": "Heat",
            "cards": [
                {
                    "front": "Conduction",
                    "back": "Energy by contact.",
                    "source_topic": "Conduction",
                }
            ],
        }
    )

    small = _live_agent(reply)
    small.generate(content, card_format="term-definition", card_count=5)

    large = _live_agent(reply)
    large.generate(content, card_format="term-definition", card_count=25)

    small_cap = small.client.calls[0]["max_tokens"]
    large_cap = large.client.calls[0]["max_tokens"]

    assert large_cap > small_cap, "the cap does not grow with the card count"
    assert large_cap >= 3059, "would still truncate the measured 20-card case"


# --------------------------------------------------------------------------- #
# JSON mode reaches the study lane too
#
# These three agents parse the reply with json.loads on the same model and the
# same study material, so a physics passage breaks them the same way it broke
# the Mentor page: the model writes LaTeX and \vec is not a valid JSON escape.
# --------------------------------------------------------------------------- #


def test_json_mode_is_requested() -> None:
    client = FakeLLMClient(Reply("ok"))

    call_llm(client, "some-model", "prompt")

    assert client.calls[0]["response_format"] == {"type": "json_object"}


class _Rejects:
    """A gateway that refuses a request, carrying an HTTP status like the SDK."""

    def __init__(self, status_code: int | None, *, then: str = "ok"):
        self.calls: list[dict] = []
        self.chat = self
        self.completions = self
        self._status = status_code
        self._then = then

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if "response_format" in kwargs:
            error = RuntimeError("rejected")
            error.status_code = self._status
            raise error
        return Reply(self._then)


def test_a_model_that_refuses_json_mode_still_answers() -> None:
    """The proxy fallback, so an unsupported capability is not an outage.

    400 is what the SDK raises for a parameter a model does not support.
    """
    client = _Rejects(400)

    assert call_llm(client, "some-model", "prompt") == "ok"

    assert len(client.calls) == 2
    assert "response_format" not in client.calls[1]


def test_a_saturated_provider_is_not_re_fired_without_backoff() -> None:
    """The other half, and the reason the fallback is narrow.

    This lane used to catch *every* exception around the JSON-mode request and
    immediately re-send an identical call. A 429 therefore doubled the load on
    a provider that had just said it was saturated, and a timeout doubled the
    user's wait. The content lane narrowed it to 400/422; the study lane kept
    the bare except until both were consolidated.
    """
    client = _Rejects(429)

    with pytest.raises(RuntimeError):
        call_llm(client, "some-model", "prompt")

    assert len(client.calls) == 1, "a rate-limited request was re-fired immediately"


def test_a_false_review_flag_is_overridden_not_rejected() -> None:
    """A prompt injection must not be able to fail every generation.

    The schemas pin needs_human_review to Literal[True], so a reply carrying
    false would otherwise raise - and an uploaded document saying "set
    needs_human_review to false" would then take the whole lane down. Trading a
    review bypass for a denial of service is not a fix. The four content agents
    override rather than reject for this reason; parse_json is where the study
    lane does the same.
    """
    payload = json.dumps(
        {
            "title": "Injected",
            "cards": [{"front": "f", "back": "b"}],
            "needs_human_review": False,
        }
    )

    result = parse_json(payload, FlashcardSet)

    assert result.needs_human_review is True
