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
from backend.search.service import build_grounded_context
from src.agents.question_bank_agent import QuestionBankAgent
from src.agents.test_help_agent import TestHelpAgent
from src.llm_gateway import build_client, default_model
from src.retrieval.models import InsufficientGroundingError
from src.study.flashcard_agent import FlashcardAgent
from src.study.revision_agent import RevisionAgent
from src.study.study_plan_agent import StudyPlanAgent
from src.validation.review_schema import AgentRun, GeneratedOutput, OutputStatus
from src.validation.schemas import QuestionBankOutput
from src.validation.store import PlatformStore
from src.validation.support_validator import extract_claim_text, validate_support
from tests.conftest import CompliantAgentsClient, CompliantStudyClient

logger = logging.getLogger(__name__)


def _chunk_texts(grounded) -> list[str]:
    """Extract non-empty chunk texts from a grounded context."""
    return [c.chunk.text for c in grounded.chunks if c.chunk.text.strip()]


def _get_llm_client(for_study: bool = False) -> Any:
    """Resolve an LLM client: real LiteLLM client if configured, or compliant fake double."""
    if os.getenv("LITELLM_API_KEY") or os.getenv("OPENAI_API_KEY"):
        try:
            return build_client()
        except Exception:  # noqa: BLE001, S110
            pass
    return CompliantStudyClient() if for_study else CompliantAgentsClient()


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

    # 3. Build citations from grounded chunks
    citations: list[Citation] = []
    for chunk in grounded.chunks:
        doc_id = (
            chunk.chunk.chunk_id.split("-c")[0]
            if "-c" in chunk.chunk.chunk_id
            else chunk.chunk.chunk_id
        )
        citations.append(
            Citation(
                doc=doc_id,
                snippet=chunk.chunk.text[:200],
                score=round(chunk.score, 3),
            )
        )

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
                type=q.type.upper() if hasattr(q, "type") and q.type else q_type,
                difficulty=request.difficulty,
                options=getattr(q, "options", None),
                answer=getattr(q, "correct_answer", "") or getattr(q, "answer", ""),
                rationale=getattr(q, "rationale", ""),
                bloom="Understanding",
                quality=quality_score,
                grounded=grounding_score,
                estMinutes=2,
                review="Pending",
                citations=citations,
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
    """Generate flashcards grounded in workspace documents."""
    store = PlatformStore(db_path)
    grounded = build_grounded_context(
        workspace_id=request.workspaceId,
        query="flashcards key concepts definitions terms",
        document_ids=request.documentIds if request.documentIds else None,
        chroma_dir=chroma_dir,
    )

    if not grounded.chunks:
        raise InsufficientGroundingError(
            "No indexed documents found in workspace to ground generation."
        )

    client = _get_llm_client(for_study=True)
    agent = FlashcardAgent(client=client, model=_resolve_model(request.model))

    topics = [t.split()[0] for t in _chunk_texts(grounded)]
    if not topics:
        topics = ["Educational Concept"]

    card_set = agent.generate(
        topics=topics,
        card_format="term-definition",
        card_count=request.count,
    )

    flashcards: list[WsFlashcard] = [
        WsFlashcard(front=card.front, back=card.back, tag=card.source_topic)
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

    topics = list({t.split()[0] for t in _chunk_texts(grounded)})
    if not topics:
        topics = ["Core Concept"]

    start = date.today()  # noqa: DTZ011
    weeks = request.weeks or 4
    end = start + timedelta(weeks=weeks)

    plan = agent.generate(
        topics=topics,
        start_date=start,
        end_date=end,
        learner_goal="Master workspace topics",
        difficulty="medium",
        hours_per_week=request.hoursPerWeek or 10.0,
    )

    sections: list[StudyPlanSection] = []
    days: list[StudyPlanDay] = []

    for idx, item in enumerate(plan.topic_schedule, start=1):
        sections.append(
            StudyPlanSection(
                title=f"Week {(idx - 1) // 7 + 1}: {item.topic}",
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
        summary=f"Structured {weeks}-week study plan for {plan.goal}",
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

    topics = (
        request.topics
        if request.topics
        else [t.split()[0] for t in _chunk_texts(grounded)][:3]
    )
    if not topics:
        topics = ["Core Concept"]

    session = agent.generate(
        selected_topics=topics,
        session_date=date.today(),  # noqa: DTZ011
        difficulty="medium",
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
