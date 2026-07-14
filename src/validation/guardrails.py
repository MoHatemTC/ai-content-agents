"""Guardrail foundation for validating agent output content.

A guardrail is a small, agent-agnostic content check that runs against an
already schema-valid output. This module provides:

* :class:`GuardrailViolation` — the structured result of a failed check,
* :class:`GuardrailContext` — per-run configuration/context a rule may consult,
* :class:`GuardrailRule` — the rule interface every guardrail implements, and
* two concrete Sprint 1 rules plus :data:`DEFAULT_RULES`.

This is a **foundation**, not a full rule library: it proves the mechanism with a
couple of rules. Deep, semantic hallucination checking against source content is a
later-sprint concern; the Sprint 1 grounding rule only verifies that provenance
references are present.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel


class GuardrailViolation(BaseModel):
    """A single guardrail failure, suitable for surfacing to a reviewer."""

    rule_name: str
    message: str
    severity: str = "error"


class GuardrailContext(BaseModel):
    """Optional context/configuration passed to every rule during a validation run.

    Attributes:
        min_text_length: Minimum length (after stripping) required of a text field
            for :class:`NonEmptyTextRule`.
        required_text_fields: If set, restricts :class:`NonEmptyTextRule` to these
            fields; otherwise every string field on the output is checked.
    """

    min_text_length: int = 1
    required_text_fields: list[str] | None = None


class GuardrailRule(ABC):
    """Interface every guardrail rule implements.

    Subclasses set a unique ``name`` and implement :meth:`check`, returning a
    :class:`GuardrailViolation` when the rule fails or ``None`` when it passes or
    does not apply to the given output.
    """

    name: str = "guardrail"

    @abstractmethod
    def check(
        self, output: BaseModel, context: GuardrailContext
    ) -> GuardrailViolation | None:
        """Check ``output`` and return a violation, or ``None`` if it passes/is N/A."""
        raise NotImplementedError


class ReferencesPresentRule(GuardrailRule):
    """Grounding/provenance rule: outputs that declare references must carry some.

    Agent output schemas in this project carry a ``references`` field listing the
    source chunks used (e.g. ``MentorOutput``, ``ConceptOutput``). This rule fails
    when such a schema produces an empty ``references`` list. Schemas that do not
    declare a ``references`` field are not subject to this rule.
    """

    name = "references_present"

    def check(
        self, output: BaseModel, context: GuardrailContext
    ) -> GuardrailViolation | None:
        if "references" not in type(output).model_fields:
            return None  # Rule does not apply to this schema.
        references = getattr(output, "references", None)
        if not references:
            return GuardrailViolation(
                rule_name=self.name,
                message=(
                    "Output has no source references; grounding/provenance is "
                    "required for generated study content."
                ),
            )
        return None


class NonEmptyTextRule(GuardrailRule):
    """Sanity rule: required text fields must not be blank or too short.

    By default every string field on the output is checked; set
    ``context.required_text_fields`` to restrict the check. The minimum length is
    ``context.min_text_length`` (default 1, i.e. blank/whitespace-only fails).
    """

    name = "non_empty_text"

    def check(
        self, output: BaseModel, context: GuardrailContext
    ) -> GuardrailViolation | None:
        if context.required_text_fields is not None:
            field_names = context.required_text_fields
        else:
            field_names = [
                name
                for name, value in output.model_dump().items()
                if isinstance(value, str)
            ]

        for name in field_names:
            value = getattr(output, name, None)
            if isinstance(value, str) and len(value.strip()) < context.min_text_length:
                return GuardrailViolation(
                    rule_name=self.name,
                    message=(
                        f"Text field {name!r} is empty or too short "
                        f"(minimum {context.min_text_length} character(s))."
                    ),
                )
        return None


# The default set of rules every agent output runs through in Sprint 1.
DEFAULT_RULES: list[GuardrailRule] = [ReferencesPresentRule(), NonEmptyTextRule()]
