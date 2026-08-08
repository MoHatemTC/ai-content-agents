"""Export approved outputs to JSON, CSV, Markdown or PDF.

Every function here runs the human-review gate
(:func:`~src.validation.review_schema.assert_exportable`) over **every** output
before writing a single byte. That ordering is the whole design: a partial file
containing some approved content and then an error is worse than no file, and it
means there is no code path — single, bulk or per-format — that can release
content a human has not explicitly approved.

:func:`export_approved_run` additionally filters by status when reading from the
store, but the gate still runs afterwards. The query is a convenience; the gate
is the invariant.

Formats are deliberately plain: JSON for machines, CSV for spreadsheets,
Markdown for reading and pasting, PDF for handing to someone. None of them are a
re-modelling of the payload — they render whatever the agent produced and the
reviewer approved.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from collections.abc import Sequence
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from src.validation.history import EXPORT_BLOCKED, EXPORT_COMPLETED
from src.validation.review_schema import (
    ExportBlockedError,
    GeneratedOutput,
    OutputStatus,
    assert_exportable,
)
from src.validation.store import PlatformStore
from src.retrieval.models import describe_chunk_id

logger = logging.getLogger(__name__)


class ExportFormat(str, Enum):
    """A supported export format, with the metadata a download needs."""

    JSON = "json"
    CSV = "csv"
    MARKDOWN = "markdown"
    PDF = "pdf"

    @property
    def extension(self) -> str:
        """File extension for this format, without the dot."""
        return {
            ExportFormat.JSON: "json",
            ExportFormat.CSV: "csv",
            ExportFormat.MARKDOWN: "md",
            ExportFormat.PDF: "pdf",
        }[self]

    @property
    def media_type(self) -> str:
        """MIME type, for HTTP responses and Streamlit download buttons."""
        return {
            ExportFormat.JSON: "application/json",
            ExportFormat.CSV: "text/csv",
            ExportFormat.MARKDOWN: "text/markdown",
            ExportFormat.PDF: "application/pdf",
        }[self]


class ExportFormatUnavailableError(RuntimeError):
    """Raised when a format's optional dependency is not installed."""


def export_outputs(
    outputs: Sequence[GeneratedOutput],
    export_format: ExportFormat | str,
    *,
    title: str = "Approved study content",
    store: PlatformStore | None = None,
) -> bytes:
    """Render approved outputs in the requested format.

    Args:
        outputs: The outputs to export. Every one must already be approved.
        export_format: Target format, as an :class:`ExportFormat` or its value.
        title: Heading used by the Markdown and PDF renderers.
        store: When given, export attempts are recorded to the event log.

    Returns:
        The rendered document as bytes, ready to write or download.

    Raises:
        ExportBlockedError: If **any** output is not approved. Nothing is
            written in that case.
        ExportFormatUnavailableError: If the format needs a dependency that is
            not installed.
        ValueError: If ``export_format`` is not a supported format.
    """
    target = ExportFormat(export_format)

    # The gate, before any rendering: all or nothing.
    try:
        for output in outputs:
            assert_exportable(output)
    except ExportBlockedError as exc:
        if store is not None:
            store.log_event(
                EXPORT_BLOCKED,
                f"Export blocked: output is {exc.status.value}, not approved",
                output_id=exc.output_id,
                details={"format": target.value, "status": exc.status.value},
            )
        raise

    data = _RENDERERS[target](outputs, title)

    if store is not None:
        store.log_event(
            EXPORT_COMPLETED,
            f"Exported {len(outputs)} approved output(s) as {target.value}",
            details={"format": target.value, "count": len(outputs)},
        )
    logger.info("exported %d output(s) as %s", len(outputs), target.value)
    return data


def export_output(
    output: GeneratedOutput,
    export_format: ExportFormat | str,
    *,
    store: PlatformStore | None = None,
) -> bytes:
    """Render a single approved output.

    Args:
        output: The output to export; must be approved.
        export_format: Target format.
        store: When given, export attempts are recorded to the event log.

    Returns:
        The rendered document as bytes.

    Raises:
        ExportBlockedError: If the output is not approved.
    """
    return export_outputs([output], export_format, store=store)


def export_approved_run(
    run_id: str,
    export_format: ExportFormat | str,
    store: PlatformStore,
    *,
    title: str | None = None,
) -> bytes:
    """Export everything approved from one agent run.

    Args:
        run_id: The run whose outputs to export.
        export_format: Target format.
        store: Store to read the outputs from and log the export to.
        title: Heading override for Markdown and PDF.

    Returns:
        The rendered document as bytes. A run with nothing approved yet exports
        an empty document rather than failing — there is simply nothing to
        release.
    """
    outputs = store.list_outputs(agent_run_id=run_id, status=OutputStatus.APPROVED)
    return export_outputs(
        outputs,
        export_format,
        title=title or f"Approved outputs for run {run_id}",
        store=store,
    )


# --------------------------------------------------------------------------- #
# Renderers
# --------------------------------------------------------------------------- #


def _now_iso() -> str:
    """Return the current UTC timestamp as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _render_json(outputs: Sequence[GeneratedOutput], title: str) -> bytes:
    """Render the full output records as a JSON document."""
    document = {
        "title": title,
        "exported_at": _now_iso(),
        "count": len(outputs),
        "outputs": [output.model_dump(mode="json") for output in outputs],
    }
    return json.dumps(document, indent=2, ensure_ascii=False).encode("utf-8")


# Scalar columns written to CSV, in order. The payload follows as JSON, because
# agent payloads are nested and differently shaped per agent - flattening them
# into columns would produce a different header for every export.
_CSV_COLUMNS = (
    "id",
    "agent_run_id",
    "output_type",
    "schema_name",
    "status",
    "validation_passed",
    "created_at",
    "updated_at",
)


def _render_csv(outputs: Sequence[GeneratedOutput], title: str) -> bytes:
    """Render one row per output, with the payload as a JSON column."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow([*_CSV_COLUMNS, "payload"])
    for output in outputs:
        record = output.model_dump(mode="json")
        writer.writerow(
            [record[column] for column in _CSV_COLUMNS]
            + [json.dumps(record["payload"], ensure_ascii=False)]
        )
    return buffer.getvalue().encode("utf-8")


def _render_markdown(outputs: Sequence[GeneratedOutput], title: str) -> bytes:
    """Render a readable document, one section per output."""
    lines = [f"# {title}", "", f"Exported {_now_iso()} — {len(outputs)} output(s).", ""]

    for index, output in enumerate(outputs, start=1):
        lines += [
            f"## {index}. {output.output_type} ({output.schema_name})",
            "",
            f"- **Output id:** `{output.id}`",
            f"- **Run id:** `{output.agent_run_id}`",
            f"- **Status:** {output.status.value}",
            f"- **Validation:** {'passed' if output.validation_passed else 'failed'}",
            "",
            *_payload_lines(output.payload),
            "",
        ]

    return "\n".join(lines).encode("utf-8")


def _payload_lines(value: Any, depth: int = 0) -> list[str]:
    """Render a payload as nested Markdown bullets.

    Agent payloads are arbitrary nested JSON, so this walks them generically
    rather than assuming any particular agent's shape.

    Args:
        value: The payload fragment to render.
        depth: Current nesting depth, used for indentation.

    Returns:
        Markdown lines for this fragment.
    """
    indent = "  " * depth
    lines: list[str] = []

    if isinstance(value, dict):
        for key, item in value.items():
            label = str(key).replace("_", " ")
            if isinstance(item, (dict, list)):
                lines.append(f"{indent}- **{label}:**")
                lines += _payload_lines(item, depth + 1)
            else:
                # Markdown and PDF go to a person, so a bare chunk id reads as
                # noise: "segment id: 54f8b219-1298-46c1-8add-...-c0004".
                #
                # Both are kept, unlike in the app. An export carries no
                # document title and may span several documents, so "Passage 1"
                # alone would not identify anything - the id is what makes an
                # exported claim traceable back to its source.
                if key == "segment_id":
                    item = f"{describe_chunk_id(str(item))} ({item})"
                lines.append(f"{indent}- **{label}:** {item}")
    elif isinstance(value, list):
        for index, item in enumerate(value, start=1):
            if isinstance(item, dict):
                # Numbered so consecutive records (questions, flashcards) stay
                # visually separate instead of running into one another.
                lines.append(f"{indent}- **[{index}]**")
                lines += _payload_lines(item, depth + 1)
            elif isinstance(item, list):
                lines += _payload_lines(item, depth + 1)
            else:
                lines.append(f"{indent}- {item}")
    else:
        lines.append(f"{indent}- {value}")

    return lines


def _render_pdf(outputs: Sequence[GeneratedOutput], title: str) -> bytes:
    """Render a printable PDF using the Markdown rendering as its source."""
    try:
        from fpdf import FPDF
        from fpdf.enums import XPos, YPos
    except ImportError as exc:  # pragma: no cover - fpdf2 is a declared dependency
        raise ExportFormatUnavailableError(
            "PDF export requires fpdf2. Install it with: pip install fpdf2"
        ) from exc

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)

    def write(text: str, height: float, *, size: int = 11, bold: bool = False) -> None:
        """Write one wrapped line, returning the cursor to the left margin.

        multi_cell leaves the cursor at the right margin by default, which would
        leave the next call zero width to work with.
        """
        pdf.set_font("Helvetica", style="B" if bold else "", size=size)
        pdf.multi_cell(0, height, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    for line in _render_markdown(outputs, title).decode("utf-8").split("\n"):
        text = _to_latin1(line.replace("**", ""))
        if not text.strip():
            pdf.ln(4)
            continue
        if text.startswith("# "):
            write(text[2:], 8, size=16, bold=True)
        elif text.startswith("## "):
            write(text[3:], 7, size=13, bold=True)
        else:
            write(text, 6)

    return bytes(pdf.output())


def _to_latin1(text: str) -> str:
    """Make text safe for fpdf2's built-in core fonts.

    The core PDF fonts are latin-1 only. Common typographic characters are
    mapped to ASCII equivalents so ordinary study content survives intact;
    anything still unrepresentable (other scripts, symbols) degrades to ``?``
    rather than failing the export. Embedding a Unicode TTF would remove the
    limitation at the cost of shipping a font file.

    Args:
        text: The line to sanitise.

    Returns:
        A latin-1 representable string.
    """
    replacements = {
        "—": "-",
        "–": "-",
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "…": "...",
        "→": "->",
        "•": "-",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text.encode("latin-1", errors="replace").decode("latin-1")


_RENDERERS = {
    ExportFormat.JSON: _render_json,
    ExportFormat.CSV: _render_csv,
    ExportFormat.MARKDOWN: _render_markdown,
    ExportFormat.PDF: _render_pdf,
}
