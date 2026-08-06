"""SQLite persistence for the review, orchestration and audit records.

:mod:`src.validation.review_schema` defines the domain contract as pure Pydantic
models with no storage; this module is the CRUD layer that makes them durable.
It owns four tables:

* ``agent_runs`` — one row per agent invocation, including failed ones,
* ``generated_outputs`` — one row per produced artifact and its current status,
* ``reviews`` — the **append-only** human audit trail, and
* ``system_events`` — the operational log behind the History page.

The store shares its database file with the ingestion lane
(:class:`src.ingestion.store.SQLiteStore`) by default, so documents, chunks,
runs, outputs and reviews all live in one file and provenance can be followed
end to end. Both stores use ``CREATE TABLE IF NOT EXISTS`` over disjoint table
names, so either may initialise the file first.

Writes deliberately expose **no update or delete method for reviews**: the audit
trail can only grow. Outputs and runs are written with ``INSERT OR REPLACE``
because both legitimately change (an output's status advances; a run gains its
``finished_at`` and outcome).
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime
from typing import Any

from src.validation.review_schema import (
    AgentRun,
    GeneratedOutput,
    OutputStatus,
    Review,
    ReviewAction,
    RunStatus,
    SystemEvent,
)

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = "ingestion.db"


def _dumps(value: Any) -> str:
    """Serialise a payload/report/id-list column to JSON text."""
    return json.dumps(value, default=str)


def _loads(raw: str | None, fallback: Any) -> Any:
    """Deserialise a JSON column, tolerating NULL and legacy blank values."""
    if not raw:
        return fallback
    return json.loads(raw)


class PlatformStore:
    """SQLite-backed storage for agent runs, outputs, reviews and events.

    Args:
        db_path: SQLite database file path. Defaults to the ``PLATFORM_DB_PATH``
            environment variable, falling back to the ingestion lane's
            ``ingestion.db`` so the whole pipeline shares one file.
    """

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path: str = db_path or os.getenv("PLATFORM_DB_PATH") or DEFAULT_DB_PATH
        self._init_db()

    # ------------------------------------------------------------------ #
    # Schema
    # ------------------------------------------------------------------ #

    def _connect(self) -> sqlite3.Connection:
        """Open a connection with foreign keys enforced."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        """Create the platform tables and indexes if they do not exist."""
        conn = self._connect()
        try:
            cursor = conn.cursor()

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_runs (
                    id TEXT PRIMARY KEY,
                    agent_name TEXT NOT NULL,
                    input_context TEXT,
                    source_chunk_ids TEXT NOT NULL,
                    prompt_ref TEXT,
                    model TEXT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    error TEXT
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS generated_outputs (
                    id TEXT PRIMARY KEY,
                    agent_run_id TEXT NOT NULL,
                    output_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    schema_name TEXT NOT NULL,
                    validation_passed INTEGER NOT NULL,
                    validation_report TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS reviews (
                    id TEXT PRIMARY KEY,
                    output_id TEXT NOT NULL,
                    reviewer TEXT NOT NULL,
                    action TEXT NOT NULL,
                    previous_status TEXT NOT NULL,
                    new_status TEXT NOT NULL,
                    edited_payload TEXT,
                    notes TEXT,
                    timestamp TEXT NOT NULL
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS system_events (
                    id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    run_id TEXT,
                    output_id TEXT,
                    details TEXT,
                    timestamp TEXT NOT NULL
                )
                """
            )

            for statement in (
                "CREATE INDEX IF NOT EXISTS idx_outputs_status "
                "ON generated_outputs (status)",
                "CREATE INDEX IF NOT EXISTS idx_outputs_run "
                "ON generated_outputs (agent_run_id)",
                "CREATE INDEX IF NOT EXISTS idx_reviews_output ON reviews (output_id)",
                "CREATE INDEX IF NOT EXISTS idx_events_type "
                "ON system_events (event_type)",
            ):
                cursor.execute(statement)

            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    # Agent runs
    # ------------------------------------------------------------------ #

    def save_agent_run(self, run: AgentRun) -> AgentRun:
        """Insert or update an agent run.

        Called twice per invocation in practice: once when the run starts and
        again when it finishes (or fails), so ``finished_at``/``status``/``error``
        land on the same row.

        Args:
            run: The run record to persist.

        Returns:
            The same run, unchanged.
        """
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO agent_runs (
                    id, agent_name, input_context, source_chunk_ids, prompt_ref,
                    model, started_at, finished_at, status, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.id,
                    run.agent_name,
                    run.input_context,
                    _dumps(run.source_chunk_ids),
                    run.prompt_ref,
                    run.model,
                    run.started_at.isoformat(),
                    run.finished_at.isoformat() if run.finished_at else None,
                    run.status.value,
                    run.error,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return run

    def get_agent_run(self, run_id: str) -> AgentRun | None:
        """Return one agent run by id, or ``None`` if it does not exist."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM agent_runs WHERE id = ?", (run_id,)
            ).fetchone()
        finally:
            conn.close()
        return self._row_to_run(row) if row else None

    def list_agent_runs(
        self,
        *,
        agent_name: str | None = None,
        status: RunStatus | None = None,
        limit: int | None = None,
    ) -> list[AgentRun]:
        """Return agent runs, newest first, optionally filtered.

        Args:
            agent_name: Restrict to one agent.
            status: Restrict to runs with this outcome.
            limit: Maximum number of rows to return.

        Returns:
            Matching runs ordered by ``started_at`` descending.
        """
        clauses: list[str] = []
        params: list[Any] = []
        if agent_name is not None:
            clauses.append("agent_name = ?")
            params.append(agent_name)
        if status is not None:
            clauses.append("status = ?")
            params.append(status.value)

        sql = "SELECT * FROM agent_runs"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY started_at DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)

        conn = self._connect()
        try:
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()
        return [self._row_to_run(row) for row in rows]

    @staticmethod
    def _row_to_run(row: tuple[Any, ...]) -> AgentRun:
        """Rebuild an :class:`AgentRun` from a database row."""
        return AgentRun(
            id=row[0],
            agent_name=row[1],
            input_context=row[2],
            source_chunk_ids=_loads(row[3], []),
            prompt_ref=row[4],
            model=row[5],
            started_at=datetime.fromisoformat(row[6]),
            finished_at=datetime.fromisoformat(row[7]) if row[7] else None,
            status=RunStatus(row[8]),
            error=row[9],
        )

    # ------------------------------------------------------------------ #
    # Generated outputs
    # ------------------------------------------------------------------ #

    def save_output(self, output: GeneratedOutput) -> GeneratedOutput:
        """Insert or update a generated output.

        Rewritten whenever a review advances the output's status or replaces its
        payload, so the row always reflects the current state while the
        ``reviews`` table keeps the history.

        Args:
            output: The output record to persist.

        Returns:
            The same output, unchanged.
        """
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO generated_outputs (
                    id, agent_run_id, output_type, payload, schema_name,
                    validation_passed, validation_report, status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    output.id,
                    output.agent_run_id,
                    output.output_type,
                    _dumps(output.payload),
                    output.schema_name,
                    int(output.validation_passed),
                    _dumps(output.validation_report),
                    output.status.value,
                    output.created_at.isoformat(),
                    output.updated_at.isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return output

    def get_output(self, output_id: str) -> GeneratedOutput | None:
        """Return one generated output by id, or ``None`` if it does not exist."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM generated_outputs WHERE id = ?", (output_id,)
            ).fetchone()
        finally:
            conn.close()
        return self._row_to_output(row) if row else None

    def list_outputs(
        self,
        *,
        status: OutputStatus | None = None,
        agent_run_id: str | None = None,
        agent_name: str | None = None,
        limit: int | None = None,
    ) -> list[GeneratedOutput]:
        """Return generated outputs, newest first, optionally filtered.

        Args:
            status: Restrict to one review status (e.g. the pending queue).
            agent_run_id: Restrict to the outputs of a single run.
            agent_name: Restrict to one agent, joining through ``agent_runs``.
            limit: Maximum number of rows to return.

        Returns:
            Matching outputs ordered by ``created_at`` descending.
        """
        clauses: list[str] = []
        params: list[Any] = []
        if status is not None:
            clauses.append("o.status = ?")
            params.append(status.value)
        if agent_run_id is not None:
            clauses.append("o.agent_run_id = ?")
            params.append(agent_run_id)
        if agent_name is not None:
            clauses.append(
                "o.agent_run_id IN (SELECT id FROM agent_runs WHERE agent_name = ?)"
            )
            params.append(agent_name)

        sql = "SELECT o.* FROM generated_outputs o"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY o.created_at DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)

        conn = self._connect()
        try:
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()
        return [self._row_to_output(row) for row in rows]

    @staticmethod
    def _row_to_output(row: tuple[Any, ...]) -> GeneratedOutput:
        """Rebuild a :class:`GeneratedOutput` from a database row."""
        return GeneratedOutput(
            id=row[0],
            agent_run_id=row[1],
            output_type=row[2],
            payload=_loads(row[3], {}),
            schema_name=row[4],
            validation_passed=bool(row[5]),
            validation_report=_loads(row[6], {}),
            status=OutputStatus(row[7]),
            created_at=datetime.fromisoformat(row[8]),
            updated_at=datetime.fromisoformat(row[9]),
        )

    # ------------------------------------------------------------------ #
    # Reviews (append-only)
    # ------------------------------------------------------------------ #

    def save_review(self, review: Review) -> Review:
        """Append one immutable review record to the audit trail.

        There is intentionally no counterpart to update or delete a review: the
        history of an output is reconstructed by reading its rows in timestamp
        order, and rewriting it would destroy the audit trail.

        Args:
            review: The review record produced by
                :func:`~src.validation.review_schema.apply_review`.

        Returns:
            The same review, unchanged.
        """
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO reviews (
                    id, output_id, reviewer, action, previous_status,
                    new_status, edited_payload, notes, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    review.id,
                    review.output_id,
                    review.reviewer,
                    review.action.value,
                    review.previous_status.value,
                    review.new_status.value,
                    _dumps(review.edited_payload)
                    if review.edited_payload is not None
                    else None,
                    review.notes,
                    review.timestamp.isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return review

    def list_reviews(self, output_id: str | None = None) -> list[Review]:
        """Return review records in chronological order.

        Args:
            output_id: Restrict to one output's history; omit for every review.

        Returns:
            Matching reviews ordered by ``timestamp`` ascending, so the list
            reads as the story of the output.
        """
        sql = "SELECT * FROM reviews"
        params: list[Any] = []
        if output_id is not None:
            sql += " WHERE output_id = ?"
            params.append(output_id)
        sql += " ORDER BY timestamp ASC"

        conn = self._connect()
        try:
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()

        return [
            Review(
                id=row[0],
                output_id=row[1],
                reviewer=row[2],
                action=ReviewAction(row[3]),
                previous_status=OutputStatus(row[4]),
                new_status=OutputStatus(row[5]),
                edited_payload=_loads(row[6], None),
                notes=row[7],
                timestamp=datetime.fromisoformat(row[8]),
            )
            for row in rows
        ]

    # ------------------------------------------------------------------ #
    # System events
    # ------------------------------------------------------------------ #

    def log_event(
        self,
        event_type: str,
        message: str,
        *,
        run_id: str | None = None,
        output_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> SystemEvent:
        """Record one operational event and return it.

        Args:
            event_type: One of the constants in :mod:`src.validation.history`.
            message: Human-readable summary shown on the History page.
            run_id: Related agent run, when the event belongs to one.
            output_id: Related generated output, when the event belongs to one.
            details: Arbitrary structured context stored as JSON.

        Returns:
            The persisted :class:`SystemEvent`.
        """
        event = SystemEvent(
            event_type=event_type,
            message=message,
            run_id=run_id,
            output_id=output_id,
            details=details or {},
        )
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO system_events (
                    id, event_type, message, run_id, output_id, details, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.event_type,
                    event.message,
                    event.run_id,
                    event.output_id,
                    _dumps(event.details),
                    event.timestamp.isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()
        logger.info("event: %s %s", event.event_type, event.message)
        return event

    def list_events(
        self,
        *,
        event_type: str | None = None,
        run_id: str | None = None,
        output_id: str | None = None,
        limit: int | None = None,
    ) -> list[SystemEvent]:
        """Return logged events, newest first, optionally filtered.

        Args:
            event_type: Restrict to one event type.
            run_id: Restrict to events belonging to one run.
            output_id: Restrict to events belonging to one output.
            limit: Maximum number of rows to return.

        Returns:
            Matching events ordered by ``timestamp`` descending.
        """
        clauses: list[str] = []
        params: list[Any] = []
        for column, value in (
            ("event_type", event_type),
            ("run_id", run_id),
            ("output_id", output_id),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                params.append(value)

        sql = "SELECT * FROM system_events"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY timestamp DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)

        conn = self._connect()
        try:
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()

        return [
            SystemEvent(
                id=row[0],
                event_type=row[1],
                message=row[2],
                run_id=row[3],
                output_id=row[4],
                details=_loads(row[5], {}),
                timestamp=datetime.fromisoformat(row[6]),
            )
            for row in rows
        ]
