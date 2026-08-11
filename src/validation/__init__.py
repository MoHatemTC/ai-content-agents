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

**Names are resolved lazily.** This package and ``src.retrieval`` genuinely
depend on each other — retrieval's models cite ``ContentReference`` from
``src.validation.schemas``, and this package's grounding guardrail calls
retrieval's ``verify_references``. Importing submodules eagerly here would make
``import src.retrieval`` fail with a partially-initialised-module error, because
loading the leaf ``src.validation.schemas`` would drag the whole package (and
therefore retrieval, again) in with it. Lazy attribute access keeps the
convenient flat API without forcing that load. ``ui`` is deliberately absent, so
importing this package never pulls in Streamlit.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # Static analysers get the real names; runtime stays lazy.
    from src.exports import ExportFormat
    from src.validation.evaluation import (
        AgentMetrics,
        EvaluationHarness,
        EvaluationReport,
    )
    from src.validation.guardrails import (
        DEFAULT_RULES,
        GuardrailContext,
        GuardrailRule,
        GuardrailViolation,
        NonEmptyTextRule,
        ReferencesPresentRule,
        Severity,
    )
    from src.validation.history import EVENT_TYPES, HistoryService
    from src.validation.integration import (
        Pipeline,
        PipelineResult,
        to_retrieval_chunks,
    )
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
    from src.validation.support_validator import (
        SupportValidationResult,
        extract_claim_text,
        validate_support,
    )
    from src.validation.validator_base import (
        ValidationResult,
        ValidatorBase,
        build_generated_output,
    )

# Public name -> the module that defines it.
_EXPORTS: dict[str, str] = {
    "AgentMetrics": "src.validation.evaluation",
    "EvaluationHarness": "src.validation.evaluation",
    "EvaluationReport": "src.validation.evaluation",
    "DEFAULT_RULES": "src.validation.guardrails",
    "PlatformGroundingRule": "src.validation.grounding_rule",
    "GuardrailContext": "src.validation.guardrails",
    "GuardrailRule": "src.validation.guardrails",
    "GuardrailViolation": "src.validation.guardrails",
    "NonEmptyTextRule": "src.validation.guardrails",
    "ReferencesPresentRule": "src.validation.guardrails",
    "Severity": "src.validation.guardrails",
    "EVENT_TYPES": "src.validation.history",
    "HistoryService": "src.validation.history",
    "Pipeline": "src.validation.integration",
    "PipelineResult": "src.validation.integration",
    "to_retrieval_chunks": "src.validation.integration",
    "AgentSpec": "src.validation.orchestrator",
    "Orchestrator": "src.validation.orchestrator",
    "RunResult": "src.validation.orchestrator",
    "AgentRun": "src.validation.review_schema",
    "ExportBlockedError": "src.validation.review_schema",
    "GeneratedOutput": "src.validation.review_schema",
    "IllegalTransitionError": "src.validation.review_schema",
    "OutputStatus": "src.validation.review_schema",
    "Review": "src.validation.review_schema",
    "ReviewAction": "src.validation.review_schema",
    "RunStatus": "src.validation.review_schema",
    "SystemEvent": "src.validation.review_schema",
    "apply_review": "src.validation.review_schema",
    "assert_exportable": "src.validation.review_schema",
    "is_legal_transition": "src.validation.review_schema",
    "OutputNotFoundError": "src.validation.review_service",
    "ReviewService": "src.validation.review_service",
    "PlatformStore": "src.validation.store",
    "SupportValidationResult": "src.validation.support_validator",
    "extract_claim_text": "src.validation.support_validator",
    "validate_support": "src.validation.support_validator",
    "ValidationResult": "src.validation.validator_base",
    "ValidatorBase": "src.validation.validator_base",
    "build_generated_output": "src.validation.validator_base",
    "ExportFormat": "src.exports",
}

# Spelled out rather than derived from _EXPORTS so static analysers can see the
# re-exports. `test_public_api_lists_agree` keeps the two in step.
__all__ = [
    "DEFAULT_RULES",
    "EVENT_TYPES",
    "AgentMetrics",
    "AgentRun",
    "AgentSpec",
    "EvaluationHarness",
    "EvaluationReport",
    "ExportBlockedError",
    "ExportFormat",
    "GeneratedOutput",
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
    "PlatformGroundingRule",
    "PlatformStore",
    "ReferencesPresentRule",
    "Review",
    "ReviewAction",
    "ReviewService",
    "RunResult",
    "RunStatus",
    "Severity",
    "SupportValidationResult",
    "SystemEvent",
    "ValidationResult",
    "ValidatorBase",
    "apply_review",
    "assert_exportable",
    "build_generated_output",
    "extract_claim_text",
    "is_legal_transition",
    "to_retrieval_chunks",
    "validate_support",
]


def __getattr__(name: str) -> Any:
    """Resolve a public name by importing its module on first access (PEP 562).

    Args:
        name: The attribute being looked up on the package.

    Returns:
        The requested object.

    Raises:
        AttributeError: If ``name`` is not part of the public API.
    """
    module_path = _EXPORTS.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module(module_path), name)


def __dir__() -> list[str]:
    """List the package's public API for tab-completion and ``dir()``."""
    return list(__all__)
