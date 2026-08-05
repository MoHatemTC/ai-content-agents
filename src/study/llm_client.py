"""Shared LLM plumbing for the study agents.

`FlashcardAgent`, `StudyPlanAgent` and `RevisionAgent` each carried a private
``_call_llm`` that was the same eight lines, and each parsed the reply with the
same three-step dance. All three shared the same four defects, which is what
duplication reliably buys:

**No ``max_tokens``.** The gateway rejects a request whose *requested* ceiling
exceeds the remaining credit — ``402: you requested up to 65536 tokens, but can
only afford 3333`` — regardless of how short the answer would have been.

**``response.choices[0]`` dereferenced unguarded.** OpenAI-compatible gateways
do not always signal upstream failure with an HTTP error: OpenRouter answers
``200`` with ``{"choices": null, "error": {...}}`` when a provider is saturated.
The SDK sees success, so the agent raises ``TypeError: 'NoneType' object is not
subscriptable``, which names neither the cause nor a remedy.

**No fence stripping.** Models wrap JSON in ``` blocks despite being told not
to, and ``json.loads`` then fails on output that was otherwise perfect.

**No retry.** Free-tier models are intermittent: the same prompt returned an
error payload on one call and valid JSON on the next.

:mod:`src.validation.orchestrator` translates the ``TypeError`` case after the
fact and its docstring says the proper fix belongs here. This is that fix; the
orchestrator's translation stays as a fallback for the agents in
``src/agents/`` that still call the gateway directly.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=BaseModel)

DEFAULT_MAX_TOKENS = 2000
DEFAULT_TEMPERATURE = 0.2
DEFAULT_ATTEMPTS = 2

_FENCE = re.compile(r"^\s*```(?:json)?\s*(?P<body>.*?)\s*```\s*$", re.DOTALL)


class UpstreamResponseError(RuntimeError):
    """The gateway returned a success status carrying an error payload.

    Named separately from the identically-purposed error in
    :mod:`src.validation.orchestrator` to avoid a ``study -> validation``
    import for one exception type. Worth consolidating once something else
    needs it.
    """


def max_tokens_default() -> int:
    """Return the per-call output cap, from ``LLM_MAX_TOKENS`` or the default.

    Read at call time rather than import time so a deployment or a test can
    change it without reimporting.
    """
    raw = os.getenv("LLM_MAX_TOKENS", "").strip()
    if not raw:
        return DEFAULT_MAX_TOKENS
    try:
        return max(1, int(raw))
    except ValueError:
        logger.warning("LLM_MAX_TOKENS=%r is not an integer; using default", raw)
        return DEFAULT_MAX_TOKENS


def schema_block(schema: type[BaseModel]) -> str:
    """Render a schema into prompt text the model can conform to.

    The prompt templates say "valid JSON matching the FlashcardSet schema" while
    ``output_schema: FlashcardSet`` in the YAML is only a label — it is never
    rendered, so the model had to guess the shape. It guessed
    ``{"cards": [...]}``, omitted the required ``title``, and every live
    generation died in ``model_validate``.

    Args:
        schema: The Pydantic model the reply must conform to.

    Returns:
        A prompt fragment naming the required keys and the full JSON schema.
    """
    required = [name for name, f in schema.model_fields.items() if f.is_required()]
    return (
        f"\nReturn a single JSON object conforming to the {schema.__name__} schema "
        "below. Include every required key; emit no prose, no explanation and no "
        "code fences.\n"
        f"Required keys: {', '.join(required)}\n"
        f"JSON schema: {json.dumps(schema.model_json_schema())}\n"
    )


def strip_fences(text: str) -> str:
    """Remove a surrounding ``` block, if the model added one."""
    match = _FENCE.match(text)
    return match.group("body") if match else text.strip()


def sentence_about(content: str, topic: str) -> str:
    """Return the sentence of ``content`` that best introduces ``topic``.

    Mock mode exists so the app runs offline, but its output is what gets
    demonstrated, so it should still be made of the document. Quoting the
    sentence that mentions a topic keeps the mock deterministic and grounded
    while saying something true about the material, rather than restating that
    the material exists.

    Args:
        content: The source text.
        topic: The topic to find.

    Returns:
        The first sentence mentioning ``topic``; otherwise the opening sentence
        of the content, which is at least drawn from the same document.
    """
    sentences = [
        part.strip() for part in re.split(r"(?<=[.!?])\s+", content) if part.strip()
    ]
    if not sentences:
        return f"{topic} (no source text was supplied)."

    needle = topic.lower()
    for sentence in sentences:
        if needle in sentence.lower():
            return sentence

    return sentences[0]


def call_llm(
    client: Any,
    model: str,
    prompt: str,
    *,
    max_tokens: int | None = None,
    temperature: float = DEFAULT_TEMPERATURE,
    attempts: int = DEFAULT_ATTEMPTS,
) -> str:
    """Send ``prompt`` and return the reply body.

    Args:
        client: An OpenAI-compatible client.
        model: Model id.
        prompt: The fully rendered prompt.
        max_tokens: Output cap; defaults to :func:`max_tokens_default`. Always
            sent, because the gateway refuses on the requested ceiling.
        temperature: Sampling temperature.
        attempts: Total tries, including the first. Free-tier gateways return
            an error payload intermittently for a prompt that succeeds on retry.

    Returns:
        The reply text, fences stripped.

    Raises:
        UpstreamResponseError: If the gateway returned no usable choice on every
            attempt, or the reply was empty.
    """
    if client is None:
        raise UpstreamResponseError("No LLM client; the agent is in mock mode.")

    last_error: str = "no attempts were made"

    for attempt in range(1, max(1, attempts) + 1):
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens if max_tokens is not None else max_tokens_default(),
        )

        choices = getattr(response, "choices", None)
        if not choices:
            # A success status carrying an error payload. Surface what the
            # gateway said rather than letting choices[0] raise TypeError.
            detail = getattr(response, "error", None) or "no detail provided"
            last_error = f"gateway returned no choices ({detail})"
            logger.warning("llm attempt %d/%d: %s", attempt, attempts, last_error)
        else:
            choice = choices[0]
            content = getattr(choice.message, "content", None)

            # A reasoning model spends its budget thinking before it answers, so
            # a cap sized for the answer alone truncates the JSON mid-object.
            # Without this check the failure surfaces from json.loads as "the
            # model did not return valid JSON", which sends you looking at the
            # prompt instead of at the one number that caused it. Measured:
            # gemini-3.5-flash spends ~1,900 tokens reasoning, so it fails at
            # max_tokens=2000 and succeeds at 8000.
            if getattr(choice, "finish_reason", None) == "length":
                raise UpstreamResponseError(
                    "The model's reply was cut off by the output limit "
                    f"(max_tokens={max_tokens if max_tokens is not None else max_tokens_default()}), "
                    "so the JSON is incomplete. Raise LLM_MAX_TOKENS, or use a "
                    "model that does not emit reasoning tokens - they are "
                    "charged against the same budget as the answer."
                )

            if content and content.strip():
                return strip_fences(content)
            last_error = "gateway returned an empty message"
            logger.warning("llm attempt %d/%d: %s", attempt, attempts, last_error)

        if attempt < attempts:
            time.sleep(0.5 * attempt)

    raise UpstreamResponseError(
        f"The model returned no usable response after {attempts} attempt(s): "
        f"{last_error}. This usually means the provider is saturated, rate "
        "limited, or out of credit."
    )


def parse_json(text: str, schema: type[ModelT]) -> ModelT:
    """Parse ``text`` into ``schema``, with errors that name what was wrong.

    Args:
        text: The reply body.
        schema: The Pydantic model to validate against.

    Returns:
        The validated instance.

    Raises:
        ValueError: If the text is not JSON, or does not satisfy the schema. The
            message carries the offending output so a failure is diagnosable
            from a log rather than only by re-running it.
    """
    body = strip_fences(text)

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"The model did not return valid JSON ({exc}). Output began: "
            f"{body[:200]!r}"
        ) from exc

    try:
        return schema.model_validate(payload)
    except ValidationError as exc:
        missing = ", ".join(
            ".".join(str(part) for part in error["loc"]) for error in exc.errors()
        )
        raise ValueError(
            f"The model's JSON does not match {schema.__name__}: {missing}. "
            f"Output began: {body[:200]!r}"
        ) from exc
