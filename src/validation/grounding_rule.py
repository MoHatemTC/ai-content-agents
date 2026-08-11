"""The platform's grounding guardrail, built on the retrieval lane's rule.

The retrieval lane owns the grounding check — :class:`GroundingVerificationRule`
in :mod:`src.retrieval.verifier` lives next to the ``verify_references``
contract it enforces, which is the right home for it. This module adopts that
rule rather than keeping a second, competing implementation, and extends it with
the three behaviours the review platform depends on:

**It never raises.** The base rule raises ``GroundingContextMissingError`` when
checked without a bound context. :meth:`ValidatorBase.validate
<src.validation.validator_base.ValidatorBase.validate>` documents that it never
raises and does not wrap ``rule.check()``, so an unbound instance reaching the
default rule set would turn a reportable validation failure into a crashed run.
Here, no evidence simply means the rule does not apply.

**It reaches nested citations.** The base rule returns early unless the output's
schema declares a top-level ``references`` field. ``QuestionBankOutput`` and
``TestHelpOutput`` cite per question, so that check would silently exempt half
the agents. This walks nested models via
:func:`~src.validation.guardrails.collect_content_references`.

**It accepts chunk ids alone.** :meth:`ReviewService.edit
<src.validation.review_service.ReviewService.edit>` re-validates a payload long
after the run, when the ``GroundedContext`` is gone and only
``AgentRun.source_chunk_ids`` survives. There is nothing left to bind, so the
rule also accepts the id set directly.

The rule keeps the base's ``grounding_verification`` name, so there is one name
for one concept across the project — metrics, reports and stored validation
reports all key on it.

This lives apart from :mod:`src.validation.guardrails` on purpose:
``src.retrieval.verifier`` imports ``GuardrailRule`` from there, so having
``guardrails`` import the verifier back would be a hard circular import.
"""

from __future__ import annotations

from pydantic import BaseModel

from src.retrieval.models import GroundedContext
from src.retrieval.verifier import GroundingVerificationRule
from src.validation.guardrails import (
    GuardrailContext,
    GuardrailViolation,
    Severity,
    collect_content_references,
)


class PlatformGroundingRule(GroundingVerificationRule):
    """Fails an output that cites a segment which was never retrieved.

    Evidence of what *was* retrieved can arrive three ways, checked in order:
    bound to the rule via :meth:`for_context` or :meth:`for_chunk_ids`, or
    supplied on the :class:`~src.validation.guardrails.GuardrailContext` passed
    to :meth:`check`. With none of them the rule does not apply.

    Args:
        grounded_context: The retrieval payload the agent was given.
        retrieved_chunk_ids: The same evidence reduced to ids, for callers that
            no longer hold the payload.
    """

    def __init__(
        self,
        grounded_context: GroundedContext | None = None,
        retrieved_chunk_ids: list[str] | None = None,
    ) -> None:
        super().__init__(grounded_context)
        self._retrieved_chunk_ids = (
            list(retrieved_chunk_ids) if retrieved_chunk_ids is not None else None
        )

    def for_context(self, grounded_context: GroundedContext) -> PlatformGroundingRule:
        """Return a copy bound to a :class:`GroundedContext`.

        Args:
            grounded_context: The context to verify citations against.

        Returns:
            A new rule bound to that context.
        """
        return PlatformGroundingRule(grounded_context=grounded_context)

    def for_chunk_ids(self, chunk_ids: list[str]) -> PlatformGroundingRule:
        """Return a copy bound to chunk ids alone.

        Used when re-validating a reviewer's edit, where the original
        ``GroundedContext`` no longer exists but the run recorded its ids.

        Args:
            chunk_ids: The chunk ids that were genuinely retrieved.

        Returns:
            A new rule bound to those ids.
        """
        return PlatformGroundingRule(retrieved_chunk_ids=chunk_ids)

    def _known_ids(self, context: GuardrailContext) -> set[str] | None:
        """Resolve the set of legitimately retrieved chunk ids, or ``None``."""
        bound_context = self._grounded_context
        if bound_context is None:
            bound_context = context.grounded_context
        if bound_context is not None:
            return set(bound_context.chunk_ids)

        ids = self._retrieved_chunk_ids
        if ids is None:
            ids = context.retrieved_chunk_ids
        return set(ids) if ids is not None else None

    def check(
        self, output: BaseModel, context: GuardrailContext
    ) -> GuardrailViolation | None:
        """Check every citation on ``output`` against what was retrieved.

        Args:
            output: The agent output to check.
            context: Guardrail configuration, which may itself carry the
                grounding evidence.

        Returns:
            A violation naming the fabricated ids, or ``None`` when every
            citation is genuine or no evidence is available to judge against.
        """
        known = self._known_ids(context)
        if known is None:
            return None  # Nothing to verify against; the rule does not apply.

        unknown = [
            reference.segment_id
            for reference in collect_content_references(output)
            if reference.segment_id not in known
        ]
        if not unknown:
            return None

        listed = ", ".join(repr(segment_id) for segment_id in unknown)
        return GuardrailViolation(
            rule_name=self.name,
            message=(
                f"Output cites {len(unknown)} segment id(s) that were never "
                f"retrieved for this query: {listed}. The citation is "
                "fabricated or points outside the retrieved scope."
            ),
            severity=Severity.ERROR,
        )
