"""One place that knows how to reach the LiteLLM gateway.

Seven agents each carried the same eleven lines: read ``LITELLM_API_KEY`` and
``LITELLM_BASE_URL``, raise if either is missing, import ``openai`` lazily,
construct a client, and default the model to ``FW-Kimi-K2.6``. Duplication of
exactly this kind is what let a single defect ship in all three study agents at
once (see :mod:`src.study.llm_client`), so the construction lives here.

The lazy ``openai`` import is deliberate and is kept: the package is only needed
by code that actually calls the gateway, and importing it at module scope would
make it a hard requirement of every test that touches an agent.

Agents take an injected client rather than a mode flag. A flag that silently
swaps real output for fake output is the wrong shape for production code - the
app served *"See the source text for a fuller treatment"* to users for weeks
because the UI forced mock mode regardless of configuration, and nothing on
screen said so. With no flag, a test that fails to inject a double cannot
quietly reach the network: :func:`build_client` raises without credentials, and
CI has none.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

# Models wrap JSON in fences despite being told not to, and ``json.loads`` then
# fails on output that was otherwise perfect.
_FENCE = re.compile(r"^\s*```(?:json)?\s*(?P<body>.*?)\s*```\s*$", re.DOTALL)

# Every agent defaulted to this same model id.
DEFAULT_MODEL = "FW-Kimi-K2.6"

# The study agents used a 60 s timeout; the src/agents ones used the SDK
# default. 60 s for all of them: a request that has not answered by then is not
# going to, and an unbounded wait is worse in a Streamlit app than a clear error.
DEFAULT_TIMEOUT = 60.0


class GatewayCredentialsError(ValueError):
    """The gateway is not configured, so no client can be built.

    Subclasses :class:`ValueError` because that is what the agents raised
    before this module existed, and callers already catch it.
    """


def gateway_availability() -> tuple[bool, str]:
    """Report whether a gateway call could be made, and why not.

    Returns:
        ``(available, reason)``. ``reason`` is empty when available.
    """
    try:
        import openai  # noqa: F401
    except ImportError:
        return False, "the openai package is not installed (pip install openai)"

    if not os.getenv("LITELLM_API_KEY") or not os.getenv("LITELLM_BASE_URL"):
        return False, "LITELLM_API_KEY and LITELLM_BASE_URL are not both set in .env"

    return True, ""


def default_model() -> str:
    """Return the configured model id.

    Read at call time rather than import time so a deployment or a test can
    change it without reimporting.
    """
    return os.getenv("DEFAULT_MODEL", DEFAULT_MODEL)


def build_client(*, timeout: float = DEFAULT_TIMEOUT) -> Any:
    """Return an OpenAI-compatible client pointed at the configured gateway.

    Args:
        timeout: Per-request timeout in seconds.

    Returns:
        An ``openai.OpenAI`` instance.

    Raises:
        GatewayCredentialsError: If the gateway is not configured. Raising here
            rather than returning ``None`` is the point of this module: an agent
            with no client is not a working agent, and finding that out at
            construction beats finding out mid-generation.
    """
    available, reason = gateway_availability()
    if not available:
        raise GatewayCredentialsError(
            f"Cannot reach the LLM gateway: {reason}. Set LITELLM_API_KEY and "
            "LITELLM_BASE_URL in .env, or pass client= to inject your own."
        )

    from openai import OpenAI  # type: ignore

    return OpenAI(
        api_key=os.getenv("LITELLM_API_KEY"),
        base_url=os.getenv("LITELLM_BASE_URL"),
        timeout=timeout,
    )


class UpstreamResponseError(RuntimeError):
    """The gateway returned a success status carrying an error payload.

    OpenAI-compatible gateways do not always signal upstream failure with an
    HTTP error. OpenRouter, for instance, answers ``200`` with
    ``{"choices": null, "error": {...}}`` when the backing provider is
    saturated. The SDK sees a success and does not raise, so an agent doing
    ``response.choices[0]`` dereferences ``None`` and surfaces
    ``TypeError: 'NoneType' object is not subscriptable`` — an error naming
    neither the cause nor a remedy, and not recognisably retryable.

    **There is one of these, deliberately.** It previously existed twice, in
    :mod:`src.validation.orchestrator` and :mod:`src.study.llm_client`, whose
    own docstring said it was "worth consolidating once something else needs
    it". Something did: the question agents disagreed about which exception to
    raise for this condition, and because ``Orchestrator.transient_errors``
    holds the orchestrator's copy by identity, the agent that handled the case
    *correctly* was the one whose error was never retried, while the agent with
    the unguarded dereference was retried by accident (BUG-08/09 in the
    Sprint-4 QA report).

    Both modules now re-export this class, so retry classification follows from
    identity rather than from every agent remembering the same convention.
    """


def response_text(response: Any) -> str:
    """Return the reply body from a chat completion, or raise something legible.

    This is the guard that BUG-08 was about. Every agent needs it, and every
    agent had its own version or none at all.

    Args:
        response: What the OpenAI-compatible client returned.

    Returns:
        The reply text, stripped, with any surrounding code fence removed.

    Raises:
        UpstreamResponseError: If the gateway returned no usable choice, or an
            empty message. Always this type, so
            :func:`~src.validation.orchestrator._default_transient_errors`
            recognises it as retryable without any per-agent convention.
    """
    if response is None:
        raise UpstreamResponseError("LLM returned no response.")

    choices = getattr(response, "choices", None)
    if not choices:
        # Surface what the gateway said rather than letting choices[0] raise.
        detail = getattr(response, "error", None) or "no detail provided"
        raise UpstreamResponseError(f"LLM returned no choices ({detail}).")

    message = getattr(choices[0], "message", None)
    if message is None:
        raise UpstreamResponseError("LLM returned an empty message.")

    content = getattr(message, "content", None)
    if not content or not content.strip():
        # Some providers spend the whole budget on reasoning and return nothing
        # else, so the finish reason is the only clue to what happened.
        raise UpstreamResponseError(
            "LLM returned an empty response. Finish reason: "
            f"{getattr(choices[0], 'finish_reason', None)}"
        )

    # A reply cut off by the output ceiling is *complete-looking* JSON that
    # stops mid-object, so json.loads reports "invalid JSON" and sends you to
    # the prompt instead of to the one number responsible. Say which it is.
    if getattr(choices[0], "finish_reason", None) == "length":
        raise UpstreamResponseError(
            "The model's reply was cut off by the output limit, so the JSON is "
            "incomplete. Raise LLM_MAX_TOKENS, ask for fewer items, or use a "
            "model that does not emit reasoning tokens - they are charged "
            "against the same budget as the answer."
        )

    return strip_fences(content)


def strip_fences(text: str) -> str:
    """Remove a surrounding ``` block, if the model added one."""
    match = _FENCE.match(text)
    return match.group("body") if match else text.strip()


def chat_json(
    client: Any,
    model: str,
    prompt: str,
    *,
    temperature: float = 0.3,
    max_tokens: int | None = None,
) -> str:
    r"""Send ``prompt`` asking for JSON, and return the reply body.

    **Why JSON mode rather than trusting the prompt.** Every agent tells the
    model to return JSON and then calls ``json.loads``. That works until the
    subject matter contains backslashes. Explaining a physics chapter, the model
    writes LaTeX - ``$\vec{E}$``, ``\Delta V``, ``\lambda`` - and ``\v``,
    ``\D`` and ``\l`` are not valid JSON escapes, so a *syntactically
    complete* reply is rejected by the parser and surfaces to the learner as
    "The LLM returned invalid JSON".

    Measured on the Mentor page against the physics textbook: 3 of 8 identical
    requests failed that way. With the LaTeX forced into the prompt to make it
    deterministic, the difference is unambiguous:

    ==========================  =======  =========
    request                      valid    invalid
    ==========================  =======  =========
    plain                        0        8
    ``response_format`` json     8        0
    ==========================  =======  =========

    Forbidding LaTeX in the prompt was the alternative and is worse: the
    notation is genuinely useful in a physics explanation, and degrading the
    output to work around a serialisation bug is the wrong trade.

    Args:
        client: An OpenAI-compatible client.
        model: Model id.
        prompt: The fully rendered prompt.
        temperature: Sampling temperature.
        max_tokens: Output ceiling. Always worth sending - the gateway refuses
            on the *requested* ceiling, not on usage.

    Returns:
        The reply text, guarded and de-fenced by :func:`response_text`.

    Raises:
        UpstreamResponseError: If the gateway returned nothing usable, or the
            reply was cut off by the output limit.
    """
    request: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    if max_tokens is not None:
        request["max_tokens"] = max_tokens

    try:
        response = client.chat.completions.create(**request)
    except Exception as exc:
        # Not every model behind a LiteLLM proxy supports JSON mode, and a
        # rejected request is worse than an unescaped one - so retry without it.
        #
        # But only when the gateway rejected the *shape* of the request. A bare
        # `except Exception` also caught RateLimitError and APITimeoutError and
        # immediately fired a second identical call with no backoff: double the
        # load on a provider that just said it was saturated, and a second
        # timeout doubling the user's wait. 400 and 422 are the codes that mean
        # "this request is malformed for this model"; everything else - 401,
        # 429, 5xx, connection failures - propagates.
        if getattr(exc, "status_code", None) not in (400, 422):
            raise
        logger.info(
            "%s rejected response_format (HTTP %s); retrying without JSON mode",
            model,
            getattr(exc, "status_code", None),
        )
        request.pop("response_format")
        response = client.chat.completions.create(**request)

    return response_text(response)
