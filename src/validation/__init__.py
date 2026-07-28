"""Review, validation, orchestration and export — the platform layer.

This package owns everything between "an agent produced something" and "a human
released it": the review contract and its export gate, the validator and its
guardrails, the orchestrator that runs agents and records what they did, the
persistence behind all of it, and the evaluation that measures the result.

The load-bearing rule is one line: nothing an agent generates reaches a user
until a person approves it, and :func:`assert_exportable` is the only thing that
decides. See ``docs/validation-lane.md`` for the full contract.

Typical use::

    from src.validation import Pipeline, ReviewService

    pipeline = Pipeline.build()
    result = pipeline.ingest_and_run(notes, "what is newton's second law")

    review = ReviewService(pipeline.platform_store)
    review.approve(result.outputs[0].id, "nour")

``ui`` is deliberately not re-exported, so importing this package never pulls
Streamlit into a process that only needs the services.
"""

from src.validation.evaluation import AgentMetrics, EvaluationHarness, EvaluationReport
from src.validation.guardrails import (
    DEFAULT_RULES,
    GroundedReferencesRule,
    GuardrailContext,
    GuardrailRule,
    GuardrailViolation,
    NonEmptyTextRule,
    ReferencesPresentRule,
    Severity,
)
from src.validation.history import EVENT_TYPES, HistoryService
from src.validation.integration import Pipeline, PipelineResult, to_retrieval_chunks
from src.validation.orchestrator import AgentSpec, Orchestrator, RunResult
from src.validation.review_schema import (
    AgentRun,
    ExportBlockedError,
    GeneratedOutput,
    IllegalTransitionError,
    OutputStatus,
    Review,
    ReviewAction,
    RunStatus,
    SystemEvent,
    apply_review,
    assert_exportable,
    is_legal_transition,
)
from src.validation.review_service import OutputNotFoundError, ReviewService
from src.validation.store import PlatformStore
from src.validation.validator_base import (
    ValidationResult,
    ValidatorBase,
    build_generated_output,
)

__all__ = [
    "DEFAULT_RULES",
    "EVENT_TYPES",
    "AgentMetrics",
    "AgentRun",
    "AgentSpec",
    "EvaluationHarness",
    "EvaluationReport",
    "ExportBlockedError",
    "GeneratedOutput",
    "GroundedReferencesRule",
    "GuardrailContext",
    "GuardrailRule",
    "GuardrailViolation",
    "HistoryService",
    "IllegalTransitionError",
    "NonEmptyTextRule",
    "Orchestrator",
    "OutputNotFoundError",
    "OutputStatus",
    "Pipeline",
    "PipelineResult",
    "PlatformStore",
    "ReferencesPresentRule",
    "Review",
    "ReviewAction",
    "ReviewService",
    "RunResult",
    "RunStatus",
    "Severity",
    "SystemEvent",
    "ValidationResult",
    "ValidatorBase",
    "apply_review",
    "assert_exportable",
    "build_generated_output",
    "is_legal_transition",
    "to_retrieval_chunks",
]
