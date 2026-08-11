from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Same rule the four content-agent schemas have carried since #39, and for the
# same reason: pydantic drops unknown keys silently by default, so a near-miss
# on an optional field - "tag" for "tags", "source_topics" spelled singular -
# vanished without a word and produced a card that quietly lost its grounding.
# The prompts have always ended with "do not add extra fields"; nothing on this
# side enforced it. Forbidding extras turns a silent drop into a visible,
# retryable generation error.
_STRICT = ConfigDict(extra="forbid")


class Flashcard(BaseModel):
    model_config = _STRICT

    front: str = Field(..., description="Card front (question or term).")
    back: str = Field(..., description="Card back (answer or definition).")
    format: str = Field(
        "term-definition",
        description="Card format: 'term-definition' or 'qa'.",
    )
    source_topic: str | None = Field(
        None,
        description="Real topic from content that this card drills (never fabricated).",
    )
    source_chunk_id: str | None = Field(
        None, description="Optional ingestion chunk id for traceability."
    )
    tags: list[str] = Field(default_factory=list)


class FlashcardSet(BaseModel):
    model_config = _STRICT

    title: str = Field(..., description="The title of the flashcard set.")
    description: str | None = Field(
        None, description="Optional description of the flashcard set."
    )
    cards: list[Flashcard] = Field(
        ...,
        min_length=1,
        description=(
            "List of flashcards in the set. At least one - a request for cards "
            "that produces none is a failure, not a success, which is the rule "
            "QuestionBankOutput has enforced since BUG-06."
        ),
    )
    source_topics: list[str] = Field(
        default_factory=list,
        description="Real content topics cards were built from.",
    )
    source_chunk_ids: list[str] = Field(default_factory=list)
    needs_human_review: Literal[True] = Field(
        default=True,
        frozen=True,
        description=(
            "Gate flag: outputs are pending review, never final. Literal and "
            "frozen, matching the content-agent schemas - this is a control "
            "over the system, so neither the model nor a later caller may "
            "switch it off (BUG-07). It was a plain mutable bool here, so a "
            "reply carrying false was accepted."
        ),
    )
