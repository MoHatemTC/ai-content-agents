"""Pydantic schemas for the generation milestone (M5).

Matches the contract defined in docs/FASTAPI_INTEGRATION.md and
Sensei-AI src/types/api/generation.contracts.ts.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Citation(BaseModel):
    doc: str
    page: int | None = None
    chunk: str | None = None
    snippet: str
    score: float = 1.0


class GeneratedQuestion(BaseModel):
    id: str
    prompt: str
    type: str = "MCQ"
    difficulty: str = "Intermediate"
    options: list[str] | None = None
    answer: str
    rationale: str
    bloom: str = "Understanding"
    quality: float = 9.0
    grounded: float = 100.0
    estMinutes: int = 2
    review: str = "Pending"
    citations: list[Citation] = Field(default_factory=list)


class GenerateQuestionsRequest(BaseModel):
    workspaceId: str
    documentIds: list[str] = Field(default_factory=list)
    model: str = "gemini"
    options: dict[str, Any] = Field(default_factory=dict)
    count: int = 5
    difficulty: str = "Intermediate"
    types: list[str] = Field(default_factory=lambda: ["MCQ"])


class GenerateQuestionsResponse(BaseModel):
    generationId: str
    kind: Literal["question_bank"] = "question_bank"
    grounding_score: float = 100.0
    quality_score: float = 9.0
    questions: list[GeneratedQuestion]


class WsFlashcard(BaseModel):
    front: str
    back: str
    tag: str | None = None
    format: str = "term-definition"
    topic: str | None = None
    sourceChunkId: str | None = None
    citations: list[Citation] = Field(default_factory=list)


class GenerateFlashcardsRequest(BaseModel):
    workspaceId: str
    documentIds: list[str] = Field(default_factory=list)
    model: str = "gemini"
    options: dict[str, Any] = Field(default_factory=dict)
    count: int = 10
    cardFormat: str = "term-definition"
    topic: str | None = None


class GenerateFlashcardsResponse(BaseModel):
    generationId: str
    kind: Literal["flashcards"] = "flashcards"
    flashcards: list[WsFlashcard]


class FlashcardTopicsRequest(BaseModel):
    workspaceId: str
    documentIds: list[str] = Field(default_factory=list)
    model: str = "gemini"


class FlashcardTopicsResponse(BaseModel):
    topics: list[str] = Field(default_factory=list)


class StudyPlanSection(BaseModel):
    title: str
    items: list[str]


class StudyPlanDay(BaseModel):
    day: int
    topics: list[str]
    hours: float = 2.0


class GenerateStudyPlanRequest(BaseModel):
    workspaceId: str
    documentIds: list[str] = Field(default_factory=list)
    model: str = "gemini"
    options: dict[str, Any] = Field(default_factory=dict)
    weeks: int | None = None
    hoursPerWeek: float | None = None
    days: int | None = None
    hoursPerDay: float | None = None


class GenerateStudyPlanResponse(BaseModel):
    generationId: str
    kind: Literal["study_plan"] = "study_plan"
    summary: str
    sections: list[StudyPlanSection]
    days: list[StudyPlanDay] = Field(default_factory=list)


class WeakTopic(BaseModel):
    topic: str
    strength: int = 40
    action: str = "Review key concepts and active recall"
    description: str | None = Field(
        None, description="One-line summary of what to revisit for this topic."
    )
    difficulty: str = Field(
        "medium", description="Per-topic difficulty: easy/medium/hard."
    )
    nextRevisionDate: str | None = Field(
        None, description="Suggested review-by date (ISO), from the revision session."
    )
    confidencePrompt: str | None = Field(
        None, description="Optional self-check prompt for this topic."
    )


class GenerateRevisionSheetRequest(BaseModel):
    workspaceId: str
    documentIds: list[str] = Field(default_factory=list)
    model: str = "gemini"
    options: dict[str, Any] = Field(default_factory=dict)
    topics: list[str] = Field(default_factory=list)


class GenerateRevisionSheetResponse(BaseModel):
    generationId: str
    kind: Literal["revision_sheet"] = "revision_sheet"
    summary: str
    sections: list[StudyPlanSection]
    weakTopics: list[WeakTopic] = Field(default_factory=list)
