"""A deepeval judge that speaks to this project's own LiteLLM gateway.

deepeval defaults to OpenAI and an ``OPENAI_API_KEY``. This project already has
a configured gateway behind :mod:`src.llm_gateway`, and introducing a second
credential to run tests would be a poor trade - so the judge reuses
``build_client()``.

Importing this module requires ``pip install -e ".[eval]"``. It lives under
``tests/support/`` rather than ``src/evaluation/`` on purpose: that package
eagerly imports its submodules and is documented as *deterministic*, so putting
a non-deterministic LLM judge there would make an optional dependency
effectively mandatory for anything importing ``src.evaluation``.

Three things about ``DeepEvalBaseLLM`` that are easy to get wrong, all verified
against 4.1.5:

* ``__init__`` calls ``load_model()`` with no arguments, so any state it needs
  must be assigned *before* ``super().__init__()``.
* ``generate_with_schema`` is ``try: generate(..., schema=...) except TypeError:
  pass`` followed by a schema-less retry. A ``TypeError`` raised by our own code
  would therefore be swallowed and silently downgraded to an unschema'd call,
  so nothing here may raise one.
* ``generate_with_schema_and_extract`` checks ``isinstance(result, schema)``
  before falling back to its own JSON salvaging. Returning a *validated schema
  instance* skips deepeval's parser entirely and avoids its
  "Evaluation LLM outputted an invalid JSON" failure mode.
"""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any

# deepeval's telemetry is ON unless opted out, and it imports posthog and
# sentry-sdk to do it. Set here rather than documented, because a test suite
# should not phone home because someone did not read a README.
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "1")
os.environ.setdefault("ERROR_REPORTING", "0")

from deepeval.models.base_model import DeepEvalBaseLLM  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from src.llm_gateway import build_client, default_model  # noqa: E402

# The judge is asked for structured verdicts; models fence them anyway.
_FENCE = re.compile(r"^\s*```(?:json)?\s*(?P<body>.*?)\s*```\s*$", re.DOTALL)

# The scoring model, independent of the model under test. Judging with the same
# lite model that generated the output is a weak check, so this can be pointed
# somewhere stronger without touching DEFAULT_MODEL, which the agents use.
JUDGE_MODEL_ENV = "DEEPEVAL_JUDGE_MODEL"


def judge_model() -> str:
    """The model id used for scoring, read at call time."""
    return os.getenv(JUDGE_MODEL_ENV, "").strip() or default_model()


class LiteLLMJudge(DeepEvalBaseLLM):
    """Scores deepeval metrics through the project's configured gateway.

    Args:
        client: An OpenAI-compatible client. Defaults to the project gateway.
        model: Judge model id. Defaults to :func:`judge_model`.
    """

    def __init__(self, *, client: Any | None = None, model: str | None = None) -> None:
        # super().__init__() calls load_model() with no arguments, so both of
        # these have to exist first.
        self._client = client if client is not None else build_client()
        self._model_id = model or judge_model()
        super().__init__(model=self._model_id)

    def load_model(self) -> Any:
        return self._client

    def get_model_name(self) -> str:
        return f"LiteLLM/{self._model_id}"

    def generate(self, prompt: str, schema: type[BaseModel] | None = None) -> Any:
        """Send one scoring prompt.

        Returns a validated ``schema`` instance when one is requested and the
        reply parses, otherwise the raw text for deepeval to salvage.

        Raises:
            RuntimeError: If the gateway returns no usable choice. Deliberately
                not ``TypeError`` - see the module docstring.
        """
        request: dict[str, Any] = {
            "model": self._model_id,
            "messages": [{"role": "user", "content": prompt}],
            # Judge determinism, as far as sampling can provide it.
            "temperature": 0.0,
        }
        if schema is not None:
            request["response_format"] = {"type": "json_object"}

        try:
            response = self._client.chat.completions.create(**request)
        except Exception:
            # Not every model behind a LiteLLM proxy honours response_format.
            # Retry without it rather than failing the whole metric.
            if schema is None:
                raise
            request.pop("response_format")
            response = self._client.chat.completions.create(**request)

        # The bug this whole QA pass is about (BUG-08) is not repeated here.
        if not getattr(response, "choices", None):
            detail = getattr(response, "error", None) or "no detail provided"
            raise RuntimeError(f"Judge gateway returned no choices ({detail}).")

        text = (response.choices[0].message.content or "").strip()
        fenced = _FENCE.match(text)
        if fenced:
            text = fenced.group("body")

        if schema is None:
            return text
        try:
            return schema.model_validate_json(text)
        except Exception:
            # Hand deepeval the text and let its own salvaging try.
            return text

    async def a_generate(
        self, prompt: str, schema: type[BaseModel] | None = None
    ) -> Any:
        """Async entry point.

        Re-enters the synchronous path on a worker thread. Because this gives
        no real concurrency, construct every metric with ``async_mode=False``:
        serial runs are ordered and debuggable, which is what a report needs.
        """
        return await asyncio.to_thread(self.generate, prompt, schema)
