from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agents.concept_agent import ConceptAgent
from src.agents.mentor_agent import MentorAgent
from src.evaluation.benchmark import BenchmarkInput, run_benchmark
from src.retrieval.models import Chunk, GroundedContext, RetrievedChunk, RetrievalScope
from tests.conftest import CompliantAgentsClient


def _context(*, chunk_id: str, text: str) -> GroundedContext:
    return GroundedContext(
        query="loops",
        scope=RetrievalScope(document_id="doc-1"),
        chunks=[
            RetrievedChunk(
                chunk=Chunk(
                    chunk_id=chunk_id,
                    document_id="doc-1",
                    ordinal=0,
                    text=text,
                ),
                score=1.0,
                rank=1,
            )
        ],
    )


def _print_report(*, label: str, report) -> None:
    print(label, json.dumps(report.summary.model_dump(), indent=2, sort_keys=True))


def main() -> None:
    grounded_context = _context(
        chunk_id="chunk-grounded",
        text="Python has for and while loops.",
    )
    grounded_inputs = [
        BenchmarkInput(
            content="content",
            user_question="Explain loops.",
            difficulty="beginner",
            context=grounded_context,
        ),
        BenchmarkInput(
            content="content",
            user_question="Explain while loops.",
            difficulty="intermediate",
            context=grounded_context,
        ),
        BenchmarkInput(
            content="content",
            user_question="Explain for loops.",
            difficulty="advanced",
            context=grounded_context,
        ),
    ]
    difficulty_inputs = [
        BenchmarkInput(
            content="Python has for and while loops.",
            user_question="Explain loops.",
            difficulty="beginner",
        ),
        BenchmarkInput(
            content="Python has for and while loops.",
            user_question="Explain loops.",
            difficulty="intermediate",
        ),
        BenchmarkInput(
            content="Python has for and while loops.",
            user_question="Explain loops.",
            difficulty="advanced",
        ),
    ]

    mentor_agent = MentorAgent(client=CompliantAgentsClient())
    mentor_grounded = run_benchmark(mentor_agent, grounded_inputs)
    mentor_difficulty = run_benchmark(mentor_agent, difficulty_inputs)
    _print_report(label="MENTOR_GROUNDED_BENCHMARK", report=mentor_grounded)
    _print_report(label="MENTOR_DIFFICULTY_BENCHMARK", report=mentor_difficulty)

    concept_agent = ConceptAgent(client=CompliantAgentsClient())
    concept_grounded = run_benchmark(concept_agent, grounded_inputs)
    concept_difficulty = run_benchmark(concept_agent, difficulty_inputs)
    _print_report(label="CONCEPT_GROUNDED_BENCHMARK", report=concept_grounded)
    _print_report(label="CONCEPT_DIFFICULTY_BENCHMARK", report=concept_difficulty)


if __name__ == "__main__":
    main()
