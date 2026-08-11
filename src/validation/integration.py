"""The end-to-end pipeline: ingest -> retrieve -> agents -> validate -> persist.

Each lane in this project works, and until now none of them were connected. This
module is the wiring: it takes uploaded material through ingestion, indexes it
for retrieval, grounds a query against it, runs the selected agents, validates
what they produce, and leaves everything in the store for a human to review.

It also carries the small **ingestion-to-retrieval bridge** the two lanes needed.
The two ``Chunk`` shapes were designed to line up and differ in one field name —
ingestion's ``id`` is retrieval's ``chunk_id`` — so the adapter is a rename plus
dropping the character offsets retrieval does not use.

Nothing here decides whether content is good; it decides what happens and in
what order. Judgement stays with the validator and, ultimately, the reviewer.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from src.ingestion.loader import ContentLoader
from src.ingestion.schema import Chunk as IngestionChunk
from src.ingestion.schema import Document
from src.ingestion.store import SQLiteStore
from src.retrieval.index import ChunkIndex
from src.retrieval.models import Chunk as RetrievalChunk
from src.retrieval.models import GroundedContext, RetrievalScope
from src.retrieval.retriever import ChromaRetriever, Retriever
from src.validation.orchestrator import Orchestrator, RunResult, build_default_agents
from src.validation.store import PlatformStore

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Ingestion -> retrieval bridge
# --------------------------------------------------------------------------- #


def to_retrieval_chunks(chunks: Iterable[IngestionChunk]) -> list[RetrievalChunk]:
    """Convert ingestion chunks into the retrieval lane's chunk records.

    The shapes already agree: ingestion emits ids in retrieval's
    ``{document_id}-c{ordinal:04d}`` convention with ``session_id`` threaded
    through, so this is a field rename (``id`` -> ``chunk_id``) and a drop of
    ``start_char`` / ``end_char``, which retrieval does not use.

    Chunks with blank text are skipped rather than raising: retrieval requires
    non-empty text, and one empty chunk should not fail an entire ingest.

    Args:
        chunks: Chunks as produced by the ingestion lane.

    Returns:
        The equivalent retrieval chunks, in input order.
    """
    converted: list[RetrievalChunk] = []
    for chunk in chunks:
        if not chunk.text or not chunk.text.strip():
            logger.warning("skipping blank chunk %s during indexing", chunk.id)
            continue
        converted.append(
            RetrievalChunk(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                session_id=chunk.session_id,
                ordinal=chunk.ordinal,
                text=chunk.text,
            )
        )
    return converted


def _saved_document_id(document: Document) -> str:
    """Return a saved document's id, failing loudly if it has none.

    ``Document.id`` is optional on the ingestion model because it is assigned at
    save time. Anything downstream of the store should have one, so a missing id
    is a bug worth surfacing rather than a ``None`` to thread onwards.
    """
    if not document.id:
        raise ValueError(
            f"Document {document.title!r} has no id after being saved; "
            "ingestion did not persist it."
        )
    return document.id


def index_document(
    document_id: str, ingestion_store: SQLiteStore, index: ChunkIndex
) -> int:
    """Load a document's stored chunks and index them for retrieval.

    Uses ``add_document`` replace semantics, so re-ingesting an edited document
    never leaves stale chunks behind.

    Args:
        document_id: The document to index.
        ingestion_store: Where the document's chunks were persisted.
        index: The retrieval index to populate.

    Returns:
        The number of chunks indexed.
    """
    chunks = to_retrieval_chunks(ingestion_store.get_chunks_by_document_id(document_id))
    if not chunks:
        logger.warning("document %s produced no indexable chunks", document_id)
        return 0
    index.add_document(document_id, chunks)
    return len(chunks)


# --------------------------------------------------------------------------- #
# The pipeline
# --------------------------------------------------------------------------- #


@dataclass
class PipelineResult:
    """What one end-to-end pipeline invocation produced.

    Attributes:
        query: The question the agents were asked.
        grounded_context: The retrieval payload they were given, if any.
        results: One :class:`RunResult` per agent, in request order.
        error: Set when the pipeline stopped before reaching the agents, e.g.
            because nothing relevant was retrievable in scope.
    """

    query: str
    grounded_context: GroundedContext | None = None
    results: list[RunResult] = field(default_factory=list)
    error: str | None = None

    @property
    def outputs(self) -> list[Any]:
        """Every generated output produced, skipping failed runs."""
        return [result.output for result in self.results if result.output is not None]

    @property
    def grounded(self) -> bool:
        """Whether the agents ran against retrieved content."""
        return self.grounded_context is not None and self.grounded_context.is_sufficient


@dataclass
class Pipeline:
    """Ingest, retrieve, generate, validate and persist, in one object.

    Args:
        loader: Ingestion entry point.
        index: Retrieval index over the ingested chunks.
        retriever: Search over the index.
        orchestrator: Runs agents and records what they produce.
        platform_store: Where runs, outputs and events are persisted.
    """

    loader: ContentLoader
    index: ChunkIndex
    retriever: Retriever
    orchestrator: Orchestrator
    platform_store: PlatformStore

    @classmethod
    def build(
        cls,
        *,
        db_path: str = "ingestion.db",
        index: ChunkIndex | None = None,
        client: Any | None = None,
        agents: dict[str, Any] | None = None,
        **orchestrator_options: Any,
    ) -> Pipeline:
        """Assemble a pipeline with the project's default components.

        Args:
            db_path: SQLite file shared by the ingestion and platform stores.
            index: An existing retrieval index; a fresh one is created if
                omitted.
            client: An OpenAI-compatible client shared by every agent.
                Defaults to one built from the configured gateway; tests
                inject a double.
            agents: Explicit agent registry, mainly for tests.
            **orchestrator_options: Passed through to :class:`Orchestrator`
                (retry policy and friends).

        Returns:
            A ready-to-use pipeline.
        """
        chunk_index = index if index is not None else ChunkIndex()
        platform_store = PlatformStore(db_path=db_path)
        return cls(
            loader=ContentLoader(db_path=db_path),
            index=chunk_index,
            retriever=ChromaRetriever(chunk_index),
            orchestrator=Orchestrator(
                platform_store,
                agents=agents
                if agents is not None
                else build_default_agents(client=client),
                **orchestrator_options,
            ),
            platform_store=platform_store,
        )

    # ------------------------------------------------------------------ #
    # Stages
    # ------------------------------------------------------------------ #

    def ingest_text(
        self, text: str, title: str = "Pasted Text", session_id: str | None = None
    ) -> Document:
        """Ingest raw text and index it for retrieval.

        Args:
            text: The material to ingest.
            title: Document title.
            session_id: Optional session scope propagated to the chunks.

        Returns:
            The saved document.
        """
        document = self.loader.load_text(text, title, session_id=session_id)
        indexed = index_document(
            _saved_document_id(document), self.loader.store, self.index
        )
        logger.info("ingested %r as %s (%d chunks)", title, document.id, indexed)
        return document

    def ingest_file(
        self, file_content: bytes, filename: str, session_id: str | None = None
    ) -> Document:
        """Ingest an uploaded file and index it for retrieval.

        Args:
            file_content: Raw file bytes.
            filename: Original filename, used for the title and type detection.
            session_id: Optional session scope propagated to the chunks.

        Returns:
            The saved document.
        """
        document = self.loader.load_file(file_content, filename, session_id=session_id)
        indexed = index_document(
            _saved_document_id(document), self.loader.store, self.index
        )
        logger.info("ingested %r as %s (%d chunks)", filename, document.id, indexed)
        return document

    def retrieve(
        self, query: str, scope: RetrievalScope, *, top_k: int | None = None
    ) -> GroundedContext:
        """Ground a query against the indexed material.

        Args:
            query: The learner's question.
            scope: The document and/or session to stay within.
            top_k: Optional result-count override.

        Returns:
            The grounded payload, which may be insufficient if nothing relevant
            exists in scope.
        """
        from src.retrieval.grounding import build_grounded_context

        return build_grounded_context(query, scope, self.retriever, top_k=top_k)

    def run(
        self,
        query: str,
        scope: RetrievalScope,
        agents: Sequence[str] | None = None,
        *,
        top_k: int | None = None,
        params: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> PipelineResult:
        """Run the full pipeline for one question.

        Retrieval that finds nothing in scope stops the pipeline before any
        agent is invoked — answering without grounding is exactly what this
        platform exists to prevent — and the reason is returned rather than
        raised.

        Args:
            query: The learner's question.
            scope: The document and/or session to stay within.
            agents: Which agents to run; defaults to every registered agent.
            top_k: Optional retrieval result-count override.
            params: Per-agent generation arguments, keyed by agent name.

        Returns:
            The :class:`PipelineResult`, including per-agent outcomes.
        """
        context = self.retrieve(query, scope, top_k=top_k)
        if not context.is_sufficient:
            message = (
                f"No content retrieved for {query!r} in scope {scope.to_where()}; "
                "agents were not run."
            )
            logger.warning(message)
            return PipelineResult(query=query, grounded_context=context, error=message)

        selected = list(agents) if agents is not None else self.orchestrator.agent_names
        results = self.orchestrator.run_agents(
            selected, grounded_context=context, params=params
        )
        return PipelineResult(query=query, grounded_context=context, results=results)

    def ingest_and_run(
        self,
        text: str,
        query: str,
        *,
        title: str = "Pasted Text",
        session_id: str | None = None,
        agents: Sequence[str] | None = None,
        params: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> PipelineResult:
        """Ingest material and immediately ask a question about it.

        The convenience path used by batch automation and the demo scenarios.

        Args:
            text: The material to ingest.
            query: The question to ask about it.
            title: Document title.
            session_id: Optional session scope.
            agents: Which agents to run; defaults to every registered agent.
            params: Per-agent generation arguments, keyed by agent name.

        Returns:
            The :class:`PipelineResult`.
        """
        document = self.ingest_text(text, title=title, session_id=session_id)
        return self.run(
            query,
            RetrievalScope(document_id=_saved_document_id(document)),
            agents,
            params=params,
        )
