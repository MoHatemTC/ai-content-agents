"""Reusable, agent-agnostic validation base.

Every agent output runs through :class:`ValidatorBase` before it is persisted as a
:class:`~src.validation.review_schema.GeneratedOutput`. Validation happens in two
steps and **never raises** on bad output — it returns a structured result instead
(graceful invalid-output handling):

1. **Schema check** — parse ``raw_output`` and validate it against the agent's
   declared Pydantic schema, collecting any errors.
2. **Guardrails** — only if the schema check passed, run each guardrail rule and
   collect violations.

The validator has no knowledge of any specific agent: the caller supplies the
schema type and (optionally) the rules, so the same base serves every lane.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence

from pydantic import BaseModel, ValidationError

from src.validation.guardrails import (
    DEFAULT_RULES,
    GuardrailContext,
    GuardrailRule,
    GuardrailViolation,
    Severity,
)

logger = logging.getLogger(__name__)


class ValidationResult(BaseModel):
    """Structured verdict for one output, stored on its ``GeneratedOutput`` record."""

    passed: bool
    schema_errors: list[str] = []
    guardrail_violations: list[GuardrailViolation] = []


class ValidatorBase:
    """Validates raw agent output against a declared schema plus guardrail rules.

    Args:
        default_rules: Rules to use when :meth:`validate` is called without an
            explicit ``rules`` argument. Defaults to
            :data:`~src.validation.guardrails.DEFAULT_RULES`.
    """

    def __init__(self, default_rules: Sequence[GuardrailRule] | None = None) -> None:
        self._default_rules: list[GuardrailRule] = (
            list(default_rules) if default_rules is not None else list(DEFAULT_RULES)
        )

    def validate(
        self,
        raw_output: str | dict[str, object],
        output_schema: type[BaseModel],
        rules: Sequence[GuardrailRule] | None = None,
        context: GuardrailContext | None = None,
    ) -> tuple[ValidationResult, BaseModel | None]:
        """Validate ``raw_output`` against ``output_schema`` and the guardrail rules.

        Args:
            raw_output: The agent output, either a JSON string or a mapping.
            output_schema: The Pydantic model type the output must conform to.
            rules: Guardrail rules to run; falls back to the validator's defaults.
            context: Optional guardrail context/config; a default is used if omitted.

        Returns:
            A ``(result, model)`` tuple. ``model`` is the parsed, schema-valid
            instance when the schema check passes, otherwise ``None``. ``result``
            always describes the full outcome and is never raised.
        """
        active_rules = list(rules) if rules is not None else self._default_rules
        active_context = context if context is not None else GuardrailContext()

        # Step 0: normalise a JSON string into a mapping.
        if isinstance(raw_output, str):
            try:
                data: object = json.loads(raw_output)
            except json.JSONDecodeError as exc:
                logger.info("validation failed: output_schema=%s invalid JSON", output_schema.__name__)
                return (
                    ValidationResult(passed=False, schema_errors=[f"invalid JSON: {exc}"]),
                    None,
                )
        else:
            data = raw_output

        # Step 1: schema check.
        try:
            model = output_schema.model_validate(data)
        except ValidationError as exc:
            errors = [
                f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}"
                for err in exc.errors()
            ]
            logger.info(
                "validation failed: output_schema=%s schema_errors=%d",
                output_schema.__name__,
                len(errors),
            )
            return ValidationResult(passed=False, schema_errors=errors), None

        # Step 2: guardrails (only reached when the schema check passed).
        violations: list[GuardrailViolation] = []
        for rule in active_rules:
            violation = rule.check(model, active_context)
            if violation is not None:
                violations.append(violation)

        # Warning-severity violations are surfaced for the reviewer but only
        # error-severity ones fail validation.
        passed = not any(v.severity is Severity.ERROR for v in violations)
        logger.info(
            "validation complete: output_schema=%s passed=%s violations=%d",
            output_schema.__name__,
            passed,
            len(violations),
        )
        return ValidationResult(passed=passed, guardrail_violations=violations), model
