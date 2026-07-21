from pydantic import BaseModel, Field
from typing import List, Optional


class Flashcard(BaseModel):
    front: str = Field(..., description="The question or prompt on the front of the flashcard")
    back: str = Field(..., description="The answer or explanation on the back of the flashcard")
    tags: Optional[List[str]] = Field(default_factory=list, description="Optional tags to categorize the flashcard")


class FlashcardSet(BaseModel):
    title: str = Field(..., description="The title of the flashcard set")
    description: Optional[str] = Field(None, description="Optional description of the flashcard set")
    cards: List[Flashcard] = Field(..., description="List of flashcards in the set")
