"""Workflow orchestrator: run selected agents and record what happened.

This is the layer that turns "an agent produced some text" into the durable,
reviewable records the rest of the platform works from. For each invocation it
builds the prompt content from a :class:`~src.retrieval.models.GroundedContext`,
calls the agent, validates the response, and persists an
:class:`~src.validation.review_schema.AgentRun` plus a
:class:`~src.validation.review_schema.GeneratedOutput`.

Two decisions shape the module:

**Raw output is captured, not parsed output.** Agents' own ``generate()`` methods
raise ``ValueError`` on malformed JSON and discard the model's text, which would
make a malformed output impossible to flag — it would simply vanish. Adapters
therefore obtain the raw string and hand it to :class:`ValidatorBase`, which
never raises and records the failure instead. The bad text is stored under
``payload["raw_output"]`` so a reviewer can see exactly what the model said.

**Failures are recorded, never raised.** A dead upstream, a timeout or missing
grounding produces an ``AgentRun`` with ``status=failure`` and the error text, so
it appears in History rather than aborting a batch. Transient errors are retried
with backoff first.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel

from src.llm_gateway import UpstreamResponseError
from src.retrieval.models import GroundedContext, InsufficientGroundingError
from src.validation.guardrails import GuardrailContext
from src.validation.history import (
    RUN_COMPLETED,
    RUN_FAILED,
    RUN_STARTED,
    VALIDATION_FAILED,
)
from src.validation.review_schema import AgentRun, GeneratedOutput, RunStatus
from src.validation.store import PlatformStore
from src.validation.validator_base import (
    ValidationResult,
    ValidatorBase,
    build_generated_output,
)

logger = logging.getLogger(__name__)


def _default_transient_errors() -> tuple[type[BaseException], ...]:
    """Return the upstream error types worth retrying.

    Connection failures, timeouts, rate limits, 5xx responses and error-shaped
    success responses are transient; everything else (a bad request, an auth
    failure) will fail again identically and is not retried. Falls back to the
    gateway-specific case alone when the OpenAI client is not installed, which
    makes SDK-level retry a no-op rather than an import error.
    """
    try:
        from openai import (
            APIConnectionError,
            APITimeoutError,
            InternalServerError,
            RateLimitError,
        )
    except ImportError:  # pragma: no cover - openai is a declared dependency
        return (UpstreamResponseError,)
    return (
        APIConnectionError,
        APITimeoutError,
        InternalServerError,
        RateLimitError,
        UpstreamResponseError,
    )


@runtime_checkable
class AgentSpec(Protocol):
    """What the orchestrator needs from an agent.

    Deliberately minimal so any generator can participate: the four agents in
    :mod:`src.agents.registry` today, the study agents later, or a stub in a
    test. Implementations are registered by name; nothing in the orchestrator
    knows about any specific agent.

    Attributes:
        name: The agent's registry name, recorded on every run.
        schema: The Pydantic model its output must satisfy.
        model: Identifier of the underlying model, for the run record.
    """

    name: str
    schema: type[BaseModel]
    model: str | None

    def run_raw(self, content: str, **params: Any) -> str:
        """Generate and return the model's **raw**, unparsed response."""
        ...


class RegistryAgentAdapter:
    """Adapts one agent from :mod:`src.agents.registry` to :class:`AgentSpec`.

    Args:
        name: Registry name (``mentor``, ``concept``, ...).
        agent: The agent instance.
        schema: The agent's declared output schema.
        default_params: Generation arguments to use when the caller supplies
            none, since the agents differ in what they require.
    """

    def __init__(
        self,
        name: str,
        agent: Any,
        schema: type[BaseModel],
        default_params: Mapping[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.schema = schema
        self.model = getattr(agent, "model", None)
        self.default_params: dict[str, Any] = dict(default_params or {})
        self._agent = agent

    def run_raw(self, content: str, **params: Any) -> str:
        """Return the agent's raw response text.

        Agents are driven through their prompt-building and LLM-calling
        internals rather than ``generate()``, because ``generate()`` validates
        internally and raises on malformed JSON — destroying the very text the
        reviewer needs to see.

        Args:
            content: The grounded ``{content}`` block for the prompt.
            **params: Agent-specific generation arguments.

        Returns:
            The unparsed response text.
        """
        call_params = {**self.default_params, **params}

        prompt = self._agent._build_prompt(content=content, **call_params)
        try:
            return self._agent._call_llm(prompt)
        except TypeError as exc:
            # A shim for an agent that indexes response.choices[0] unguarded.
            # Every agent in this repo now uses src.llm_gateway.response_text,
            # which raises UpstreamResponseError directly, so this fires for
            # none of them - but AgentSpec is an open protocol and a third-party
            # agent can still get here.
            #
            # Deliberately NOT widened to ValueError. That would make a
            # deterministic bug after the gateway call - a bad int(), a failed
            # parse - look like a saturated provider and be retried three times,
            # each one a real billed call, while the run record asserted a
            # diagnosis that was never true. BUG-09 is fixed by there being one
            # UpstreamResponseError, not by classifying more types as transient.
            #
            # Note the scope: this try wraps the gateway call only.
            # _build_prompt is deliberately outside it, so a control-validation
            # ValueError from there cannot be misread as an upstream failure.
            raise UpstreamResponseError(
                "The gateway returned a response without choices, which usually "
                "means an error payload delivered with a success status "
                "(provider saturated or rate limited). "
                f"Original error: {exc}"
            ) from exc


# Generation arguments each agent needs when the caller does not specify any.
DEFAULT_AGENT_PARAMS: dict[str, dict[str, Any]] = {
    "mentor": {"user_question": "Explain this material.", "difficulty": "beginner"},
    "concept": {"user_question": "Explain this material.", "difficulty": "beginner"},
    "question_bank": {
        "question_type": "mcq",
        "difficulty": "beginner",
        "num_questions": 2,
    },
    "test_help": {
        "question_type": "mcq",
        "difficulty": "beginner",
        "num_questions": 2,
    },
}


def build_default_agents(*, client: Any | None = None) -> dict[str, AgentSpec]:
    """Build adapters for every agent in the shared registry.

    Args:
        client: An OpenAI-compatible client shared by every agent. Defaults to
            one built from the configured gateway; tests inject a double.

    Returns:
        Adapters keyed by registry name.
    """
    from src.agents.registry import AgentRegistry

    registry = AgentRegistry(client=client)
    return {
        name: RegistryAgentAdapter(
            name=name,
            agent=registry.get_agent(name),
            schema=registry.get_schema(name),
            default_params=DEFAULT_AGENT_PARAMS.get(name),
        )
        for name in registry.list_agents()
    }


@dataclass
class RunResult:
    """Everything one orchestrated invocation produced.

    Attributes:
        run: The persisted run record, successful or failed.
        output: The persisted output, or ``None`` when the agent never answered.
        validation: The validator's verdict, or ``None`` on agent failure.
        grounded_context: The retrieval payload the agent was given, if any.
        error: The failure text when the agent could not be run at all.
    """

    run: AgentRun
    output: GeneratedOutput | None = None
    validation: ValidationResult | None = None
    grounded_context: GroundedContext | None = None
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        """Whether the agent produced an output at all (valid or not)."""
        return self.output is not None


@dataclass
class Orchestrator:
    """Runs selected agents and records runs, outputs and events.

    Args:
        store: Where runs, outputs and events are persisted.
        agents: Agents available to run, keyed by name. Defaults to the shared
            registry's four agents.
        validator: Validator to judge outputs with; a default is built if
            omitted.
        max_retries: Extra attempts after a transient upstream failure.
        retry_backoff: Seconds to wait before the first retry, doubling
            thereafter.
        transient_errors: Error types considered worth retrying.
    """

    store: PlatformStore
    agents: dict[str, AgentSpec] | None = None
    validator: ValidatorBase = field(default_factory=ValidatorBase)
    max_retries: int = 2
    retry_backoff: float = 1.0
    transient_errors: tuple[type[BaseException], ...] = field(
        default_factory=_default_transient_errors
    )

    def __post_init__(self) -> None:
        # `None` means "not supplied"; an empty dict means "deliberately no
        # agents". These used to be the same thing, because the check was
        # falsiness, so asking for an empty registry silently built the full
        # one. That was invisible while the default agents were free to
        # construct in mock mode - now they need credentials.
        if self.agents is None:
            self.agents = build_default_agents()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def run_agent(
        self,
        agent_name: str,
        *,
        content: str | None = None,
        grounded_context: GroundedContext | None = None,
        params: Mapping[str, Any] | None = None,
        guardrail_context: GuardrailContext | None = None,
    ) -> RunResult:
        """Run one agent and persist everything it produced.

        Supply either ``grounded_context`` (the real pipeline) or ``content``
        (ad-hoc generation). With a grounded context the run also records the
        chunk ids behind the answer, and validation gains the hallucinated-
        citation check.

        Args:
            agent_name: Which registered agent to run.
            content: Raw prompt content, when not running grounded.
            grounded_context: The retrieval payload to ground the agent in.
            params: Agent-specific generation arguments.
            guardrail_context: Guardrail configuration; the grounded context is
                attached to it automatically.

        Returns:
            The :class:`RunResult`. Agent failures are reported through
            ``result.error``, never raised.

        Raises:
            KeyError: If ``agent_name`` is not registered.
            ValueError: If neither ``content`` nor ``grounded_context`` is given,
                so the agent would be invoked with nothing to work from.
        """
        agent = self._get_agent(agent_name)
        run = AgentRun(agent_name=agent_name, model=agent.model)

        try:
            prompt_content = self._resolve_content(content, grounded_context)
        except InsufficientGroundingError as exc:
            # Recorded rather than raised: an unanswerable query is a fact about
            # the run, and the History page should show it.
            self.store.save_agent_run(run)
            return self._fail(run, str(exc))

        run.input_context = prompt_content
        if grounded_context is not None:
            run.source_chunk_ids = grounded_context.chunk_ids

        self.store.save_agent_run(run)
        self.store.log_event(RUN_STARTED, f"{agent_name} run started", run_id=run.id)

        try:
            raw_output = self._invoke_with_retry(
                agent, prompt_content, dict(params or {})
            )
        except Exception as exc:  # noqa: BLE001 - every failure is recorded
            return self._fail(run, f"{type(exc).__name__}: {exc}")

        result, model = self.validator.validate(
            raw_output,
            agent.schema,
            context=self._guardrail_context(guardrail_context, grounded_context),
        )
        output = self._persist_output(run, agent, result, model, raw_output)

        run.status = RunStatus.SUCCESS
        run.finished_at = _now()
        self.store.save_agent_run(run)
        self.store.log_event(
            RUN_COMPLETED,
            f"{agent_name} run completed (validation "
            f"{'passed' if result.passed else 'failed'})",
            run_id=run.id,
            output_id=output.id,
        )

        return RunResult(
            run=run,
            output=output,
            validation=result,
            grounded_context=grounded_context,
        )

    def run_agents(
        self,
        agent_names: Iterable[str],
        *,
        content: str | None = None,
        grounded_context: GroundedContext | None = None,
        params: Mapping[str, Mapping[str, Any]] | None = None,
        guardrail_context: GuardrailContext | None = None,
    ) -> list[RunResult]:
        """Run several agents over the same content, in order.

        One agent's failure never stops the others — each is independent and
        each records its own outcome.

        Args:
            agent_names: The agents to run.
            content: Raw prompt content, when not running grounded.
            grounded_context: The retrieval payload to ground the agents in.
            params: Per-agent generation arguments, keyed by agent name.
            guardrail_context: Guardrail configuration shared by every run.

        Returns:
            One :class:`RunResult` per requested agent, in request order.
        """
        per_agent = params or {}
        return [
            self.run_agent(
                name,
                content=content,
                grounded_context=grounded_context,
                params=per_agent.get(name),
                guardrail_context=guardrail_context,
            )
            for name in agent_names
        ]

    @property
    def agent_names(self) -> list[str]:
        """Names of every registered agent."""
        return list(self.agents)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _get_agent(self, agent_name: str) -> AgentSpec:
        """Look up a registered agent or fail loudly."""
        try:
            return self.agents[agent_name]
        except KeyError:
            available = ", ".join(sorted(self.agents)) or "none"
            raise KeyError(
                f"Unknown agent {agent_name!r}. Registered agents: {available}."
            ) from None

    @staticmethod
    def _resolve_content(
        content: str | None, grounded_context: GroundedContext | None
    ) -> str:
        """Return the prompt content, preferring the grounded payload."""
        if grounded_context is not None:
            return grounded_context.as_prompt_content()
        if content is None:
            raise ValueError(
                "run_agent requires either content or grounded_context; "
                "an agent must never be invoked with nothing to work from."
            )
        return content

    @staticmethod
    def _guardrail_context(
        supplied: GuardrailContext | None, grounded_context: GroundedContext | None
    ) -> GuardrailContext:
        """Attach the grounded context so the citation check can run."""
        base = supplied or GuardrailContext()
        if grounded_context is None:
            return base
        return base.model_copy(update={"grounded_context": grounded_context})

    def _invoke_with_retry(
        self, agent: AgentSpec, content: str, params: dict[str, Any]
    ) -> str:
        """Call the agent, retrying transient upstream failures with backoff."""
        delay = self.retry_backoff
        last_error: BaseException | None = None

        for attempt in range(self.max_retries + 1):
            try:
                return agent.run_raw(content, **params)
            except self.transient_errors as exc:
                last_error = exc
                if attempt == self.max_retries:
                    break
                logger.warning(
                    "transient failure from %s (attempt %d/%d): %s",
                    agent.name,
                    attempt + 1,
                    self.max_retries + 1,
                    exc,
                )
                if delay:
                    time.sleep(delay)
                    delay *= 2

        assert last_error is not None  # only reachable after a transient failure
        raise last_error

    def _persist_output(
        self,
        run: AgentRun,
        agent: AgentSpec,
        result: ValidationResult,
        model: BaseModel | None,
        raw_output: str,
    ) -> GeneratedOutput:
        """Store the output, keeping unparseable text visible to the reviewer."""
        payload: dict[str, Any] = (
            model.model_dump(mode="json")
            if model is not None
            else {"raw_output": raw_output}
        )
        output = build_generated_output(
            agent_run_id=run.id,
            output_type=agent.name,
            output_schema=agent.schema,
            payload=payload,
            result=result,
        )
        self.store.save_output(output)

        if not result.passed:
            self.store.log_event(
                VALIDATION_FAILED,
                f"{agent.name} output failed validation",
                run_id=run.id,
                output_id=output.id,
                details=result.model_dump(mode="json"),
            )
        return output

    def _fail(self, run: AgentRun, error: str) -> RunResult:
        """Record a run that never produced an output."""
        run.status = RunStatus.FAILURE
        run.error = error
        run.finished_at = _now()
        self.store.save_agent_run(run)
        self.store.log_event(
            RUN_FAILED, f"{run.agent_name} run failed: {error}", run_id=run.id
        )
        logger.warning("run failed: agent=%s error=%s", run.agent_name, error)
        return RunResult(run=run, error=error)


def _now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)
