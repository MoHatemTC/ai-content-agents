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

import re
from dataclasses import dataclass, field


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
    MIN_READABLE_RATIO = 0.40
    MAX_EMPTY_LINE_RATIO = 0.50
    MIN_UNIQUE_WORD_RATIO = 0.20

    # Vocabulary is measured over windows of this many words rather than over the
    # whole document. See _check_repetition for why the distinction matters.
    REPETITION_WINDOW_WORDS = 2000

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
        self._check_readable_ratio(text, issues)
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

    def _check_readable_ratio(self, text: str, issues: list[str]) -> None:
        """
        Validate that the document is made of readable characters.

        The check exists to catch mojibake and binary junk - text that is
        characters but not writing. It counted **letters** against every
        character, which quietly made it a test of prose: a worked physics
        solution is 22% digits and 23% operators, so it scored 0.29 and was
        rejected as unreadable while being perfectly good study material.

        Counting alphanumerics against non-whitespace asks the question actually
        intended. Digits are content, not noise, and whitespace is neither.
        Measured: worked physics 0.68, ordinary prose 0.98, a physics textbook
        0.94, mojibake and binary 0.00.

        Args:
            text:
                Document content.
            issues:
                List that accumulates validation issues.
        """
        non_whitespace = sum(not char.isspace() for char in text)
        if not non_whitespace:
            return

        readable_ratio = sum(char.isalnum() for char in text) / non_whitespace

        if readable_ratio < self.MIN_READABLE_RATIO:
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

        Vocabulary richness is measured **per window**, not over the whole
        document, because the ratio of distinct words to total words falls as a
        document grows however varied its prose: a writer reuses "the" and "of"
        indefinitely while the stock of new words runs out (Heaps' law). Judged
        whole-document, length alone reads as repetition, and a real textbook is
        rejected for being long - a 1,598-page physics text scores 0.019 against
        a 0.20 floor, yet 0.381 over its first 2,000 words.

        Averaging the ratio across fixed-size windows keeps the check meaningful
        at any length: genuinely repetitive text scores low in every window,
        while a long varied document scores normally in each one.

        Args:
            text:
                Document content.
            issues:
                List that accumulates validation issues.
        """
        words = re.findall(r"\b\w+\b", text.lower())

        if not words:
            return

        window = self.REPETITION_WINDOW_WORDS
        windows = [
            words[start : start + window] for start in range(0, len(words), window)
        ]

        # A short trailing window would score near 1.0 whatever the document says
        # - three words are almost always three distinct words - and would drag
        # the average up enough to pass genuinely repetitive text. Fold it back
        # into its predecessor instead of letting it vote on its own.
        if len(windows) > 1 and len(windows[-1]) < window // 2:
            windows[-2].extend(windows.pop())

        ratios = [len(set(chunk)) / len(chunk) for chunk in windows]
        unique_ratio = sum(ratios) / len(ratios)

        if unique_ratio < self.MIN_UNIQUE_WORD_RATIO:
            issues.append("Document appears to contain highly repetitive content.")
