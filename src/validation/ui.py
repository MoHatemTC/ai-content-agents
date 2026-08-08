"""Streamlit pages for reviewing, tracing and exporting generated content.

Three pages over the platform services:

* **Review** — the queue. Inspect an output's payload, its validation verdict
  and the chunks it was grounded in, then approve, edit, reject or comment.
* **History** — what the system did: runs, their outcomes, and the merged
  timeline of everything that happened to one output.
* **Export** — download a run's approved outputs as JSON, CSV, Markdown or PDF.
  Attempting to export unapproved content shows the gate's refusal rather than
  hiding it, because seeing the gate work is the point.

This module holds no logic of its own: every decision belongs to
:mod:`src.validation.review_service`, :mod:`src.validation.history` and
:mod:`src.exports`, which are tested without Streamlit. What lives here is
layout and wiring.

Run it with::

    streamlit run src/validation/ui.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Allow `streamlit run src/validation/ui.py`, which puts this file's directory
# on sys.path rather than the project root.
if __name__ == "__main__":  # pragma: no cover - import-path bootstrap
    _project_root = Path(__file__).resolve().parent.parent.parent
    if str(_project_root) not in sys.path:
        sys.path.insert(0, str(_project_root))

import streamlit as st

from src.exports import ExportFormat, export_approved_run
from src.validation.evaluation import EvaluationHarness
from src.validation.history import HistoryService
from src.validation.review_schema import (
    ExportBlockedError,
    GeneratedOutput,
    IllegalTransitionError,
    OutputStatus,
)
from src.validation.review_service import ReviewService
from src.validation.store import PlatformStore
from src.retrieval.models import describe_chunk_id

STATUS_ICONS = {
    OutputStatus.PENDING: "🕓",
    OutputStatus.EDITED: "✏️",
    OutputStatus.APPROVED: "✅",
    OutputStatus.REJECTED: "🚫",
}


@st.cache_resource
def get_store() -> PlatformStore:
    """Return the shared platform store.

    Cached so every page and rerun uses one connection configuration. The path
    comes from ``PLATFORM_DB_PATH``, which is also what the batch CLI writes to.
    """
    return PlatformStore()


def _reviewer_name() -> str:
    """Return the reviewer identity entered in the sidebar.

    Every review record is attributed, so the page refuses to act without one.
    """
    return st.sidebar.text_input(
        "Reviewer", value="", placeholder="your name", key="reviewer"
    ).strip()


def _status_label(status: OutputStatus) -> str:
    """Render a status with its icon."""
    return f"{STATUS_ICONS.get(status, '')} {status.value}"


def _describe(output: GeneratedOutput) -> str:
    """Render a one-line label for an output in a selector."""
    verdict = "valid" if output.validation_passed else "flagged"
    return (
        f"{_status_label(output.status)} · {output.output_type} · {verdict} · "
        f"{output.id[:8]}"
    )


def _show_validation(output: GeneratedOutput) -> None:
    """Render an output's validation verdict, spelling out any failure."""
    report: dict[str, Any] = output.validation_report or {}
    errors = report.get("schema_errors") or []
    violations = report.get("guardrail_violations") or []

    if output.validation_passed:
        st.success("Validation passed: schema valid and all guardrails satisfied.")
    else:
        st.error("Validation failed — read the reasons before approving.")

    for error in errors:
        st.warning(f"**Schema:** {error}")
    for violation in violations:
        icon = "🚨" if violation.get("severity") == "error" else "⚠️"
        st.warning(f"{icon} **{violation.get('rule_name')}:** {violation.get('message')}")

    if report.get("revalidated") is False:
        st.info(
            "This verdict predates the last edit: the output's schema could not "
            "be resolved, so it was not re-checked."
        )


def _show_provenance(store: PlatformStore, output: GeneratedOutput) -> None:
    """Render the run and the chunk ids the output was grounded in."""
    run = store.get_agent_run(output.agent_run_id)
    if run is None:
        st.info("The generating run is no longer on record.")
        return

    st.caption(
        f"Run `{run.id[:8]}` · agent **{run.agent_name}** · model "
        f"`{run.model or 'unknown'}` · {run.status.value}"
    )
    if run.error:
        st.error(f"Run error: {run.error}")

    if run.source_chunk_ids:
        # Readable for scanning; the raw ids stay one click away, because a
        # reviewer tracing an output back to its chunk needs the real string.
        st.write(
            "**Grounded in:** "
            + ", ".join(describe_chunk_id(c) for c in run.source_chunk_ids)
        )
        with st.expander("Raw chunk ids"):
            st.code("\n".join(run.source_chunk_ids), language=None)
    else:
        st.warning("This output was generated without retrieval grounding.")

    if run.input_context:
        with st.expander("Content the agent was given"):
            st.text(run.input_context)


# --------------------------------------------------------------------------- #
# Review page
# --------------------------------------------------------------------------- #


def render_review_page(service: ReviewService | None = None) -> None:
    """Render the review queue and the actions on a selected output.

    Args:
        service: Review service to drive; the shared store is used if omitted.
    """
    store = get_store()
    review = service or ReviewService(store)

    st.title("Review queue")
    st.caption(
        "Nothing an agent produces can be exported until a human approves it here."
    )

    reviewer = _reviewer_name()

    statuses = st.multiselect(
        "Status",
        options=list(OutputStatus),
        default=[OutputStatus.PENDING],
        format_func=_status_label,
    )
    agent_filter = st.text_input("Agent (optional)", placeholder="mentor").strip()

    outputs: list[GeneratedOutput] = []
    for status in statuses or list(OutputStatus):
        outputs += review.list_outputs(status=status, agent_name=agent_filter or None)
    outputs.sort(key=lambda output: output.created_at, reverse=True)

    if not outputs:
        st.info("Nothing matches these filters. Generate some content first.")
        return

    st.write(f"**{len(outputs)}** output(s).")
    selected_id = st.selectbox(
        "Output", options=[o.id for o in outputs], format_func=lambda i: _describe(
            next(o for o in outputs if o.id == i)
        )
    )
    output = review.get(selected_id)

    st.subheader(f"{output.output_type} — {_status_label(output.status)}")
    _show_provenance(store, output)
    _show_validation(output)

    st.markdown("### Payload")
    edited_text = st.text_area(
        "Editable JSON payload",
        value=json.dumps(output.payload, indent=2, ensure_ascii=False),
        height=320,
        key=f"payload-{output.id}",
    )

    notes = st.text_input("Notes (optional)", key=f"notes-{output.id}")

    if not reviewer:
        st.warning("Enter your name in the sidebar to record a review.")

    approve, save, reject, comment = st.columns(4)
    disabled = not reviewer

    if approve.button("✅ Approve", disabled=disabled, use_container_width=True):
        _act(lambda: review.approve(output.id, reviewer, notes or None), "Approved.")
    if save.button("✏️ Save edit", disabled=disabled, use_container_width=True):
        _act(
            lambda: review.edit(
                output.id, reviewer, json.loads(edited_text), notes or None
            ),
            "Edit saved and re-validated.",
        )
    if reject.button("🚫 Reject", disabled=disabled, use_container_width=True):
        _act(lambda: review.reject(output.id, reviewer, notes or None), "Rejected.")
    if comment.button("💬 Comment", disabled=disabled, use_container_width=True):
        if not notes:
            st.warning("A comment needs some text.")
        else:
            _act(lambda: review.comment(output.id, reviewer, notes), "Comment added.")

    history = review.history(output.id)
    if history:
        st.markdown("### Review history")
        st.dataframe(
            [
                {
                    "when": record.timestamp.strftime("%Y-%m-%d %H:%M"),
                    "reviewer": record.reviewer,
                    "action": record.action.value,
                    "status": f"{record.previous_status.value} → {record.new_status.value}",
                    "notes": record.notes or "",
                }
                for record in history
            ],
            use_container_width=True,
            hide_index=True,
        )


def _act(action: Any, success_message: str) -> None:
    """Run a review action, reporting refusals instead of crashing the page."""
    try:
        action()
    except json.JSONDecodeError as exc:
        st.error(f"That payload is not valid JSON: {exc}")
    except IllegalTransitionError as exc:
        st.error(f"{exc} Approved and rejected outputs are final.")
    except ValueError as exc:
        st.error(str(exc))
    else:
        st.success(success_message)
        st.rerun()


# --------------------------------------------------------------------------- #
# History page
# --------------------------------------------------------------------------- #


def render_history_page() -> None:
    """Render generation history: runs, events and per-output timelines."""
    store = get_store()
    history = HistoryService(store)

    st.title("History")
    st.caption("Every agent run, including the ones that failed.")

    runs = history.list_runs(limit=200)
    if not runs:
        st.info("No runs recorded yet.")
        return

    st.dataframe(
        [
            {
                "started": run.started_at.strftime("%Y-%m-%d %H:%M:%S"),
                "agent": run.agent_name,
                "status": run.status.value,
                "chunks": len(run.source_chunk_ids),
                "error": (run.error or "")[:80],
                "run": run.id[:8],
            }
            for run in runs
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("### Run detail")
    run_id = st.selectbox(
        "Run", options=[run.id for run in runs], format_func=lambda i: f"{i[:8]}"
    )
    detail = history.run_detail(run_id)
    if detail is not None:
        st.write(
            f"**{detail.run.agent_name}** · {detail.run.status.value} · "
            f"{len(detail.outputs)} output(s)"
        )
        for output in detail.outputs:
            with st.expander(_describe(output)):
                st.json(output.payload)
                st.markdown("**Timeline**")
                for entry in history.output_timeline(output.id):
                    actor = f" — {entry.actor}" if entry.actor else ""
                    st.write(
                        f"`{entry.timestamp.strftime('%H:%M:%S')}` "
                        f"**{entry.kind}**{actor}: {entry.summary}"
                    )

    st.markdown("### Event log")
    events = history.list_events(limit=200)
    if events:
        st.dataframe(
            [
                {
                    "when": event.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    "type": event.event_type,
                    "message": event.message,
                }
                for event in events
            ],
            use_container_width=True,
            hide_index=True,
        )


# --------------------------------------------------------------------------- #
# Export page
# --------------------------------------------------------------------------- #


def render_export_page() -> None:
    """Render the export page for a run's approved outputs."""
    store = get_store()

    st.title("Export")
    st.caption("Only approved outputs leave the platform.")

    runs = store.list_agent_runs(limit=200)
    if not runs:
        st.info("No runs to export yet.")
        return

    run_id = st.selectbox(
        "Run",
        options=[run.id for run in runs],
        format_func=lambda i: next(
            f"{r.agent_name} · {r.started_at.strftime('%Y-%m-%d %H:%M')} · {i[:8]}"
            for r in runs
            if r.id == i
        ),
    )

    outputs = store.list_outputs(agent_run_id=run_id)
    approved = [o for o in outputs if o.status is OutputStatus.APPROVED]
    blocked = [o for o in outputs if o.status is not OutputStatus.APPROVED]

    st.write(f"**{len(approved)}** approved of {len(outputs)} output(s) in this run.")
    if blocked:
        st.info(
            f"{len(blocked)} output(s) are held back: "
            + ", ".join(sorted({_status_label(o.status) for o in blocked}))
        )

    export_format = ExportFormat(
        st.selectbox(
            "Format",
            options=[f.value for f in ExportFormat],
            format_func=str.upper,
        )
    )

    try:
        data = export_approved_run(run_id, export_format, store)
    except ExportBlockedError as exc:
        # Surfaced rather than swallowed: the gate refusing is the feature.
        st.error(f"Export blocked by the review gate: {exc}")
        return

    if not approved:
        st.warning("Nothing in this run is approved yet, so the export is empty.")

    st.download_button(
        f"Download {export_format.value}",
        data=data,
        file_name=f"approved-{run_id[:8]}.{export_format.extension}",
        mime=export_format.media_type,
        disabled=not approved,
    )


# --------------------------------------------------------------------------- #
# Metrics page
# --------------------------------------------------------------------------- #


def render_metrics_page() -> None:
    """Render the evaluation metrics over everything recorded so far."""
    st.title("Quality metrics")
    st.caption(
        "Scored from the stored record — no model calls, so these numbers are "
        "reproducible."
    )

    report = EvaluationHarness(get_store()).evaluate()
    if report.overall.runs == 0:
        st.info("Nothing to score yet. Run some agents first.")
        return

    overall = report.overall
    left, middle, right = st.columns(3)
    left.metric("Schema pass rate", _pct(overall.schema_pass_rate))
    middle.metric("Groundedness", _pct(overall.groundedness_rate))
    right.metric("Review edit rate", _pct(overall.review_edit_rate))

    st.dataframe(report.summary_rows(), use_container_width=True, hide_index=True)


def _pct(value: float | None) -> str:
    """Render a rate as a percentage, or ``n/a`` when undefined."""
    return "n/a" if value is None else f"{value * 100:.0f}%"


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

PAGES = {
    "📝 Review": render_review_page,
    "🕘 History": render_history_page,
    "📤 Export": render_export_page,
    "📊 Metrics": render_metrics_page,
}


def main() -> None:
    """Run the review application."""
    st.set_page_config(page_title="Content Agents — Review", page_icon="✅", layout="wide")
    st.sidebar.title("✅ Review & Export")
    choice = st.sidebar.radio("Page", list(PAGES))
    st.sidebar.caption(f"Database: `{get_store().db_path}`")
    PAGES[choice]()


if __name__ == "__main__":  # pragma: no cover - Streamlit entry point
    main()
