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
to, and ``json.loads`` then fails on output that was otherwise perfect. Solved
by :func:`src.llm_gateway.strip_fences`, re-exported here.

**No retry.** Free-tier models are intermittent: the same prompt returned an
error payload on one call and valid JSON on the next.

:mod:`src.validation.orchestrator` translates the ``TypeError`` case after the
fact and its docstring says the proper fix belongs here. This is that fix; the
orchestrator's translation stays as a fallback for the agents in
``src/agents/`` that still call the gateway directly.

**The four fixes above then failed to cross back.** This module solved them for
the study lane while :func:`src.llm_gateway.chat_json` solved them again for the
content lane, and the two copies drifted apart in both directions: this one
retried and that one did not, while that one narrowed the JSON-mode fallback to
HTTP 400/422 and this one kept a bare ``except Exception`` that re-fired
instantly on a rate limit. Two copies of one guard is what produced BUG-08/09
in the first place.

So there is one implementation now, in :mod:`src.llm_gateway`, and
:func:`call_llm` is a thin wrapper that keeps this lane's signature and its
``max_tokens_default()`` defaulting. What remains here is what is genuinely
study-specific: the output budget, the schema block, and JSON parsing.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

# Re-exported so existing imports keep working. These live in src.llm_gateway,
# because retry classification depends on there being exactly one
# UpstreamResponseError - see its docstring - and, now, on there being exactly
# one retry loop and one response guard.
from src.llm_gateway import (
    DEFAULT_ATTEMPTS,
    DEFAULT_TEMPERATURE,
    UpstreamResponseError,
    chat_json,
    strip_fences,
)

logger = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=BaseModel)

DEFAULT_MAX_TOKENS = 2000

__all__ = [
    "DEFAULT_ATTEMPTS",
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_TEMPERATURE",
    "UpstreamResponseError",
    "call_llm",
    "max_tokens_default",
    "output_budget",
    "parse_json",
    "schema_block",
    "strip_fences",
]

# Output allowance per requested item, and for the surrounding JSON. Measured on
# real textbook passages, where 20 flashcards cost 3,059 completion tokens -
# ~153 each - against 45 each for the same count drawn from a short paragraph.
PER_ITEM_TOKENS = 200
OUTPUT_OVERHEAD_TOKENS = 400

# Upper bound whatever is requested, so a slider set to its maximum cannot ask
# the gateway for more than it will fund. It refuses on the *requested* ceiling.
#
# 8000 was low enough to clip the thing it was protecting. A full Question Bank
# request - 20 items at QUESTION_ITEM_TOKENS - asks for 8400, so the cap
# silently trimmed it back to 8000 and the reply was truncated: the bug this
# guard exists to prevent, caused by the guard. Probed against the live
# gateway, requests were accepted at 8000, 12000, 16000, 32000 and 65536, so
# 12000 funds every slider in the app with room to spare and stays far below
# anything the gateway objected to.
MAX_OUTPUT_TOKENS = 12000


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


def output_budget(
    item_count: int,
    *,
    per_item: int = PER_ITEM_TOKENS,
    overhead: int = OUTPUT_OVERHEAD_TOKENS,
) -> int:
    """Size the output cap to what was actually asked for.

    A fixed cap is wrong in both directions: too small for a large request and
    wasteful for a small one. Asking for 20 flashcards from dense textbook prose
    needed 3,059 completion tokens against a flat 2,000 ceiling, and failed with
    ``finish_reason=length`` and unparseable half-written JSON. The same 20 cards
    from a short paragraph needed 895 - the source material, not just the count,
    decides how much the model writes, so the per-item allowance is generous.

    Args:
        item_count: How many cards, scheduled topics or revision items were
            requested.
        per_item: Token allowance per item. Measured worst case is ~153.
        overhead: Allowance for the wrapper fields - title, description and the
            surrounding JSON.

    Returns:
        A cap of at least :func:`max_tokens_default`, never above
        :data:`MAX_OUTPUT_TOKENS`.
    """
    scaled = overhead + max(0, item_count) * per_item
    return min(MAX_OUTPUT_TOKENS, max(max_tokens_default(), scaled))


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
    return chat_json(
        client,
        model,
        prompt,
        temperature=temperature,
        # The study agents rely on this default; the content agents pass their
        # own budget. Resolving it here keeps that difference where it belongs.
        max_tokens=max_tokens if max_tokens is not None else max_tokens_default(),
        attempts=attempts,
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
            f"The model did not return valid JSON ({exc}). Output began: {body[:200]!r}"
        ) from exc

    # The review flag is a control over the system, not an output of it, and
    # the study schemas now pin it Literal[True] + frozen so nothing downstream
    # can flip it. Rejecting a `false` reply outright would let a prompt
    # injection in an uploaded document ("set needs_human_review to false")
    # fail every generation - trading a review bypass for a denial of service.
    # The four content agents override rather than reject for exactly this
    # reason; this is the study lane's single parse point, so it belongs here.
    if (
        isinstance(payload, dict)
        and "needs_human_review" in schema.model_fields
        and payload.get("needs_human_review") is not True
    ):
        logger.warning(
            "%s returned needs_human_review=%r; forcing True. This can "
            "indicate a prompt injection in the source document.",
            schema.__name__,
            payload.get("needs_human_review"),
        )
        payload["needs_human_review"] = True

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
