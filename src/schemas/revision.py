from datetime import date

from pydantic import BaseModel, Field


class RevisionItem(BaseModel):
    topic: str = Field(..., description="The topic to revise")
    description: str | None = Field(
        None, description="Optional description of the revision item"
    )
    next_revision_date: date = Field(
        ..., description="The next date to revise this item"
    )
    difficulty: str = Field(
        ..., description="Difficulty level (e.g., easy, medium, hard)"
    )


class RevisionSession(BaseModel):
    session_date: date = Field(..., description="The date of the revision session")
    items: list[RevisionItem] = Field(
        ..., description="List of items to revise in this session"
    )
    notes: str | None = Field(
        None, description="Optional notes for this revision session"
    )
