"""FastAPI router for generation endpoints (M5).

Exposes POST /generate/questions, /generate/test-help, /generate/flashcards,
/generate/study-plan, /generate/revision.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from backend.auth.schemas import AuthUser
from backend.config import Settings
from backend.deps import get_current_user, get_settings, require_workspace_member
from backend.generation.schemas import (
    FlashcardTopicsRequest,
    FlashcardTopicsResponse,
    GenerateFlashcardsRequest,
    GenerateFlashcardsResponse,
    GenerateQuestionsRequest,
    GenerateQuestionsResponse,
    GenerateRevisionSheetRequest,
    GenerateRevisionSheetResponse,
    GenerateStudyPlanRequest,
    GenerateStudyPlanResponse,
)
from backend.generation.service import (
    flashcard_topics_service,
    generate_flashcards_service,
    generate_questions_service,
    generate_revision_sheet_service,
    generate_study_plan_service,
)

router = APIRouter(prefix="/generate", tags=["generation"])


@router.post("/questions", response_model=GenerateQuestionsResponse)
async def generate_questions(
    request_body: GenerateQuestionsRequest,
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> GenerateQuestionsResponse:
    """Generate grounded questions for a workspace."""
    require_workspace_member(
        db_path=settings.platform_db_path,
        workspace_id=request_body.workspaceId,
        user=current_user,
    )
    return generate_questions_service(
        request_body,
        db_path=settings.platform_db_path,
        chroma_dir=settings.chroma_dir,
        is_test_help=False,
    )


@router.post("/test-help", response_model=GenerateQuestionsResponse)
async def generate_test_help(
    request_body: GenerateQuestionsRequest,
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> GenerateQuestionsResponse:
    """Generate grounded exam / test help for a workspace."""
    require_workspace_member(
        db_path=settings.platform_db_path,
        workspace_id=request_body.workspaceId,
        user=current_user,
    )
    return generate_questions_service(
        request_body,
        db_path=settings.platform_db_path,
        chroma_dir=settings.chroma_dir,
        is_test_help=True,
    )


@router.post("/flashcards", response_model=GenerateFlashcardsResponse)
async def generate_flashcards(
    request_body: GenerateFlashcardsRequest,
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> GenerateFlashcardsResponse:
    """Generate grounded flashcards for a workspace."""
    require_workspace_member(
        db_path=settings.platform_db_path,
        workspace_id=request_body.workspaceId,
        user=current_user,
    )
    return generate_flashcards_service(
        request_body,
        db_path=settings.platform_db_path,
        chroma_dir=settings.chroma_dir,
    )


@router.post("/flashcard-topics", response_model=FlashcardTopicsResponse)
async def flashcard_topics(
    request_body: FlashcardTopicsRequest,
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> FlashcardTopicsResponse:
    """Return the topic allow-list extracted from the indexed documents."""
    require_workspace_member(
        db_path=settings.platform_db_path,
        workspace_id=request_body.workspaceId,
        user=current_user,
    )
    return flashcard_topics_service(
        request_body,
        db_path=settings.platform_db_path,
        chroma_dir=settings.chroma_dir,
    )


@router.post("/study-plan", response_model=GenerateStudyPlanResponse)
async def generate_study_plan(
    request_body: GenerateStudyPlanRequest,
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> GenerateStudyPlanResponse:
    """Generate a grounded study plan for a workspace."""
    require_workspace_member(
        db_path=settings.platform_db_path,
        workspace_id=request_body.workspaceId,
        user=current_user,
    )
    return generate_study_plan_service(
        request_body,
        db_path=settings.platform_db_path,
        chroma_dir=settings.chroma_dir,
    )


@router.post("/revision", response_model=GenerateRevisionSheetResponse)
async def generate_revision_sheet(
    request_body: GenerateRevisionSheetRequest,
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> GenerateRevisionSheetResponse:
    """Generate a grounded revision sheet for a workspace."""
    require_workspace_member(
        db_path=settings.platform_db_path,
        workspace_id=request_body.workspaceId,
        user=current_user,
    )
    return generate_revision_sheet_service(
        request_body,
        db_path=settings.platform_db_path,
        chroma_dir=settings.chroma_dir,
    )
