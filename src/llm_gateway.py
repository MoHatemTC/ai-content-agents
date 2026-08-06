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

import os
from typing import Any

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
