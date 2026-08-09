"""Service layer for generation endpoints (M5).

Integrates src/agents (QuestionBankAgent, TestHelpAgent) and
src/study (FlashcardAgent, StudyPlanAgent, RevisionAgent) with
backend/search/service.py build_grounded_context and PlatformStore.
"""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from typing import Any
from uuid import uuid4

from backend.generation.schemas import (
    Citation,
    FlashcardTopicsRequest,
    FlashcardTopicsResponse,
    GeneratedQuestion,
    GenerateFlashcardsRequest,
    GenerateFlashcardsResponse,
    GenerateQuestionsRequest,
    GenerateQuestionsResponse,
    GenerateRevisionSheetRequest,
    GenerateRevisionSheetResponse,
    GenerateStudyPlanRequest,
    GenerateStudyPlanResponse,
    StudyPlanDay,
    StudyPlanSection,
    WeakTopic,
    WsFlashcard,
)
from backend.errors import ApiError
from backend.search.service import build_grounded_context
from src.agents.question_bank_agent import QuestionBankAgent
from src.agents.test_help_agent import TestHelpAgent
from src.llm_gateway import build_client, default_model
from src.retrieval.models import InsufficientGroundingError
from src.schemas.flashcards import Flashcard
from src.study.flashcard_agent import FlashcardAgent
from src.study.revision_agent import RevisionAgent
from src.study.study_plan_agent import StudyPlanAgent
from src.validation.review_schema import AgentRun, GeneratedOutput, OutputStatus
from src.validation.schemas import QuestionBankOutput, QuestionItem
from src.validation.store import PlatformStore
from src.validation.support_validator import extract_claim_text, validate_support

logger = logging.getLogger(__name__)


def _get_llm_client(for_study: bool = False) -> Any:
    """Resolve an LLM client.

    Returns the real LiteLLM client when credentials are configured. The
    compliant test doubles are used ONLY when ``SENSEI_USE_TEST_DOUBLES`` is
    set (the pytest suite, via ``tests/conftest.py``). In production a missing
    or broken LLM configuration raises a 503 rather than fabricating content,
    so the API never serves placeholder "Question 1 about the supplied
    content?" output from the doubles.

    The doubles are imported lazily from ``src.testing.compliant`` — never from
    ``tests.conftest``, whose import-time env writes would wipe the gateway
    credentials in a running server.
    """
    if os.getenv("SENSEI_USE_TEST_DOUBLES"):
        if for_study:
            from src.testing.compliant import CompliantStudyClient

            return CompliantStudyClient()
        from src.testing.compliant import CompliantAgentsClient

        return CompliantAgentsClient()
    if os.getenv("LITELLM_API_KEY") or os.getenv("OPENAI_API_KEY"):
        try:
            return build_client()
        except Exception as exc:  # noqa: BLE001
            raise ApiError(
                status_code=503,
                code="llm_unavailable",
                message=f"LLM provider unavailable: {type(exc).__name__}",
            ) from exc
    raise ApiError(
        status_code=503,
        code="llm_unavailable",
        message=(
            "LLM provider is not configured. Set LITELLM_API_KEY and "
            "LITELLM_BASE_URL in .env and restart the server."
        ),
    )


_DISPLAY_TYPES = {
    "mcq": "MCQ",
    "true_false": "True/False",
    "short_answer": "Short Answer",
}


def _display_type(raw: str) -> str:
    """Map an agent question-type value to the UI display label."""
    return _DISPLAY_TYPES.get((raw or "").lower(), raw)


def _resolve_model(requested: str | None) -> str:
    """Resolve the model id to send to the gateway.

    The UI ships provider placeholders ("mock" or bare vendor names such as
    "gemini" / "kimi") instead of full gateway model ids. There is no mock LLM
    on the backend, so any placeholder (no "/") falls back to the configured
    ``DEFAULT_MODEL`` (e.g. ``gemini/gemini-flash-lite-latest``).
    """
    if not requested or "/" not in requested:
        return default_model()
    return requested


def generate_questions_service(
    request: GenerateQuestionsRequest,
    *,
    db_path: str,
    chroma_dir: str,
    is_test_help: bool = False,
) -> GenerateQuestionsResponse:
    """Generate question bank or exam help grounded in workspace documents."""
    store = PlatformStore(db_path)

    # 1. Build grounded context
    query = (
        f"Key concepts difficulty {request.difficulty} types {','.join(request.types)}"
    )
    grounded = build_grounded_context(
        workspace_id=request.workspaceId,
        query=query,
        document_ids=request.documentIds if request.documentIds else None,
        chroma_dir=chroma_dir,
    )

    if not grounded.chunks:
        raise InsufficientGroundingError(
            "No indexed documents found in workspace to ground generation."
        )

    # 2. Invoke agent
    client = _get_llm_client(for_study=False)
    q_type = request.types[0] if request.types else "MCQ"
    content_text = grounded.as_prompt_content()

    if is_test_help:
        agent = TestHelpAgent(client=client, model=_resolve_model(request.model))
        output: QuestionBankOutput = agent.generate(
            content=content_text,
            question_type=q_type,
            difficulty=request.difficulty.lower(),
            num_questions=request.count,
        )
    else:
        agent = QuestionBankAgent(client=client, model=_resolve_model(request.model))
        output = agent.generate(
            content=content_text,
            question_type=q_type,
            difficulty=request.difficulty.lower(),
            num_questions=request.count,
        )

    # 3. Build per-question citations from each question's own grounded references.
    # The agent returns references per question, so citations must follow the
    # question rather than reusing one shared list for the whole request.
    chunk_by_id = {chunk.chunk.chunk_id: chunk for chunk in grounded.chunks}

    def _question_citations(q: QuestionItem) -> list[Citation]:
        """Map one question's agent references to the citation contract."""
        refs = getattr(q, "references", None) or []
        if not refs:
            # No per-question references: fall back to the retrieved context so
            # every question still shows where the material came from.
            return [
                Citation(
                    doc=(
                        chunk.chunk.chunk_id.split("-c")[0]
                        if "-c" in chunk.chunk.chunk_id
                        else chunk.chunk.chunk_id
                    ),
                    chunk=chunk.chunk.chunk_id,
                    snippet=chunk.chunk.text[:200],
                    score=round(chunk.score, 3),
                )
                for chunk in grounded.chunks
            ]

        result: list[Citation] = []
        for ref in refs:
            segment_id = ref.segment_id
            retrieved = chunk_by_id.get(segment_id)
            doc_id = segment_id.split("-c")[0] if "-c" in segment_id else segment_id
            snippet = ref.text or (retrieved.chunk.text if retrieved else "")
            result.append(
                Citation(
                    doc=doc_id,
                    chunk=segment_id,
                    snippet=snippet[:200],
                    score=round(retrieved.score, 3) if retrieved else 0.0,
                )
            )
        return result

    # 4. Support validation score
    support = validate_support(extract_claim_text(output), grounded)
    grounding_score = 100.0 if support.supported else 85.0
    quality_score = 9.2 if support.supported else 7.5

    questions: list[GeneratedQuestion] = []
    for idx, q in enumerate(output.questions, start=1):
        questions.append(
            GeneratedQuestion(
                id=f"q-{uuid4().hex[:8]}",
                prompt=q.question,
                type=_display_type(getattr(q, "type", "") or q_type),
                difficulty=request.difficulty,
                options=getattr(q, "options", None),
                answer=getattr(q, "correct_answer", "") or getattr(q, "answer", ""),
                rationale=getattr(q, "rationale", ""),
                bloom="Understanding",
                quality=quality_score,
                grounded=grounding_score,
                estMinutes=2,
                review="Pending",
                citations=_question_citations(q),
            )
        )

    # 5. Save AgentRun and GeneratedOutput to PlatformStore
    run = AgentRun(
        agent_name="test_help_agent" if is_test_help else "question_bank_agent",
        input_context=f"workspace:{request.workspaceId}",
        source_chunk_ids=grounded.chunk_ids,
        model=_resolve_model(request.model),
    )
    run.mark_finished()
    store.save_agent_run(run)

    gen_id = f"gen-{uuid4().hex[:8]}"
    gen_output = GeneratedOutput(
        id=gen_id,
        agent_run_id=run.id,
        output_type="question_bank",
        payload={"questions": [q.model_dump() for q in questions]},
        schema_name="QuestionBankOutput",
        validation_passed=support.supported,
        validation_report={
            "support": support.supported,
            "grounding_score": grounding_score,
        },
        status=OutputStatus.PENDING,
    )
    store.save_output(gen_output)

    # Auto-flag if thresholds not met
    if grounding_score < 98.0 or quality_score < 8.5:
        store.log_event(
            "auto_flagged",
            f"Output {gen_id} auto-flagged due to low grounding ({grounding_score}) or quality ({quality_score})",
            output_id=gen_id,
        )

    return GenerateQuestionsResponse(
        generationId=gen_id,
        kind="question_bank",
        grounding_score=grounding_score,
        quality_score=quality_score,
        questions=questions,
    )


def generate_flashcards_service(
    request: GenerateFlashcardsRequest,
    *,
    db_path: str,
    chroma_dir: str,
) -> GenerateFlashcardsResponse:
    """Generate flashcards grounded in workspace documents.

    When ``request.topic`` names a real topic (anything but "All chapters"),
    it becomes the retrieval query so the deck drills that specific material
    instead of the whole document. Every card carries its own citations built
    from the chunk id the model cited (or, as a fallback, the chunks whose
    text contains the card's source topic).
    """
    store = PlatformStore(db_path)
    topic = (request.topic or "").strip()
    query = (
        topic
        if topic and topic.lower() != "all chapters"
        else "flashcards key concepts definitions terms"
    )
    grounded = build_grounded_context(
        workspace_id=request.workspaceId,
        query=query,
        document_ids=request.documentIds if request.documentIds else None,
        chroma_dir=chroma_dir,
    )

    if not grounded.chunks:
        raise InsufficientGroundingError(
            "No indexed documents found in workspace to ground generation."
        )

    client = _get_llm_client(for_study=True)
    agent = FlashcardAgent(client=client, model=_resolve_model(request.model))

    content_text = grounded.as_prompt_content()
    card_set = agent.generate(
        content=content_text,
        card_format=request.cardFormat,
        card_count=request.count,
    )

    chunk_by_id = {c.chunk.chunk_id: c for c in grounded.chunks}

    def _card_citations(card: Flashcard) -> list[Citation]:
        """Map one card's cited chunk (or topic match) to citations."""
        chunk_id = card.source_chunk_id
        retrieved = chunk_by_id.get(chunk_id) if chunk_id else None
        if retrieved:
            doc_id = chunk_id.split("-c")[0] if "-c" in chunk_id else chunk_id
            return [
                Citation(
                    doc=doc_id,
                    chunk=chunk_id,
                    snippet=retrieved.chunk.text[:200],
                    score=round(retrieved.score, 3),
                )
            ]
        if not card.source_topic:
            return []
        needle = card.source_topic.lower()
        matched = [
            c
            for c in grounded.chunks
            if needle in c.chunk.text.lower()
        ]
        return [
            Citation(
                doc=(
                    c.chunk.chunk_id.split("-c")[0]
                    if "-c" in c.chunk.chunk_id
                    else c.chunk.chunk_id
                ),
                chunk=c.chunk.chunk_id,
                snippet=c.chunk.text[:200],
                score=round(c.score, 3),
            )
            for c in matched[:3]
        ]

    flashcards: list[WsFlashcard] = [
        WsFlashcard(
            front=card.front,
            back=card.back,
            tag=card.source_topic,
            format=card.format,
            topic=card.source_topic,
            sourceChunkId=card.source_chunk_id,
            citations=_card_citations(card),
        )
        for card in card_set.cards
    ]

    run = AgentRun(
        agent_name="flashcard_agent",
        input_context=f"workspace:{request.workspaceId}",
        source_chunk_ids=grounded.chunk_ids,
        model=_resolve_model(request.model),
    )
    run.mark_finished()
    store.save_agent_run(run)

    gen_id = f"gen-{uuid4().hex[:8]}"
    gen_output = GeneratedOutput(
        id=gen_id,
        agent_run_id=run.id,
        output_type="flashcards",
        payload={"flashcards": [f.model_dump() for f in flashcards]},
        schema_name="FlashcardSet",
        validation_passed=True,
        validation_report={"count": len(flashcards)},
        status=OutputStatus.PENDING,
    )
    store.save_output(gen_output)

    return GenerateFlashcardsResponse(
        generationId=gen_id,
        kind="flashcards",
        flashcards=flashcards,
    )


def flashcard_topics_service(
    request: FlashcardTopicsRequest,
    *,
    db_path: str,
    chroma_dir: str,
) -> FlashcardTopicsResponse:
    """Extract the real topic allow-list from the indexed document chunks.

    Uses the same deterministic :meth:`FlashcardAgent.extract_topics` heuristic
    the agent itself runs on the grounded content, so the topic selector in the
    studio is always in sync with what the PDF actually covers.
    """
    grounded = build_grounded_context(
        workspace_id=request.workspaceId,
        query="flashcards key concepts definitions terms",
        document_ids=request.documentIds if request.documentIds else None,
        chroma_dir=chroma_dir,
    )
    if not grounded.chunks:
        return FlashcardTopicsResponse(topics=[])

    content_text = grounded.as_prompt_content()
    topics = FlashcardAgent.extract_topics(content_text)
    return FlashcardTopicsResponse(topics=topics)


def generate_study_plan_service(
    request: GenerateStudyPlanRequest,
    *,
    db_path: str,
    chroma_dir: str,
) -> GenerateStudyPlanResponse:
    """Generate study plan grounded in workspace documents."""
    store = PlatformStore(db_path)
    grounded = build_grounded_context(
        workspace_id=request.workspaceId,
        query="study plan topics schedule breakdown",
        document_ids=request.documentIds if request.documentIds else None,
        chroma_dir=chroma_dir,
    )

    if not grounded.chunks:
        raise InsufficientGroundingError(
            "No indexed documents found in workspace to ground generation."
        )

    client = _get_llm_client(for_study=True)
    agent = StudyPlanAgent(client=client, model=_resolve_model(request.model))

    content_text = grounded.as_prompt_content()

    start = date.today()  # noqa: DTZ011
    if request.days:
        span_days = max(int(request.days), 1)
        is_day_based = True
        end = start + timedelta(days=span_days)
    else:
        weeks = max(request.weeks or 4, 1)
        span_days = weeks * 7
        is_day_based = span_days < 14
        end = start + timedelta(weeks=weeks)

    hours_per_week = request.hoursPerWeek or (
        (request.hoursPerDay or 2) * 7 if request.hoursPerDay is not None else 10.0
    )

    plan = agent.generate(
        content=content_text,
        start_date=start,
        end_date=end,
        learner_goal="Master workspace topics",
        difficulty="medium",
        hours_per_week=hours_per_week,
    )

    sections: list[StudyPlanSection] = []
    days: list[StudyPlanDay] = []

    for idx, item in enumerate(plan.topic_schedule, start=1):
        label = f"Day {idx}" if is_day_based else f"Week {(idx - 1) // 7 + 1}"
        sections.append(
            StudyPlanSection(
                title=f"{label}: {item.topic}",
                items=[f"Resource: {r}" for r in item.resources]
                or [f"Study {item.topic}"],
            )
        )
        days.append(
            StudyPlanDay(
                day=idx,
                topics=[item.topic],
                hours=item.duration_hours,
            )
        )

    run = AgentRun(
        agent_name="study_plan_agent",
        input_context=f"workspace:{request.workspaceId}",
        source_chunk_ids=grounded.chunk_ids,
        model=_resolve_model(request.model),
    )
    run.mark_finished()
    store.save_agent_run(run)

    gen_id = f"gen-{uuid4().hex[:8]}"
    gen_output = GeneratedOutput(
        id=gen_id,
        agent_run_id=run.id,
        output_type="study_plan",
        payload={"goal": plan.goal, "schedule": [s.model_dump() for s in sections]},
        schema_name="StudyPlan",
        validation_passed=True,
        validation_report={"days": len(days)},
        status=OutputStatus.PENDING,
    )
    store.save_output(gen_output)

    return GenerateStudyPlanResponse(
        generationId=gen_id,
        kind="study_plan",
        summary=(
            f"Structured {span_days}-day study plan for {plan.goal}"
            if is_day_based
            else f"Structured {weeks}-week study plan for {plan.goal}"
        ),
        sections=sections,
        days=days,
    )


def generate_revision_sheet_service(
    request: GenerateRevisionSheetRequest,
    *,
    db_path: str,
    chroma_dir: str,
) -> GenerateRevisionSheetResponse:
    """Generate revision sheet grounded in workspace documents."""
    store = PlatformStore(db_path)
    grounded = build_grounded_context(
        workspace_id=request.workspaceId,
        query="revision topics summary key ideas",
        document_ids=request.documentIds if request.documentIds else None,
        chroma_dir=chroma_dir,
    )

    if not grounded.chunks:
        raise InsufficientGroundingError(
            "No indexed documents found in workspace to ground generation."
        )

    client = _get_llm_client(for_study=True)
    agent = RevisionAgent(client=client, model=_resolve_model(request.model))

    content_text = grounded.as_prompt_content()
    extracted_topics = FlashcardAgent.extract_topics(content_text)
    topics = [t for t in (request.topics or []) if t in extracted_topics]
    if not topics:
        topics = extracted_topics[:3]
    if not topics:
        topics = ["Core Concept"]

    session = agent.generate(
        content=content_text,
        selected_topics=topics,
        session_date=date.today(),  # noqa: DTZ011
    )

    sections: list[StudyPlanSection] = []
    weak_topics: list[WeakTopic] = []

    for item in session.items:
        sections.append(
            StudyPlanSection(
                title=f"Revision: {item.topic}",
                items=[item.description, item.confidence_prompt],
            )
        )
        weak_topics.append(
            WeakTopic(
                topic=item.topic,
                strength=40 if item.difficulty == "hard" else 60,
                action=f"Review by {item.next_revision_date}",
                description=item.description,
                difficulty=item.difficulty,
                nextRevisionDate=str(item.next_revision_date),
                confidencePrompt=item.confidence_prompt,
            )
        )

    run = AgentRun(
        agent_name="revision_agent",
        input_context=f"workspace:{request.workspaceId}",
        source_chunk_ids=grounded.chunk_ids,
        model=_resolve_model(request.model),
    )
    run.mark_finished()
    store.save_agent_run(run)

    gen_id = f"gen-{uuid4().hex[:8]}"
    gen_output = GeneratedOutput(
        id=gen_id,
        agent_run_id=run.id,
        output_type="revision_sheet",
        payload={
            "notes": session.notes,
            "weak_topics": [w.model_dump() for w in weak_topics],
        },
        schema_name="RevisionSession",
        validation_passed=True,
        validation_report={"items": len(sections)},
        status=OutputStatus.PENDING,
    )
    store.save_output(gen_output)

    return GenerateRevisionSheetResponse(
        generationId=gen_id,
        kind="revision_sheet",
        summary=session.notes or "Revision session covering targeted topics.",
        sections=sections,
        weakTopics=weak_topics,
    )
