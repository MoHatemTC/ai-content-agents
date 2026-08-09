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
    # A question's rationale is the field that asserts something about the
    # source, so it is the exact analogue of `explanation` (BUG-12).
    "rationale",
)

# Deliberately NOT a claim field: `next_steps`.
#
# It is the mentor's recommendation about what to study next - "Re-read the loop
# section", "Attempt the end-of-chapter problems". Advice about what the learner
# should do is by construction absent from the source passage, so checking it
# for support against that passage rejects every correct answer. Measured: 5 of
# 5 realistic next-steps scored below the threshold, and it is a required field
# (mentor.yaml), so mentor generations failed 5 of 5 whenever grounding was on.
#
# Same reasoning that keeps question stems and distractors out (BUG-12): the
# check is for claims the source can settle, not for everything the model wrote.

# Schemas that carry their claims one level down. QuestionBankOutput and
# TestHelpOutput hold everything inside `questions`, so a top-level scan found
# nothing and validate_support passed anything at all - a check that cannot
# fail, which is worse than no check because it reads as coverage.
_CLAIM_CONTAINERS = ("questions",)
# Share of a claim's content words that must appear in the source.
_SUPPORT_THRESHOLD = 0.6

# Sentences addressed to the *learner* rather than asserting anything about the
# source. mentor.yaml instructs the model to answer "in a supportive and
# encouraging way" and to "encourage understanding by asking the learner to
# think about the concept", so it opens with "Hello there!" and "You are asking
# a wonderful question", and closes with a question put back to the reader.
#
# None of that is a claim the source can settle, and checking it for support
# rejects a correct answer. Measured against the physics textbook: of 9 claim
# sentences in a live mentor reply, all 6 factual ones passed and all 3 failures
# were exactly this. Same reasoning that keeps question stems and distractors
# out of the claim set (BUG-12) - the check is for claims, not for prose.
_SECOND_PERSON = re.compile(
    r"\b(?:you|your|yourself|yours|let's|we'll)\b", re.IGNORECASE
)
_GREETING = re.compile(
    r"^\s*(?:hello|hi|hey|great|well done|good job|nice)\b",
    re.IGNORECASE,
)
_PEDAGOGIC_IMPERATIVE = re.compile(
    r"^\s*(?:try|think|consider|imagine|picture|notice|remember|review|practice|explore|attempt|reflect|ask)\b",
    re.IGNORECASE,
)
_ABOUT_THE_SOURCE = re.compile(
    r"\b(?:the (?:provided|supplied|given|uploaded|educational|source)(?:\s+\w+){0,2}\s+(?:content|material|text|passages?)|i am sorry|i apologize)\b",
    re.IGNORECASE,
)
_WORD_PATTERN = re.compile(r"[a-z0-9]+")
_NEGATION_PATTERN = re.compile(r"\b(?:no|not|never|without)\b", re.IGNORECASE)
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


def _token_overlap_score(claim_tokens: set[str], source_tokens: set[str]) -> float:
    """Return the share of claim tokens also present in the source."""
    if not claim_tokens:
        return 1.0
    return len(claim_tokens & source_tokens) / len(claim_tokens)


def _is_learner_address(text: str) -> bool:
    """Whether a sentence talks *to* the learner, or *about* the source.

    Three shapes, each measured against live mentor output rather than guessed:

    * **Greetings and second-person praise** - "Hello there!", "You are doing a
      wonderful job exploring the exciting world of electricity."
    * **Pedagogic imperatives** - "Try to picture how these electrons spread the
      charge.", "Think about why the field weakens with distance." Instructions
      to the reader, not assertions about the passage.
    * **Meta-statements about the content** - "The provided educational content
      does not contain information about magnetic fields." Both prompts
      *require* this when the material is insufficient, and it describes the
      source rather than claiming anything the source could confirm.

    The known cost: a claim phrased in the second person - "You can see the
    field weakens with distance" - is exempted and goes unchecked. That is a
    real hole, and it is the better trade: before this, the check rejected 100%
    of mentor output, so it was switched off in production and validated
    nothing at all. Stated in the PR rather than hidden here.
    """
    stripped = text.strip()
    if _GREETING.match(stripped) or _PEDAGOGIC_IMPERATIVE.match(stripped):
        return True
    if _ABOUT_THE_SOURCE.search(stripped):
        return True
    return bool(_SECOND_PERSON.search(stripped))


def _contains_negation(text: str) -> bool:
    """Detect simple negation terms so overlap cannot hide contradictions."""
    return bool(_NEGATION_PATTERN.search(text))


def extract_claim_text(
    output: BaseModel | Mapping[str, Any],
) -> list[str]:
    """Extract sentence-like claims from meaningful explanation fields.

    What is deliberately *not* a claim matters as much as what is, and each
    exclusion was measured against a real question and a real source passage:

    * **References** - citation provenance is validated separately by
      :func:`src.retrieval.grounding.verify_references`.
    * **Question stems** - they routinely read "Which of the following is
      **not** ...". Measured on such a stem: :func:`_contains_negation` fires
      and token overlap is 0.33 against a source containing no negation, so a
      correct question would be reported as both contradictory *and*
      unsupported. Two independent false-positive mechanisms.
    * **Options** - distractors are *deliberately false*. Feeding them to an
      overlap check guarantees an unsupported verdict on every well-formed
      question bank.
    * **``correct_answer``** - usually a single token, so the ratio is 0 or 1
      with nothing in between. Noise, not signal.

    ``rationale`` is included because it is the field that asserts something
    about the source; measured overlap 0.71 on a faithful rationale, with no
    negation.
    """
    data = output.model_dump() if isinstance(output, BaseModel) else output
    claims: list[str] = []

    def collect(source: Mapping[str, Any]) -> None:
        for field_name in _CLAIM_FIELDS:
            value = source.get(field_name)
            if isinstance(value, str):
                claims.extend(_split_statements(value))
            elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                for item in value:
                    if isinstance(item, str):
                        claims.extend(_split_statements(item))

    collect(data)

    # One level only, and only through named containers. A generic "collect
    # every string leaf" walk would pull in reference text and distractors, and
    # would shift mentor/concept groundedness ratios that other tests pin.
    for container in _CLAIM_CONTAINERS:
        for item in data.get(container) or []:
            if isinstance(item, Mapping):
                collect(item)

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
    claim_list = [
        statement
        for statement in (
            _split_statements(claims)
            if isinstance(claims, str)
            else [
                statement
                for claim in claims
                for statement in _split_statements(claim)
            ]
        )
        if not _is_learner_address(statement)
    ]
    source_text = " ".join(chunk.chunk.text for chunk in context.chunks)
    source_tokens = _content_tokens(source_text)
    source_has_negation = _contains_negation(source_text)
    unsupported = []
    for claim in claim_list:
        overlap = _token_overlap_score(_content_tokens(claim), source_tokens)
        # The negation check exists so that overlap cannot *hide* a
        # contradiction - "charge is not conserved" shares every content word
        # with "charge is conserved". That only applies when the claim looks
        # supported on overlap alone. Firing it on a low-overlap claim adds
        # nothing (overlap already rejects it) and misfires on the meta-statement
        # both prompts explicitly ask for: "the content does not cover X".
        contradictory = (
            overlap >= _SUPPORT_THRESHOLD
            and _contains_negation(claim)
            and not source_has_negation
        )
        if overlap < _SUPPORT_THRESHOLD or contradictory:
            unsupported.append(claim)
    return SupportValidationResult(
        supported=not unsupported,
        unsupported_claims=unsupported,
    )
