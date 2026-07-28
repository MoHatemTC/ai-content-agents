"""Objective guardrails for Question Bank and Test Help outputs.

Distractor plausibility remains a human-review judgement.  These rules only
enforce properties that can be checked deterministically before review.
"""

from __future__ import annotations

from pydantic import BaseModel

from src.validation.guardrails import GuardrailContext, GuardrailRule, GuardrailViolation
from src.validation.schemas import QuestionBankOutput, QuestionType, TestHelpOutput


QuestionSetOutput = QuestionBankOutput | TestHelpOutput


class QuestionItemQualityRule(GuardrailRule):
    """Validate answer-key and option invariants for every generated question."""

    name = "question_item_quality"

    def check(
        self, output: BaseModel, context: GuardrailContext
    ) -> GuardrailViolation | None:
        if not isinstance(output, (QuestionBankOutput, TestHelpOutput)):
            return None

        issues: list[str] = []
        seen_stems: set[str] = set()
        for index, question in enumerate(output.questions or [], start=1):
            prefix = f"Question {index}"
            stem = (question.question or "").strip().casefold()
            if not stem:
                issues.append(f"{prefix} has an empty question stem.")
            elif stem in seen_stems:
                issues.append(f"{prefix} duplicates a previous question stem.")
            else:
                seen_stems.add(stem)

            rationale = (question.rationale or "").strip()
            if not rationale:
                issues.append(f"{prefix} has an empty rationale.")

            if not question.references:
                issues.append(f"{prefix} has no grounding references.")

            if question.type is QuestionType.SHORT_ANSWER:
                if question.options is not None:
                    issues.append(f"{prefix} is short_answer but options must be null.")
                continue

            options = question.options
            if not options:
                issues.append(f"{prefix} requires answer options.")
                continue

            normalized = [
                option.strip().casefold() if isinstance(option, str) else ""
                for option in options
            ]
            if any(not option for option in normalized):
                issues.append(f"{prefix} contains an empty option.")
            if len(set(normalized)) != len(normalized):
                issues.append(f"{prefix} contains duplicate options.")

            required_options = 2 if question.type is QuestionType.TRUE_FALSE else 4
            if len(options) < required_options:
                issues.append(
                    f"{prefix} needs at least {required_options} options for "
                    f"{question.type.value}."
                )
            correct_ans = (question.correct_answer or "").strip().casefold()
            if correct_ans not in normalized:
                issues.append(f"{prefix} correct_answer is not one of its options.")

        if issues:
            return GuardrailViolation(rule_name=self.name, message=" ".join(issues))
        return None
