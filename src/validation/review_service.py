"""Human review service: the queue, the four actions, the audit trail.

This is the backend the Streamlit Review page drives. It sits between the pure
review logic in :mod:`src.validation.review_schema` — which decides whether an
action is legal and produces the immutable ``Review`` record — and
:class:`~src.validation.store.PlatformStore`, which makes both durable.

Each action follows the same shape: load the output, apply the pure logic, then
persist the mutated output and append the review row. Because
:func:`~src.validation.review_schema.apply_review` raises *before* mutating
anything when a transition is illegal, a refused action leaves no trace — no
status change and no orphaned review row.

Editing additionally **re-validates**. A reviewer rewriting a payload could
otherwise leave a stale "passed" verdict attached to content that no longer
satisfies its schema, or quietly introduce a citation that was never retrieved.
Re-validation reuses the generating run's ``source_chunk_ids`` as the grounding
evidence, so the hallucination check still applies long after the run itself.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from src.retrieval.models import GroundedContext
from src.validation.guardrails import GuardrailContext
from src.validation.history import REVIEW_ACTION
from src.validation.review_schema import (
    GeneratedOutput,
    OutputStatus,
    Review,
    ReviewAction,
    apply_review,
)
from src.validation.store import PlatformStore
from src.validation.validator_base import ValidatorBase

logger = logging.getLogger(__name__)


# Past tense per action, because appending "ed" to the action name gives
# "approveed". Used only in the human-readable event message.
_PAST_TENSE = {
    ReviewAction.APPROVE: "approved",
    ReviewAction.EDIT: "edited",
    ReviewAction.REJECT: "rejected",
    ReviewAction.COMMENT: "commented on",
}


class OutputNotFoundError(LookupError):
    """Raised when a review action names an output that does not exist."""

    def __init__(self, output_id: str) -> None:
        self.output_id = output_id
        super().__init__(f"No generated output with id {output_id!r}.")


def default_schema_resolver(schema_name: str) -> type[BaseModel] | None:
    """Map a stored ``schema_name`` back to the Pydantic type that produced it.

    ``GeneratedOutput`` records the schema by name, not by reference, so
    re-validating an edited payload needs this lookup. Unknown names return
    ``None`` — a future agent's schema is not a reason to fail an edit.

    Args:
        schema_name: The class name stored on the output.

    Returns:
        The schema type, or ``None`` when it cannot be resolved.
    """
    from src.validation import schemas

    candidate = getattr(schemas, schema_name, None)
    if isinstance(candidate, type) and issubclass(candidate, BaseModel):
        return candidate
    return None


class ReviewService:
    """Lists outputs awaiting review and applies human review decisions.

    Args:
        store: Where outputs and reviews are persisted.
        validator: Validator used to re-check edited payloads; a default is
            built if omitted.
        schema_resolver: Maps a stored schema name to its Pydantic type.
            Override to teach the service about additional agent schemas.
    """

    def __init__(
        self,
        store: PlatformStore,
        *,
        validator: ValidatorBase | None = None,
        schema_resolver: Any = None,
    ) -> None:
        self._store = store
        self._validator = validator or ValidatorBase()
        self._resolve_schema = schema_resolver or default_schema_resolver

    # ------------------------------------------------------------------ #
    # Reading the queue
    # ------------------------------------------------------------------ #

    def list_pending(self, limit: int | None = None) -> list[GeneratedOutput]:
        """Return outputs still awaiting a decision, newest first.

        Args:
            limit: Maximum number of outputs to return.

        Returns:
            Every output in ``pending`` status.
        """
        return self._store.list_outputs(status=OutputStatus.PENDING, limit=limit)

    def list_outputs(
        self,
        *,
        status: OutputStatus | None = None,
        agent_run_id: str | None = None,
        agent_name: str | None = None,
        limit: int | None = None,
    ) -> list[GeneratedOutput]:
        """Return outputs matching the given filters, newest first.

        Args:
            status: Restrict to one review status.
            agent_run_id: Restrict to the outputs of a single run.
            agent_name: Restrict to one agent.
            limit: Maximum number of outputs to return.

        Returns:
            Matching outputs.
        """
        return self._store.list_outputs(
            status=status,
            agent_run_id=agent_run_id,
            agent_name=agent_name,
            limit=limit,
        )

    def get(self, output_id: str) -> GeneratedOutput:
        """Return one output.

        Args:
            output_id: The output to load.

        Returns:
            The output record.

        Raises:
            OutputNotFoundError: If no such output exists.
        """
        output = self._store.get_output(output_id)
        if output is None:
            raise OutputNotFoundError(output_id)
        return output

    def history(self, output_id: str) -> list[Review]:
        """Return an output's review history, oldest first.

        Args:
            output_id: The output to trace.

        Returns:
            Its immutable review records in chronological order.
        """
        return self._store.list_reviews(output_id=output_id)

    # ------------------------------------------------------------------ #
    # Review actions
    # ------------------------------------------------------------------ #

    def approve(
        self, output_id: str, reviewer: str, notes: str | None = None
    ) -> Review:
        """Approve an output, making it exportable.

        Args:
            output_id: The output being approved.
            reviewer: Identity of the human reviewer.
            notes: Optional free-text reviewer notes.

        Returns:
            The recorded review.

        Raises:
            OutputNotFoundError: If no such output exists.
            IllegalTransitionError: If the output is already in a terminal state.
        """
        return self._act(output_id, reviewer, ReviewAction.APPROVE, notes=notes)

    def reject(self, output_id: str, reviewer: str, notes: str | None = None) -> Review:
        """Reject an output, permanently barring it from export.

        Args:
            output_id: The output being rejected.
            reviewer: Identity of the human reviewer.
            notes: Optional free-text reviewer notes.

        Returns:
            The recorded review.

        Raises:
            OutputNotFoundError: If no such output exists.
            IllegalTransitionError: If the output is already in a terminal state.
        """
        return self._act(output_id, reviewer, ReviewAction.REJECT, notes=notes)

    def comment(self, output_id: str, reviewer: str, notes: str) -> Review:
        """Append a status-neutral note to an output's history.

        Available in every state, including the terminal ones, so the audit
        trail never closes.

        Args:
            output_id: The output being commented on.
            reviewer: Identity of the human reviewer.
            notes: The comment text.

        Returns:
            The recorded review.

        Raises:
            OutputNotFoundError: If no such output exists.
        """
        return self._act(output_id, reviewer, ReviewAction.COMMENT, notes=notes)

    def edit(
        self,
        output_id: str,
        reviewer: str,
        edited_payload: dict[str, Any],
        notes: str | None = None,
        *,
        grounded_context: GroundedContext | None = None,
    ) -> Review:
        """Replace an output's payload and re-validate the result.

        The new payload is checked against the output's declared schema and,
        where grounding evidence survives, against the chunk ids the generating
        run actually retrieved. The stored verdict is updated either way — an
        edit can repair a failing output or break a passing one, and the record
        must say which.

        Args:
            output_id: The output being edited.
            reviewer: Identity of the human reviewer.
            edited_payload: The replacement payload. Must not be empty.
            notes: Optional free-text reviewer notes.
            grounded_context: Grounding evidence to check citations against;
                defaults to reconstructing it from the run's
                ``source_chunk_ids``.

        Returns:
            The recorded review.

        Raises:
            OutputNotFoundError: If no such output exists.
            ValueError: If ``edited_payload`` is empty.
            IllegalTransitionError: If the output is already in a terminal state.
        """
        if not edited_payload:
            raise ValueError("An edit requires a non-empty replacement payload.")

        output = self.get(output_id)
        review = apply_review(
            output,
            reviewer,
            ReviewAction.EDIT,
            edited_payload=edited_payload,
            notes=notes,
        )
        self._revalidate(output, grounded_context=grounded_context)
        self._persist(output, review)
        return review

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _act(
        self,
        output_id: str,
        reviewer: str,
        action: ReviewAction,
        *,
        notes: str | None = None,
    ) -> Review:
        """Apply a payload-free review action and persist the result."""
        output = self.get(output_id)
        review = apply_review(output, reviewer, action, notes=notes)
        self._persist(output, review)
        return review

    def _persist(self, output: GeneratedOutput, review: Review) -> None:
        """Save the mutated output, append the review row, log the event."""
        self._store.save_output(output)
        self._store.save_review(review)
        self._store.log_event(
            REVIEW_ACTION,
            f"{review.reviewer} {_PAST_TENSE[review.action]} output "
            f"({review.previous_status.value} -> {review.new_status.value})",
            output_id=output.id,
            details={"action": review.action.value, "reviewer": review.reviewer},
        )

    def _revalidate(
        self,
        output: GeneratedOutput,
        *,
        grounded_context: GroundedContext | None = None,
    ) -> None:
        """Re-run validation over an edited payload and update the verdict.

        When the schema cannot be resolved the previous verdict is left alone
        and the report is marked ``revalidated: False``, so a stale verdict is
        never silently presented as a fresh one.
        """
        schema = self._resolve_schema(output.schema_name)
        if schema is None:
            logger.warning(
                "cannot re-validate output %s: unknown schema %r",
                output.id,
                output.schema_name,
            )
            output.validation_report = {
                **output.validation_report,
                "revalidated": False,
            }
            return

        context = GuardrailContext(
            grounded_context=grounded_context,
            retrieved_chunk_ids=(
                None if grounded_context is not None else self._run_chunk_ids(output)
            ),
        )
        result, _ = self._validator.validate(output.payload, schema, context=context)

        output.validation_passed = result.passed
        output.validation_report = {
            **result.model_dump(mode="json"),
            "revalidated": True,
        }

    def _run_chunk_ids(self, output: GeneratedOutput) -> list[str] | None:
        """Return the chunk ids the generating run retrieved, if it was grounded."""
        run = self._store.get_agent_run(output.agent_run_id)
        if run is None or not run.source_chunk_ids:
            return None
        return run.source_chunk_ids
