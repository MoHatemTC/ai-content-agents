"""The grounding contract: (query + scope) -> grounded context with provenance.

:func:`build_grounded_context` is the single entry point agents (or the
orchestration layer) call to obtain a :class:`GroundedContext` — the payload
that keeps answers grounded in uploaded content. :func:`verify_references`
is the QA-side complement: it checks that the references an agent *cited*
were actually part of the retrieved context, so fabricated citations are
caught before review/export.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from src.retrieval.models import GroundedContext

if TYPE_CHECKING:
    from collections.abc import Sequence

    from src.retrieval.models import RetrievalScope
    from src.retrieval.retriever import Retriever
    from src.validation.schemas import ContentReference

logger = logging.getLogger(__name__)


def build_grounded_context(
    query: str,
    scope: RetrievalScope,
    retriever: Retriever,
    *,
    top_k: int | None = None,
) -> GroundedContext:
    """Build the grounded-context payload for a query within a scope.

    This is the grounding contract's producer side: the returned payload
    contains only chunks inside ``scope``, ranked by relevance, each
    carrying provenance (chunk id, document, session, ordinal). Consumers
    use :meth:`GroundedContext.as_prompt_content` for the prompt
    ``{content}`` block, :meth:`GroundedContext.to_content_references` for
    output citations, and :attr:`GroundedContext.chunk_ids` for
    ``AgentRun.source_chunk_ids``.

    Args:
        query: The user's question or search text.
        scope: The selected document/session to ground against.
        retriever: Any :class:`Retriever` implementation.
        top_k: Optional result-count override.

    Returns:
        The grounded payload; when nothing relevant exists in scope,
        ``is_sufficient`` is ``False`` and rendering a prompt from it
        raises :class:`~src.retrieval.models.InsufficientGroundingError`.
    """
    chunks = retriever.retrieve(query, scope, top_k=top_k)
    context = GroundedContext(query=query, scope=scope, chunks=chunks)
    if not context.is_sufficient:
        logger.info("No grounded content for query %r in scope %s", query, scope.to_where())
    return context


class GroundingVerification(BaseModel):
    """Result of checking cited references against a grounded context.

    Attributes:
        valid: ``True`` when every cited segment id was actually retrieved.
        unknown_segment_ids: Cited ids that were *not* part of the grounded
            context (in citation order) — fabricated or out-of-scope.
    """

    valid: bool
    unknown_segment_ids: list[str] = Field(default_factory=list)


def verify_references(
    references: Sequence[ContentReference],
    context: GroundedContext,
) -> GroundingVerification:
    """Check that cited references stay within the grounded context.

    Only citation *provenance* is verified (cited segment ids must be a
    subset of the retrieved chunk ids). Whether references are present at
    all is the ``ReferencesPresentRule`` guardrail's job, so an empty
    citation list is trivially valid here.

    Args:
        references: The ``references`` an agent produced.
        context: The grounded context that fed the agent.

    Returns:
        The verification result, listing any segment ids that were never
        retrieved.
    """
    known_ids = set(context.chunk_ids)
    unknown = [
        reference.segment_id
        for reference in references
        if reference.segment_id not in known_ids
    ]
    if unknown:
        logger.warning("Citations reference unknown segment ids: %s", unknown)
    return GroundingVerification(valid=not unknown, unknown_segment_ids=unknown)
