"""Citations a person can read, and a "Sources" heading that is earned.

The Mentor page used to print raw chunk ids under the heading "Provenance
references":

    54f8b219-1298-46c1-8add-46d3f5020e07-c0004: The electron and proton...

Two separate defects. The label is a database key, not a citation. And nothing
verified it: ``verify_references`` only runs when the agent is handed a
``GroundedContext``, and the app deliberately does not pass one (issue #33), so
a model could invent an id and the page would present it as a source.

Fixing only the first would have made things worse - an invented citation
reading "Passage 5 - Physics Notes.pdf" is far more convincing than a UUID -
which is why both live in one change and both are tested here.
"""

from __future__ import annotations

import json

from src.exports.export import export_outputs
from src.retrieval.models import describe_chunk_id
from src.validation.review_schema import GeneratedOutput, OutputStatus

DOC_ID = "54f8b219-1298-46c1-8add-46d3f5020e07"


# --------------------------------------------------------------------------- #
# The label
# --------------------------------------------------------------------------- #


def test_a_chunk_id_reads_as_a_passage_number() -> None:
    assert describe_chunk_id(f"{DOC_ID}-c0004") == "Passage 5"


def test_the_document_title_is_included_when_known() -> None:
    assert (
        describe_chunk_id(f"{DOC_ID}-c0004", title="Ch. 23_ppt.pdf")
        == "Passage 5 · Ch. 23_ppt.pdf"
    )


def test_the_first_passage_is_one_not_zero() -> None:
    """Ordinals are 0-based in the code; "Passage 0" reads as a bug to a human."""
    assert describe_chunk_id(f"{DOC_ID}-c0000") == "Passage 1"


def test_an_id_that_does_not_follow_the_convention_is_left_alone() -> None:
    """External ingestion may supply its own ids. Degrade, never raise.

    The prompt templates use placeholder ids like ``seg1``, and a model
    sometimes copies those instead of a real one.
    """
    for foreign in ("seg1", "chunk_001", "", "no-ordinal-here"):
        assert describe_chunk_id(foreign) == foreign


# --------------------------------------------------------------------------- #
# The verification
#
# Driven through the real page in test_ui_smoke.py, not asserted here: checking
# `id in retrieved_ids` in a test would be asserting Python's `in` operator, not
# this codebase's behaviour.
# --------------------------------------------------------------------------- #


def test_the_payload_keeps_the_raw_id() -> None:
    """Eight consumers compare segment_id by exact string match.

    verify_references, PlatformGroundingRule, review_service re-validation, the
    evaluator, and the source_chunk_ids column persisted in SQLite. Rendering is
    a display concern and must not rewrite what they read.
    """
    payload = {
        "explanation": "Charge is conserved.",
        "references": [{"segment_id": f"{DOC_ID}-c0004", "text": "excerpt"}],
        "requires_human_review": True,
    }

    describe_chunk_id(payload["references"][0]["segment_id"], title="Notes.pdf")

    assert payload["references"][0]["segment_id"] == f"{DOC_ID}-c0004"


# --------------------------------------------------------------------------- #
# Exports
# --------------------------------------------------------------------------- #


def _approved_output() -> GeneratedOutput:
    return GeneratedOutput(
        agent_run_id="run-1",
        output_type="mentor",
        schema_name="MentorOutput",
        payload={
            "explanation": "Charge is conserved.",
            "key_points": ["Charge is conserved."],
            "next_steps": ["Review the chapter."],
            "references": [{"segment_id": f"{DOC_ID}-c0004", "text": "excerpt"}],
            "requires_human_review": True,
        },
        validation_passed=True,
        status=OutputStatus.APPROVED,
    )


def test_the_markdown_export_is_readable_and_still_traceable() -> None:
    """An export carries no document title and may span several documents.

    So "Passage 5" alone would identify nothing - the raw id is what makes an
    exported claim traceable. Both are kept, unlike in the app.
    """
    text = export_outputs([_approved_output()], "markdown").decode("utf-8")

    assert "Passage 5" in text, "the export still shows a bare chunk id"
    assert f"{DOC_ID}-c0004" in text, "the export lost its traceability"


def test_the_json_export_is_untouched() -> None:
    """JSON is a machine-readable audit surface; it must carry the raw id only."""
    payload = json.loads(export_outputs([_approved_output()], "json"))

    reference = payload["outputs"][0]["payload"]["references"][0]
    assert reference["segment_id"] == f"{DOC_ID}-c0004"
    assert "Passage" not in json.dumps(payload), "a display label leaked into JSON"
