"""Shared models for sequential batch generation."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

OutputT = TypeVar("OutputT", bound=BaseModel)


class BatchGenerationFailure(BaseModel):
    """One batch item that could not be generated."""

    index: int = Field(ge=0)
    input_item: dict[str, Any]
    error: str


class BatchGenerationResult(BaseModel, Generic[OutputT]):
    """Structured outcome of processing a generation batch."""

    successful_outputs: list[OutputT] = Field(default_factory=list)
    failed_items: list[BatchGenerationFailure] = Field(default_factory=list)
    total_processed: int = Field(ge=0)
    total_succeeded: int = Field(ge=0)
    total_failed: int = Field(ge=0)
    elapsed_seconds: float = Field(ge=0.0)
