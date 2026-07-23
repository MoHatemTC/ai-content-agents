"""Data models for the retrieval lane.

Defines the ingestion-side :class:`Chunk` record, the :class:`RetrievalScope`
that pins every retrieval to a selected document and/or session, the ranked
:class:`RetrievedChunk` result, and the :class:`GroundedContext` payload that
agents consume. ``GroundedContext`` bridges retrieval into the shared
contracts other lanes already expect: prompt ``{content}`` blocks,
:class:`~src.validation.schemas.ContentReference` citations, and
``AgentRun.source_chunk_ids`` provenance.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from src.validation.schemas import ContentReference


class InsufficientGroundingError(RuntimeError):
    """Raised when a grounded payload is requested but no chunks were retrieved.

    Guarantees an agent can never be silently invoked with empty grounding:
    callers must either handle this error or check
    :attr:`GroundedContext.is_sufficient` first.
    """


class Chunk(BaseModel):
    """One ingested segment of an uploaded document.

    Attributes:
        chunk_id: Stable citation id, ``f"{document_id}-c{ordinal:04d}"`` by
            convention (the splitter enforces it; external ingestion may
            supply its own stable ids).
        document_id: Id of the source document.
        session_id: Optional owning session for session-scoped retrieval.
        ordinal: 0-based position of the chunk within its document.
        text: The chunk's textual content.
    """

    chunk_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    session_id: str | None = None
    ordinal: int = Field(ge=0)
    text: str = Field(min_length=1)


class RetrievalScope(BaseModel):
    """The document/session selection a retrieval is confined to.

    At least one of ``document_id`` / ``session_id`` must be set — an
    unscoped retrieval is a :class:`pydantic.ValidationError`, which makes
    out-of-scope leakage structurally impossible rather than a convention.
    """

    document_id: str | None = None
    session_id: str | None = None

    @model_validator(mode="after")
    def _require_some_scope(self) -> RetrievalScope:
        """Reject a scope with neither document nor session selected."""
        if self.document_id is None and self.session_id is None:
            raise ValueError(
                "RetrievalScope requires document_id and/or session_id; "
                "unscoped retrieval is not allowed"
            )
        return self

    def to_where(self) -> dict[str, object]:
        """Build the Chroma ``where`` filter enforcing this scope.

        Returns:
            A metadata filter: a single equality clause when one field is
            set, or an ``$and`` of both clauses when both are set.
        """
        clauses: list[dict[str, object]] = []
        if self.document_id is not None:
            clauses.append({"document_id": self.document_id})
        if self.session_id is not None:
            clauses.append({"session_id": self.session_id})
        if len(clauses) == 1:
            return clauses[0]
        return {"$and": clauses}


class RetrievedChunk(BaseModel):
    """A chunk returned by retrieval, with its relevance score and rank.

    Attributes:
        chunk: The retrieved chunk record.
        score: Cosine similarity of the chunk to the query (``1 - distance``).
        rank: 1-based position in the result list (1 = most relevant).
    """

    chunk: Chunk
    score: float
    rank: int = Field(ge=1)


class GroundedContext(BaseModel):
    """The grounded-context payload agents consume.

    The grounding contract: given a query and a scope, this payload carries
    only in-scope chunks, ranked, with full provenance. Consumers use it
    three ways:

    - :meth:`as_prompt_content` fills the ``{content}`` placeholder in the
      agent prompt templates,
    - :meth:`to_content_references` produces the ``references`` field of
      agent outputs (satisfying the ``ReferencesPresentRule`` guardrail),
    - :attr:`chunk_ids` feeds ``AgentRun.source_chunk_ids`` so reviewers can
      trace any answer back to the exact ingested chunks.
    """

    query: str
    scope: RetrievalScope
    chunks: list[RetrievedChunk] = Field(default_factory=list)

    @property
    def is_sufficient(self) -> bool:
        """Whether any grounding content was retrieved at all."""
        return len(self.chunks) > 0

    @property
    def chunk_ids(self) -> list[str]:
        """Retrieved chunk ids in rank order (``AgentRun.source_chunk_ids``)."""
        return [retrieved.chunk.chunk_id for retrieved in self.chunks]

    def to_content_references(self) -> list[ContentReference]:
        """Convert retrieved chunks into shared-contract citation objects.

        Returns:
            One :class:`ContentReference` per chunk, in rank order, with
            ``segment_id`` set to the chunk id.
        """
        return [
            ContentReference(segment_id=retrieved.chunk.chunk_id, text=retrieved.chunk.text)
            for retrieved in self.chunks
        ]

    def as_prompt_content(self) -> str:
        """Render the payload as the ``{content}`` block for agent prompts.

        Each chunk renders as a ``[chunk_id]`` marker line followed by its
        text, so the model can cite the stable ids the prompts ask for.
        Chunk text is inserted verbatim: ``str.format`` does not re-process
        substituted values, so braces in content are safe unescaped.

        Returns:
            The rendered content block.

        Raises:
            InsufficientGroundingError: If no chunks were retrieved.
        """
        if not self.chunks:
            raise InsufficientGroundingError(
                f"No grounded content retrieved for query {self.query!r}; "
                "refusing to build an ungrounded prompt"
            )
        return "\n\n".join(
            f"[{retrieved.chunk.chunk_id}]\n{retrieved.chunk.text}" for retrieved in self.chunks
        )
