"""One way to put an agent's output in front of a human.

Seven agents across two lanes are supposed to queue their output for review, and
until recently none of them did. The content lane (mentor, concept) built an
``AgentRun`` and a ``GeneratedOutput`` and dropped both. The study lane
(flashcards, study plan, revision) never built either: each agent set
``needs_human_review=True``, stamped a run id, and told the *caller* - in its
docstring - to route the result through ``review_schema``. No caller ever did.

Both lanes printed "pending review" while the reviewer's queue stayed empty.

The fix is one function rather than a base class, because the two lanes have
nothing else in common: the study agents take goals and date ranges, the content
agents take a question and a difficulty, and forcing them under one parent would
mean a constructor that fits neither. What they do share is exactly this - the
order in which a run is opened, a generation attempted, a failure recorded, and
an output validated and queued.

Recording the failure matters as much as recording the success. A run that
raises is a fact about the run: without it, History shows the run hanging in
SUCCESS forever and a reviewer has no way to tell a bad generation from one that
never happened.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from src.validation.review_schema import AgentRun, GeneratedOutput, RunStatus
from src.validation.validator_base import ValidatorBase, build_generated_output


def persist_reviewable_run(
    *,
    store: Any | None = None,
    agent_name: str,
    output_type: str,
    output_schema: type[BaseModel],
    model: str | None,
    input_context: str | None,
    source_chunk_ids: list[str] | None = None,
    generate: Callable[[], BaseModel],
    collect_report: Callable[[], dict[str, Any]] | None = None,
) -> GeneratedOutput:
    """Run ``generate`` inside a recorded, reviewable agent run.

    Args:
        store: Where to persist. Defaults to the shared
            :class:`~src.validation.store.PlatformStore`; tests inject one.
        agent_name: Recorded on the run, and what the History page groups by.
        output_type: Kind of artifact - ``flashcard_set``, ``study_plan``, ...
        output_schema: Schema the payload is validated against.
        model: Model id, for the audit record.
        input_context: What the model actually saw. Must be the *resolved*
            prompt content, not an argument that was discarded in favour of a
            retrieved context - otherwise the record asserts an input that was
            never used.
        source_chunk_ids: Provenance, when the caller has it.
        generate: The generation itself, already bound to its arguments. Called
            exactly once.
        collect_report: Called after a successful generation; whatever it
            returns is merged into ``validation_report``. A callable rather than
            a dict because the things worth reporting - grounding warnings, for
            one - are only known once the agent has run.

    Returns:
        The persisted :class:`GeneratedOutput`, pending review.

    Raises:
        Whatever ``generate`` raises, after recording the failed run.
    """
    if store is None:
        from src.validation.store import PlatformStore

        store = PlatformStore()

    agent_run = AgentRun(
        agent_name=agent_name,
        input_context=input_context,
        source_chunk_ids=list(source_chunk_ids or []),
        model=model,
    )
    store.save_agent_run(agent_run)

    try:
        generated = generate()
    except Exception as error:
        agent_run.status = RunStatus.FAILURE
        agent_run.error = str(error)
        agent_run.finished_at = datetime.now(timezone.utc)
        store.save_agent_run(agent_run)
        raise

    agent_run.finished_at = datetime.now(timezone.utc)
    store.save_agent_run(agent_run)

    payload = generated.model_dump()
    validation_result, validated_output = ValidatorBase().validate(
        payload, output_schema
    )

    output = build_generated_output(
        agent_run_id=agent_run.id,
        output_type=output_type,
        output_schema=output_schema,
        payload=(
            validated_output.model_dump() if validated_output is not None else payload
        ),
        result=validation_result,
    )
    extra = collect_report() if collect_report is not None else None
    if extra:
        # Surfaced to the reviewer, who can judge what a heuristic cannot. The
        # output is still queued - it is flagged, not rejected.
        report = dict(output.validation_report or {})
        report.update(extra)
        output.validation_report = report

    store.save_output(output)
    return output
