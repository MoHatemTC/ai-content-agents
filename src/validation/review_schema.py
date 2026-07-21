"""Shared review contract for the Content Agents quality & trust layer.

This module defines the data contract every agent output flows through before it
can reach a user or be exported:

* the output status lifecycle (``pending`` -> ``edited`` -> ``approved``),
* the ``AgentRun`` / ``GeneratedOutput`` / ``Review`` domain models,
* the pure review-action logic (:func:`apply_review`) that produces an immutable
  ``Review`` record and advances an output's status, and
* the human-review **export gate** (:func:`assert_exportable`) that blocks any
  output that has not been explicitly approved by a human.

Persistence is intentionally **out of scope** here: the models are plain Pydantic
objects and the review logic never touches a database. A teammate's persistence
lane stores these records; a DB-backed store simply needs to save the models and
the ``Review`` rows this module produces (see ``docs/validation-lane.md``).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


def _now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def _new_id() -> str:
    """Return a fresh unique identifier as a string."""
    return str(uuid4())


class OutputStatus(str, Enum):
    """Lifecycle state of a generated output.

    ``approved`` is terminal for Sprint 1 — there is no re-open path and no
    further approve/edit action. Status-neutral audit comments may still be
    appended to an approved output's review history.
    """

    PENDING = "pending"
    EDITED = "edited"
    APPROVED = "approved"


class RunStatus(str, Enum):
    """Outcome of a single agent invocation (run-level, not output-level)."""

    SUCCESS = "success"
    FAILURE = "failure"


class ReviewAction(str, Enum):
    """A human review action recorded against an output."""

    APPROVE = "approve"
    EDIT = "edit"
    COMMENT = "comment"


# Legal status *changes* (same-status "no-op" actions such as COMMENT are handled
# in apply_review and do not go through this table).
_LEGAL_TRANSITIONS: dict[OutputStatus, set[OutputStatus]] = {
    OutputStatus.PENDING: {OutputStatus.EDITED, OutputStatus.APPROVED},
    OutputStatus.EDITED: {OutputStatus.APPROVED},
    OutputStatus.APPROVED: set(),
}


def is_legal_transition(old: OutputStatus, new: OutputStatus) -> bool:
    """Return whether changing an output's status from ``old`` to ``new`` is allowed.

    Only genuine status changes are considered. ``pending -> edited``,
    ``pending -> approved`` and ``edited -> approved`` are legal; anything out of
    ``approved`` (re-open) and any backward move is illegal.
    """
    return new in _LEGAL_TRANSITIONS.get(old, set())


class IllegalTransitionError(ValueError):
    """Raised when a review action would move an output through an illegal transition."""

    def __init__(self, old: OutputStatus, new: OutputStatus) -> None:
        self.old = old
        self.new = new
        super().__init__(f"Illegal status transition: {old.value!r} -> {new.value!r}.")


class ExportBlockedError(RuntimeError):
    """Raised by the review gate when a non-approved output is asked to be exported."""

    def __init__(self, output_id: str, status: OutputStatus) -> None:
        self.output_id = output_id
        self.status = status
        super().__init__(
            f"Output {output_id!r} is not exportable "
            f"(status={status.value!r}; requires {OutputStatus.APPROVED.value!r})."
        )


class AgentRun(BaseModel):
    """One record per agent invocation.

    Provenance to the retrieval layer is carried via ``source_chunk_ids``;
    ``agent_name`` refers to the shared agent registry (a plain string while the
    registry is not yet DB-backed).
    """

    id: str = Field(default_factory=_new_id)
    agent_name: str
    input_context: str | None = None
    source_chunk_ids: list[str] = Field(default_factory=list)
    prompt_ref: str | None = None
    model: str | None = None
    started_at: datetime = Field(default_factory=_now)
    finished_at: datetime | None = None
    status: RunStatus = RunStatus.SUCCESS
    error: str | None = None


class GeneratedOutput(BaseModel):
    """One record per produced artifact, carrying its validation verdict and status.

    ``payload`` is the validated JSON output; ``validation_report`` is the
    structured result from the validator (see :mod:`src.validation.validator_base`).
    New outputs default to :attr:`OutputStatus.PENDING` — nothing is trusted until
    a human approves it.
    """

    id: str = Field(default_factory=_new_id)
    agent_run_id: str
    output_type: str
    payload: dict[str, Any]
    schema_name: str
    validation_passed: bool = False
    validation_report: dict[str, Any] = Field(default_factory=dict)
    status: OutputStatus = OutputStatus.PENDING
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class Review(BaseModel):
    """An immutable, append-only record of a single human review action.

    Review rows are never mutated or deleted: the full history of an output is
    reconstructable by reading its ``Review`` records in timestamp order, while the
    output's *current* status lives on :class:`GeneratedOutput`.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=_new_id)
    output_id: str
    reviewer: str
    action: ReviewAction
    previous_status: OutputStatus
    new_status: OutputStatus
    edited_payload: dict[str, Any] | None = None
    notes: str | None = None
    timestamp: datetime = Field(default_factory=_now)


def apply_review(
    output: GeneratedOutput,
    reviewer: str,
    action: ReviewAction,
    *,
    edited_payload: dict[str, Any] | None = None,
    notes: str | None = None,
) -> Review:
    """Apply a human review action to ``output`` and return the ``Review`` record.

    This is pure domain logic with no persistence: it validates the transition,
    updates ``output.status`` / ``output.updated_at`` in place (and ``output.payload``
    on an edit), and returns an immutable :class:`Review` for the caller to store.

    Args:
        output: The output being reviewed. Mutated in place on success.
        reviewer: Identity of the human reviewer.
        action: The review action being taken.
        edited_payload: Replacement payload; required when ``action`` is
            :attr:`ReviewAction.EDIT`, ignored otherwise.
        notes: Optional free-text reviewer notes.

    Returns:
        The immutable :class:`Review` record describing this action.

    Raises:
        IllegalTransitionError: If the action is not permitted from the output's
            current status. ``approved`` is terminal: approve/edit actions on an
            already-approved output are rejected, while status-neutral
            :attr:`ReviewAction.COMMENT` actions remain allowed for the audit trail.
        ValueError: If ``action`` is :attr:`ReviewAction.EDIT` without an
            ``edited_payload``.
    """
    previous = output.status

    if previous == OutputStatus.APPROVED and action is not ReviewAction.COMMENT:
        # Approved is terminal for status changes; only audit comments may still
        # be appended.
        raise IllegalTransitionError(previous, previous)

    if action is ReviewAction.APPROVE:
        new_status = OutputStatus.APPROVED
    elif action is ReviewAction.EDIT:
        if edited_payload is None:
            raise ValueError("An 'edit' review action requires an edited_payload.")
        new_status = OutputStatus.EDITED
    else:  # COMMENT — status is unchanged.
        new_status = previous

    if new_status != previous and not is_legal_transition(previous, new_status):
        raise IllegalTransitionError(previous, new_status)

    review = Review(
        output_id=output.id,
        reviewer=reviewer,
        action=action,
        previous_status=previous,
        new_status=new_status,
        edited_payload=edited_payload if action is ReviewAction.EDIT else None,
        notes=notes,
    )

    output.status = new_status
    output.updated_at = _now()
    if action is ReviewAction.EDIT and edited_payload is not None:
        output.payload = edited_payload

    logger.info(
        "review applied: output_id=%s reviewer=%s action=%s %s -> %s",
        output.id,
        reviewer,
        action.value,
        previous.value,
        new_status.value,
    )
    return review


def assert_exportable(output: GeneratedOutput) -> None:
    """Enforce the human-review gate: raise unless ``output`` is approved.

    Every export path — single or bulk — must call this before releasing an
    output. There is no bypass: a ``pending`` or ``edited`` output cannot be
    exported.

    Raises:
        ExportBlockedError: If ``output.status`` is not :attr:`OutputStatus.APPROVED`.
    """
    if output.status != OutputStatus.APPROVED:
        logger.warning(
            "blocked export attempt: output_id=%s status=%s",
            output.id,
            output.status.value,
        )
        raise ExportBlockedError(output.id, output.status)
