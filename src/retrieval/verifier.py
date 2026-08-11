"""Grounding-verification guardrail: catches fabricated citations.

Wraps :func:`src.retrieval.grounding.verify_references` as a
:class:`~src.validation.guardrails.GuardrailRule` so the validation lane can
*enforce*, not just check, that every cited ``segment_id`` on an agent
output was genuinely part of the grounded context it was given.
``ReferencesPresentRule`` (in the validation lane) only checks that
references exist; this rule checks they are real — a model that cites a
plausible-looking but never-retrieved chunk id fails here.

This is the retrieval lane's producer-side answer to the "answer supported
by context" check the validation lane needs during hallucination
verification: the check itself lives here (next to the contract it
verifies), the validation lane only has to wire it in as a guardrail.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from src.retrieval.grounding import verify_references
from src.validation.guardrails import (
    GuardrailContext,
    GuardrailRule,
    GuardrailViolation,
    Severity,
)

if TYPE_CHECKING:
    from src.retrieval.models import GroundedContext


class GroundingContextMissingError(RuntimeError):
    """Raised when the rule is checked without a :class:`GroundedContext` bound.

    A guardrail runs per-output, but knowing which citations are legitimate
    requires the specific :class:`~src.retrieval.models.GroundedContext` that
    fed the agent for *this* query — that isn't part of the output schema,
    so it can't be inferred from ``output`` alone. Callers must bind it via
    :meth:`GroundingVerificationRule.for_context` before checking.
    """


class GroundingVerificationRule(GuardrailRule):
    """Fails an output when any cited ``segment_id`` was never actually retrieved.

    Outputs whose schema has no ``references`` field are not subject to this
    rule (schema-level presence is ``ReferencesPresentRule``'s job; this rule
    only judges the references that *do* exist).

    Usage::

        context = build_grounded_context(query, scope, retriever)
        output = mentor_agent.generate(content=context.as_prompt_content(), ...)
        rule = GroundingVerificationRule().for_context(context)
        violation = rule.check(output, GuardrailContext())
    """

    name = "grounding_verification"

    def __init__(self, grounded_context: GroundedContext | None = None) -> None:
        """Create the rule, optionally pre-bound to a :class:`GroundedContext`.

        Args:
            grounded_context: The context the output under check was
                generated from. May be omitted and supplied later via
                :meth:`for_context`.
        """
        self._grounded_context = grounded_context

    def for_context(
        self, grounded_context: GroundedContext
    ) -> GroundingVerificationRule:
        """Return a copy of this rule bound to a specific :class:`GroundedContext`.

        A fresh instance is returned rather than mutating ``self`` so one
        rule object is never silently re-bound out from under a concurrent
        check.

        Args:
            grounded_context: The context to verify citations against.

        Returns:
            A new :class:`GroundingVerificationRule` bound to ``grounded_context``.
        """
        return GroundingVerificationRule(grounded_context)

    def check(
        self, output: BaseModel, context: GuardrailContext
    ) -> GuardrailViolation | None:
        """Check that every reference on ``output`` was genuinely retrieved.

        Args:
            output: The agent output to check (e.g. ``MentorOutput``).
            context: Guardrail run configuration (unused by this rule; kept
                for interface compatibility with :class:`GuardrailRule`).

        Returns:
            A :class:`GuardrailViolation` naming the fabricated segment ids,
            or ``None`` when every citation is genuine or the schema has no
            ``references`` field.

        Raises:
            GroundingContextMissingError: If no :class:`GroundedContext` has
                been bound via the constructor or :meth:`for_context`.
        """
        if "references" not in type(output).model_fields:
            return None  # Rule does not apply to this schema.
        if self._grounded_context is None:
            raise GroundingContextMissingError(
                "GroundingVerificationRule.check() requires a bound "
                "GroundedContext; call .for_context(ctx) before checking "
                "an output."
            )
        references = getattr(output, "references", None) or []
        verification = verify_references(references, self._grounded_context)
        if not verification.valid:
            return GuardrailViolation(
                rule_name=self.name,
                message=(
                    "Output cites segment id(s) that were never retrieved for "
                    f"this query: {verification.unknown_segment_ids}. This "
                    "indicates a fabricated or out-of-scope citation."
                ),
                severity=Severity.ERROR,
            )
        return None
