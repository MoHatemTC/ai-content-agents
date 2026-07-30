from __future__ import annotations

from pydantic import BaseModel, Field


class Flashcard(BaseModel):
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
    title: str = Field(..., description="The title of the flashcard set.")
    description: str | None = Field(
        None, description="Optional description of the flashcard set."
    )
    cards: list[Flashcard] = Field(..., description="List of flashcards in the set.")
    source_topics: list[str] = Field(
        default_factory=list,
        description="Real content topics cards were built from.",
    )
    source_chunk_ids: list[str] = Field(default_factory=list)
    needs_human_review: bool = Field(
        True, description="Gate flag: outputs are pending review, never final."
    )
