"""Generation history and the platform event log.

Two things live here:

* the **event vocabulary** — the ``*_STARTED`` / ``*_FAILED`` constants every
  other module logs through, kept in one place so the History page can filter on
  a closed set rather than on free-form strings, and
* the **read side** over :class:`~src.validation.store.PlatformStore`, assembling
  runs, outputs, reviews and events into the views the History page renders.

Writing events is the store's job (:meth:`PlatformStore.log_event`); this module
only names them and reads them back.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.validation.review_schema import (
    AgentRun,
    GeneratedOutput,
    Review,
    RunStatus,
    SystemEvent,
)
from src.validation.store import PlatformStore

# --------------------------------------------------------------------------- #
# Event vocabulary
# --------------------------------------------------------------------------- #

RUN_STARTED = "run_started"
RUN_COMPLETED = "run_completed"
RUN_FAILED = "run_failed"
VALIDATION_FAILED = "validation_failed"
REVIEW_ACTION = "review_action"
EXPORT_BLOCKED = "export_blocked"
EXPORT_COMPLETED = "export_completed"
BATCH_STARTED = "batch_started"
BATCH_COMPLETED = "batch_completed"

EVENT_TYPES: tuple[str, ...] = (
    RUN_STARTED,
    RUN_COMPLETED,
    RUN_FAILED,
    VALIDATION_FAILED,
    REVIEW_ACTION,
    EXPORT_BLOCKED,
    EXPORT_COMPLETED,
    BATCH_STARTED,
    BATCH_COMPLETED,
)


# --------------------------------------------------------------------------- #
# Views
# --------------------------------------------------------------------------- #


class RunDetail(BaseModel):
    """One agent run together with everything it produced."""

    run: AgentRun
    outputs: list[GeneratedOutput] = Field(default_factory=list)
    events: list[SystemEvent] = Field(default_factory=list)


class TimelineEntry(BaseModel):
    """One dated thing that happened to an output, for the merged timeline.

    Attributes:
        timestamp: When it happened.
        kind: ``"run"``, ``"review"`` or ``"event"`` — what produced the entry.
        summary: A one-line human-readable description.
        actor: The reviewer's name for review entries; the agent's for runs.
    """

    timestamp: datetime
    kind: str
    summary: str
    actor: str | None = None


class HistoryService:
    """Read-only queries over the platform's persisted history.

    Args:
        store: The store to read from.
    """

    def __init__(self, store: PlatformStore) -> None:
        self._store = store

    def list_runs(
        self,
        *,
        agent_name: str | None = None,
        status: RunStatus | None = None,
        limit: int | None = None,
    ) -> list[AgentRun]:
        """Return agent runs, newest first.

        Args:
            agent_name: Restrict to one agent.
            status: Restrict to successful or failed runs.
            limit: Maximum number of runs to return.

        Returns:
            Matching runs.
        """
        return self._store.list_agent_runs(
            agent_name=agent_name, status=status, limit=limit
        )

    def run_detail(self, run_id: str) -> RunDetail | None:
        """Return a run with its outputs and events, or ``None`` if unknown.

        Args:
            run_id: The run to describe.

        Returns:
            The assembled detail view.
        """
        run = self._store.get_agent_run(run_id)
        if run is None:
            return None
        return RunDetail(
            run=run,
            outputs=self._store.list_outputs(agent_run_id=run_id),
            events=self._store.list_events(run_id=run_id),
        )

    def output_timeline(self, output_id: str) -> list[TimelineEntry]:
        """Return everything that happened to one output, oldest first.

        Merges the generating run, every human review action and every system
        event into a single chronological story — the view that answers "why is
        this output in the state it is in?".

        Args:
            output_id: The output to trace.

        Returns:
            Timeline entries in ascending timestamp order; empty when the output
            does not exist.
        """
        output = self._store.get_output(output_id)
        if output is None:
            return []

        entries: list[TimelineEntry] = []

        run = self._store.get_agent_run(output.agent_run_id)
        if run is not None:
            entries.append(
                TimelineEntry(
                    timestamp=run.started_at,
                    kind="run",
                    summary=f"{run.agent_name} generated this output",
                    actor=run.agent_name,
                )
            )

        entries.extend(
            TimelineEntry(
                timestamp=review.timestamp,
                kind="review",
                summary=self._describe_review(review),
                actor=review.reviewer,
            )
            for review in self._store.list_reviews(output_id=output_id)
        )

        entries.extend(
            TimelineEntry(
                timestamp=event.timestamp,
                kind="event",
                summary=f"{event.event_type}: {event.message}",
            )
            for event in self._store.list_events(output_id=output_id)
        )

        return sorted(entries, key=lambda entry: entry.timestamp)

    @staticmethod
    def _describe_review(review: Review) -> str:
        """Render a review action as one readable line."""
        if review.previous_status == review.new_status:
            description = f"commented ({review.previous_status.value})"
        else:
            description = (
                f"{review.action.value}: "
                f"{review.previous_status.value} -> {review.new_status.value}"
            )
        if review.notes:
            description += f" - {review.notes}"
        return description

    def list_events(
        self,
        *,
        event_type: str | None = None,
        run_id: str | None = None,
        limit: int | None = None,
    ) -> list[SystemEvent]:
        """Return logged events, newest first.

        Args:
            event_type: Restrict to one of :data:`EVENT_TYPES`.
            run_id: Restrict to one run.
            limit: Maximum number of events to return.

        Returns:
            Matching events.
        """
        return self._store.list_events(
            event_type=event_type, run_id=run_id, limit=limit
        )
