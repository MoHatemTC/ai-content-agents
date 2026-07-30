"""
Content quality validation utilities.

This module validates educational content before it is ingested into the
system. It performs lightweight heuristic checks to identify documents that
are unlikely to be useful for downstream AI agents.

Validation currently includes:
- Empty or whitespace-only content.
- Minimum document length.
- Readable text ratio.
- Excessive blank lines.
- Highly repetitive content.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re


@dataclass(slots=True)
class QualityResult:
    """
    Represents the outcome of a document quality validation.

    Attributes:
        passed:
            Whether the document passed all quality checks.
        score:
            Overall quality score between 0.0 and 1.0.
        issues:
            Human-readable descriptions of any validation failures.
    """

    passed: bool
    score: float
    issues: list[str] = field(default_factory=list)


class QualityChecker:
    """
    Validates educational content before ingestion.

    The checker applies a set of lightweight heuristics to detect low-quality
    documents that should not be processed by downstream agents.
    """

    MIN_CHARACTERS = 100
    MIN_LETTER_RATIO = 0.40
    MAX_EMPTY_LINE_RATIO = 0.50
    MIN_UNIQUE_WORD_RATIO = 0.20

    def validate(self, text: str) -> QualityResult:
        """
        Validate the quality of a document.

        Args:
            text:
                The cleaned document text.

        Returns:
            A ``QualityResult`` describing whether the document passed
            validation and any detected issues.
        """
        issues: list[str] = []

        if text is None:
            return QualityResult(
                passed=False,
                score=0.0,
                issues=["Document is empty."],
            )

        text = text.strip()

        if not text:
            return QualityResult(
                passed=False,
                score=0.0,
                issues=["Document is empty."],
            )

        self._check_length(text, issues)
        self._check_letter_ratio(text, issues)
        self._check_blank_lines(text, issues)
        self._check_repetition(text, issues)

        passed = not issues
        score = max(0.0, 1.0 - (0.25 * len(issues)))

        return QualityResult(
            passed=passed,
            score=round(score, 2),
            issues=issues,
        )

    def _check_length(self, text: str, issues: list[str]) -> None:
        """
        Validate that the document satisfies the minimum length requirement.

        Args:
            text:
                Document content.
            issues:
                List that accumulates validation issues.
        """
        if len(text) < self.MIN_CHARACTERS:
            issues.append(
                f"Document is too short (minimum {self.MIN_CHARACTERS} characters)."
            )

    def _check_letter_ratio(self, text: str, issues: list[str]) -> None:
        """
        Validate that the document contains sufficient readable text.

        Args:
            text:
                Document content.
            issues:
                List that accumulates validation issues.
        """
        letter_ratio = sum(char.isalpha() for char in text) / len(text)

        if letter_ratio < self.MIN_LETTER_RATIO:
            issues.append("Document contains too little readable text.")

    def _check_blank_lines(self, text: str, issues: list[str]) -> None:
        """
        Detect documents containing excessive blank lines.

        Args:
            text:
                Document content.
            issues:
                List that accumulates validation issues.
        """
        lines = text.splitlines()

        if not lines:
            return

        empty_lines = sum(1 for line in lines if not line.strip())
        empty_ratio = empty_lines / len(lines)

        if empty_ratio > self.MAX_EMPTY_LINE_RATIO:
            issues.append("Document contains excessive blank lines.")

    def _check_repetition(self, text: str, issues: list[str]) -> None:
        """
        Detect highly repetitive document content.

        Args:
            text:
                Document content.
            issues:
                List that accumulates validation issues.
        """
        words = re.findall(r"\b\w+\b", text.lower())

        if not words:
            return

        unique_ratio = len(set(words)) / len(words)

        if unique_ratio < self.MIN_UNIQUE_WORD_RATIO:
            issues.append("Document appears to contain highly repetitive content.")