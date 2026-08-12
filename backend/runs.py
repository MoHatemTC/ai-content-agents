"""Run recording and grounding-refusal adaptation for the HTTP agent paths.

``src.validation.orchestrator`` records a run *before* invoking the agent and
funnels every failure through ``_fail``, so an unanswerable query or a saturated
gateway lands in History rather than vanishing. The FastAPI services grew up
alongside it and saved their ``AgentRun`` only after a success, which meant a
failed generation left no trace at all — the guarantee
``docs/agent-parity.md`` records as "failed run recorded, not lost" held on the
orchestrator path and nowhere else.

This module is the shared piece that closes that gap. :func:`recorded_run`
mirrors the orchestrator's shape for callers that invoke agents directly, and
:func:`generate_or_422` (moved here from ``backend.chat.service``, which had
the only copy) turns a grounding refusal into a 422 that names the problem.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from backend.errors import ApiError
from src.retrieval.grounding import CitationGroundingError
from src.validation.history import RUN_COMPLETED, RUN_FAILED, RUN_STARTED
from src.validation.review_schema import AgentRun, RunStatus
from src.validation.store import PlatformStore

logger = logging.getLogger(__name__)


@contextmanager
def recorded_run(
    store: PlatformStore,
    *,
    agent_name: str,
    input_context: str,
    model: str,
) -> Iterator[AgentRun]:
    """Record an agent run for its whole lifetime, success or failure.

    The run is persisted *before* the body runs, so a failure inside it still
    leaves a row behind. On the way out the status is set and the run saved
    again, with the matching history event — the same sequence
    :meth:`src.validation.orchestrator.AgentOrchestrator.run` performs.

    Args:
        store: Where runs and events are persisted.
        agent_name: Registered agent name, e.g. ``"question_bank_agent"``.
        input_context: What the run was asked to work from.
        model: The gateway model id the run was dispatched to.

    Yields:
        The live :class:`AgentRun`, so the body can attach
        ``source_chunk_ids`` once retrieval has happened.

    Raises:
        Exception: Whatever the body raised, re-raised after recording. The
            caller still decides the HTTP status; recording is not swallowing.
    """
    run = AgentRun(agent_name=agent_name, input_context=input_context, model=model)
    store.save_agent_run(run)
    store.log_event(RUN_STARTED, f"{agent_name} run started", run_id=run.id)

    try:
        yield run
    except Exception as exc:  # noqa: BLE001 - every failure is recorded, then re-raised
        error = f"{type(exc).__name__}: {exc}"
        run.status = RunStatus.FAILURE
        run.error = error
        run.finished_at = datetime.now(timezone.utc)
        store.save_agent_run(run)
        store.log_event(
            RUN_FAILED, f"{agent_name} run failed: {error}", run_id=run.id
        )
        logger.warning("run failed: agent=%s error=%s", agent_name, error)
        raise

    run.mark_finished()
    store.save_agent_run(run)
    store.log_event(RUN_COMPLETED, f"{agent_name} run completed", run_id=run.id)


def generate_or_422(agent: Any, **kwargs: Any) -> Any:
    """Call an agent, turning its refusals into responses that name the cause.

    PREVIEW ADAPTATION. These call sites passed ``strict=False``, which existed
    on the separate MentorAgent and ConceptAgent this branch was written
    against. PR #39 merged those into one ExplanationAgentBase and dropped the
    flag, because it split the checks by kind instead: the fuzzy support
    heuristic became advisory for every caller - which is most of what
    strict=False bought - while the exact checks still refuse. So the toggle is
    gone rather than renamed.

    What still raises is an invented citation, or a reply that cites nothing.
    Neither a chat answer nor a question set is a good reason to relax either,
    so the call is adapted rather than the guarantee. A 422 naming the problem
    beats the 500 the catch-all handler would otherwise return.

    **Two outcomes, because there are two problems.** The agents raise
    ``ValueError`` for a grounding refusal *and* for a reply that could not be
    parsed or did not fit the schema. Mapping both to ``ungrounded_reply`` told
    a learner their question "could not be grounded in this workspace" when the
    model had really returned LaTeX that broke the JSON parser - the wrong
    cause, pointing at the wrong fix. A refusal is 422 and about the content; a
    reply that never became an object is 502 and about the provider.
    """
    try:
        return agent.generate(**kwargs)
    except CitationGroundingError as exc:
        raise ApiError(
            status_code=422,
            code="ungrounded_reply",
            message=f"The model's reply could not be grounded in this workspace: {exc}",
        ) from exc
    except ValueError as exc:
        raise ApiError(
            status_code=502,
            code="invalid_model_reply",
            message=f"The model returned a reply this app could not read: {exc}",
        ) from exc
