"""Guardrail foundation for validating agent output content.

A guardrail is a small, agent-agnostic content check that runs against an
already schema-valid output. This module provides:

* :class:`GuardrailViolation` — the structured result of a failed check,
* :class:`GuardrailContext` — per-run configuration/context a rule may consult,
* :class:`GuardrailRule` — the rule interface every guardrail implements, and
* three concrete rules plus :data:`DEFAULT_RULES`.

The rules answer three different questions about a schema-valid output:
:class:`NonEmptyTextRule` asks whether it says anything at all,
:class:`ReferencesPresentRule` asks whether it cites its sources, and
:class:`~src.validation.grounding_rule.PlatformGroundingRule` asks whether those
citations are **real** —
whether each cited segment was actually retrieved, catching a model that
fabricates provenance. Semantic entailment checking (does the source actually
*support* the claim?) remains out of scope.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum

from pydantic import BaseModel

from src.retrieval.models import GroundedContext
from src.validation.schemas import ContentReference


def reference_field_values(output: BaseModel) -> list[object]:
    """Return the value of every ``references`` field on an output, nested included.

    Agent schemas cite in two different shapes: ``MentorOutput`` and
    ``ConceptOutput`` carry a top-level ``references`` list, while
    ``QuestionBankOutput`` and ``TestHelpOutput`` carry one per question inside
    ``questions``. A rule that only looked at the top level would silently pass
    half the agents, so this walks nested models and lists of models too.

    Values are returned untyped because citation *presence* is meaningful for
    any element type — a schema may legitimately cite bare id strings.

    Args:
        output: Any schema-valid agent output.

    Returns:
        One entry per ``references`` field found, in document order. Empty when
        the output declares no citations anywhere, meaning citation rules do
        not apply to it.
    """
    found: list[object] = []

    def walk(value: object) -> None:
        if isinstance(value, BaseModel):
            for name in type(value).model_fields:
                attribute = getattr(value, name, None)
                if name == "references":
                    found.append(attribute)
                else:
                    walk(attribute)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)

    walk(output)
    return found


def collect_content_references(output: BaseModel) -> list[ContentReference]:
    """Gather every typed citation on an output, including nested ones.

    Unlike :func:`reference_field_values` this keeps only real
    :class:`~src.validation.schemas.ContentReference` objects, because verifying
    a citation requires a ``segment_id`` to compare against retrieval.

    Args:
        output: Any schema-valid agent output.

    Returns:
        Every ``ContentReference`` found, in document order.
    """
    found: list[ContentReference] = []
    for value in reference_field_values(output):
        if isinstance(value, ContentReference):
            found.append(value)
        elif isinstance(value, (list, tuple)):
            found.extend(item for item in value if isinstance(item, ContentReference))
    return found


class Severity(str, Enum):
    """Severity of a guardrail violation.

    ``ERROR`` violations fail validation; ``WARNING`` violations are surfaced in
    the validation result for the reviewer but do not fail it.
    """

    ERROR = "error"
    WARNING = "warning"


class GuardrailViolation(BaseModel):
    """A single guardrail failure, suitable for surfacing to a reviewer."""

    rule_name: str
    message: str
    severity: Severity = Severity.ERROR


class GuardrailContext(BaseModel):
    """Optional context/configuration passed to every rule during a validation run.

    Attributes:
        min_text_length: Minimum length (after stripping) required of a text field
            for :class:`NonEmptyTextRule`.
        required_text_fields: If set, restricts :class:`NonEmptyTextRule` to these
            fields; otherwise every string field on the output is checked.
        grounded_context: The retrieval payload the agent was given, when the
            output was produced through the grounded pipeline. Supplies
            the grounding rule with the set of chunk ids that were
            genuinely retrieved.
        retrieved_chunk_ids: The same information reduced to the ids alone, for
            callers that no longer hold the full payload — re-validating a
            reviewer's edit long after the run, from
            ``AgentRun.source_chunk_ids``. Ignored when ``grounded_context`` is
            set; when neither is set the grounding rule does not apply.
    """

    min_text_length: int = 1
    required_text_fields: list[str] | None = None
    grounded_context: GroundedContext | None = None
    retrieved_chunk_ids: list[str] | None = None


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

    Agent output schemas in this project cite their sources in one of two
    shapes — a top-level ``references`` list (``MentorOutput``,
    ``ConceptOutput``) or one per question (``QuestionBankOutput``,
    ``TestHelpOutput``). This rule fails when **any** declared ``references``
    field is empty, so an individual ungrounded question is caught rather than
    hidden behind its well-cited siblings. Schemas that declare no
    ``references`` field are not subject to it.
    """

    name = "references_present"

    def check(
        self, output: BaseModel, context: GuardrailContext
    ) -> GuardrailViolation | None:
        values = reference_field_values(output)
        if not values:
            return None  # Rule does not apply to this schema.
        if any(not value for value in values):
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

    By default **every** string field on the output is checked — agents whose
    schemas include optional/legitimately-blank text fields should pass
    ``context.required_text_fields`` to restrict the check to the fields that are
    actually required. The minimum length is ``context.min_text_length``
    (default 1, i.e. blank/whitespace-only fails).
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


# Rules that need no external evidence. The grounding check is added on top by
# ValidatorBase, which can import it without the circular dependency this module
# would hit (src.retrieval.verifier imports GuardrailRule from here).
DEFAULT_RULES: list[GuardrailRule] = [
    ReferencesPresentRule(),
    NonEmptyTextRule(),
]
