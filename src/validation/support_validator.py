"""Deterministic validation of generated claims against grounded content."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel

from src.retrieval.models import GroundedContext


class SupportValidationResult(BaseModel):
    """Result of checking generated claims against retrieved content."""

    supported: bool
    unsupported_claims: list[str]


_CLAIM_FIELDS = (
    "definition",
    "explanation",
    "key_points",
    "next_steps",
)
_WORD_PATTERN = re.compile(r"[a-z0-9]+")
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "is",
    "of",
    "practice",
    "the",
    "to",
}


def _split_statements(text: str) -> list[str]:
    """Split a text field into non-empty sentence-like statements."""
    return [
        statement.strip()
        for statement in re.split(r"(?<=[.!?])\s+|\n+", text.strip())
        if statement.strip()
    ]


def _stem(word: str) -> str:
    """Apply a small deterministic suffix normalization for word variants."""
    if len(word) > 5 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith("es"):
        return word[:-2]
    if len(word) > 3 and word.endswith("s"):
        return word[:-1]
    return word


def _content_tokens(text: str) -> set[str]:
    """Return normalized content words used for deterministic comparison."""
    return {
        _stem(word)
        for word in _WORD_PATTERN.findall(text.lower())
        if word not in _STOP_WORDS
    }


def extract_claim_text(
    output: BaseModel | Mapping[str, Any],
) -> list[str]:
    """Extract sentence-like claims from meaningful explanation fields.

    References are intentionally excluded because citation provenance is
    validated separately by :func:`src.retrieval.grounding.verify_references`.
    """
    data = output.model_dump() if isinstance(output, BaseModel) else output
    claims: list[str] = []
    for field_name in _CLAIM_FIELDS:
        value = data.get(field_name)
        if isinstance(value, str):
            claims.extend(_split_statements(value))
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for item in value:
                if isinstance(item, str):
                    claims.extend(_split_statements(item))
    return claims


def validate_support(
    claims: str | Sequence[str],
    context: GroundedContext,
) -> SupportValidationResult:
    """Validate each claim against the retrieved chunk text.

    Matching is deterministic and intentionally conservative: every
    meaningful normalized word in a claim must occur in the grounded source.
    This supports simple grammatical variants while avoiding external model
    calls. A string input remains supported for backward compatibility.
    """
    claim_list = (
        _split_statements(claims)
        if isinstance(claims, str)
        else [
            statement
            for claim in claims
            for statement in _split_statements(claim)
        ]
    )
    source_text = " ".join(chunk.chunk.text for chunk in context.chunks)
    source_tokens = _content_tokens(source_text)
    unsupported = [
        claim
        for claim in claim_list
        if not _content_tokens(claim).issubset(source_tokens)
    ]
    return SupportValidationResult(
        supported=not unsupported,
        unsupported_claims=unsupported,
    )
