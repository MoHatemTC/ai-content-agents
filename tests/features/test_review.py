"""Tests for the human review service: the queue, the four actions, the audit trail.

These cover the behaviour the Streamlit Review page depends on. Everything runs
offline against a temporary SQLite file — no agent and no network.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.retrieval.models import Chunk, GroundedContext, RetrievalScope, RetrievedChunk
from src.validation.history import REVIEW_ACTION
from src.validation.review_schema import (
    AgentRun,
    GeneratedOutput,
    IllegalTransitionError,
    OutputStatus,
    ReviewAction,
)
from src.validation.review_service import OutputNotFoundError, ReviewService
from src.validation.schemas import ContentReference, MentorOutput
from src.validation.store import PlatformStore

UI_PATH = Path(__file__).resolve().parents[2] / "src" / "validation" / "ui.py"


@pytest.fixture()
def store(tmp_path: Path) -> PlatformStore:
    """A PlatformStore backed by a throwaway database file."""
    return PlatformStore(db_path=str(tmp_path / "platform.db"))


@pytest.fixture()
def service(store: PlatformStore) -> ReviewService:
    """A ReviewService over the throwaway store."""
    return ReviewService(store)


@pytest.fixture()
def review_app(
    store: PlatformStore, monkeypatch: pytest.MonkeyPatch
) -> Iterator[AppTest]:
    """The Streamlit app driven headlessly against the throwaway store.

    ``PLATFORM_DB_PATH`` points the page's cached store at the temporary file.
    The whole resource cache is cleared around each test because Streamlit
    executes the page as a fresh ``__main__`` module, so its ``get_store`` is a
    different function object from ``src.validation.ui.get_store`` — clearing
    that one would leave the previous test's database cached.
    """
    import streamlit as st

    monkeypatch.setenv("PLATFORM_DB_PATH", store.db_path)
    st.cache_resource.clear()
    yield AppTest.from_file(str(UI_PATH), default_timeout=30)
    st.cache_resource.clear()


def _mentor_payload(*segment_ids: str) -> dict:
    """A schema-valid MentorOutput payload citing the given segment ids."""
    return MentorOutput(
        explanation="Force equals mass times acceleration.",
        key_points=["F = ma"],
        next_steps=["Practice a worked example."],
        references=[
            ContentReference(segment_id=segment_id, text="excerpt")
            for segment_id in segment_ids
        ],
    ).model_dump(mode="json")


def _seed(
    store: PlatformStore,
    *,
    status: OutputStatus = OutputStatus.PENDING,
    agent_name: str = "mentor",
    payload: dict | None = None,
    source_chunk_ids: list[str] | None = None,
    validation_passed: bool = True,
) -> GeneratedOutput:
    """Persist a run and one output, returning the output."""
    run = AgentRun(
        agent_name=agent_name,
        source_chunk_ids=source_chunk_ids or ["doc-c0000"],
    )
    store.save_agent_run(run)
    output = GeneratedOutput(
        agent_run_id=run.id,
        output_type=agent_name,
        payload=payload if payload is not None else _mentor_payload("doc-c0000"),
        schema_name="MentorOutput",
        validation_passed=validation_passed,
        status=status,
    )
    return store.save_output(output)


# --------------------------------------------------------------------------- #
# The review queue
# --------------------------------------------------------------------------- #


def test_list_pending_returns_only_unreviewed_outputs(
    store: PlatformStore, service: ReviewService
) -> None:
    _seed(store, status=OutputStatus.PENDING)
    _seed(store, status=OutputStatus.APPROVED)
    _seed(store, status=OutputStatus.REJECTED)

    pending = service.list_pending()

    assert len(pending) == 1
    assert pending[0].status is OutputStatus.PENDING


def test_list_outputs_filters_by_agent_and_status(
    store: PlatformStore, service: ReviewService
) -> None:
    _seed(store, agent_name="mentor")
    _seed(store, agent_name="concept")
    _seed(store, agent_name="concept", status=OutputStatus.APPROVED)

    assert len(service.list_outputs(agent_name="concept")) == 2
    assert len(service.list_outputs(status=OutputStatus.APPROVED)) == 1


def test_get_unknown_output_raises(service: ReviewService) -> None:
    with pytest.raises(OutputNotFoundError):
        service.get("does-not-exist")


# --------------------------------------------------------------------------- #
# Approve / reject / comment
# --------------------------------------------------------------------------- #


def test_approve_persists_status_and_review(
    store: PlatformStore, service: ReviewService
) -> None:
    output = _seed(store)

    review = service.approve(output.id, "nour", notes="accurate")

    assert service.get(output.id).status is OutputStatus.APPROVED
    assert review.action is ReviewAction.APPROVE
    saved = store.list_reviews(output_id=output.id)
    assert len(saved) == 1
    assert saved[0].reviewer == "nour"
    assert saved[0].notes == "accurate"


def test_reject_persists_status_and_review(
    store: PlatformStore, service: ReviewService
) -> None:
    output = _seed(store)

    service.reject(output.id, "nour", notes="ungrounded")

    assert service.get(output.id).status is OutputStatus.REJECTED
    assert store.list_reviews(output_id=output.id)[0].action is ReviewAction.REJECT


def test_comment_leaves_status_untouched(
    store: PlatformStore, service: ReviewService
) -> None:
    output = _seed(store)

    service.comment(output.id, "nour", notes="checking with Youssef")

    assert service.get(output.id).status is OutputStatus.PENDING
    assert len(store.list_reviews(output_id=output.id)) == 1


def test_illegal_action_leaves_everything_unchanged(
    store: PlatformStore, service: ReviewService
) -> None:
    """A refused action must not half-apply: no status change, no review row."""
    output = _seed(store, status=OutputStatus.APPROVED)

    with pytest.raises(IllegalTransitionError):
        service.reject(output.id, "nour")

    assert service.get(output.id).status is OutputStatus.APPROVED
    assert store.list_reviews(output_id=output.id) == []


def test_approving_a_rejected_output_is_refused(
    store: PlatformStore, service: ReviewService
) -> None:
    output = _seed(store)
    service.reject(output.id, "nour")

    with pytest.raises(IllegalTransitionError):
        service.approve(output.id, "someone-else")


# --------------------------------------------------------------------------- #
# Edit, and the re-validation that comes with it
# --------------------------------------------------------------------------- #


def test_edit_replaces_the_payload_and_records_it(
    store: PlatformStore, service: ReviewService
) -> None:
    output = _seed(store)
    edited = _mentor_payload("doc-c0000")
    edited["explanation"] = "Reworded by the reviewer."

    service.edit(output.id, "nour", edited)

    stored = service.get(output.id)
    assert stored.status is OutputStatus.EDITED
    assert stored.payload["explanation"] == "Reworded by the reviewer."
    assert store.list_reviews(output_id=output.id)[0].edited_payload == edited


def test_edit_revalidates_and_can_fail_the_verdict(
    store: PlatformStore, service: ReviewService
) -> None:
    """A reviewer must not be able to leave a stale 'passed' on broken content."""
    output = _seed(store, validation_passed=True)

    service.edit(output.id, "nour", {"explanation": "missing every other field"})

    stored = service.get(output.id)
    assert stored.validation_passed is False
    assert stored.validation_report["schema_errors"]


def test_edit_revalidates_and_can_repair_the_verdict(
    store: PlatformStore, service: ReviewService
) -> None:
    """The reverse: fixing the content updates the verdict to passing."""
    output = _seed(store, payload={"explanation": "broken"}, validation_passed=False)

    service.edit(output.id, "nour", _mentor_payload("doc-c0000"))

    assert service.get(output.id).validation_passed is True


def test_edit_rechecks_citations_against_the_runs_chunks(
    store: PlatformStore, service: ReviewService
) -> None:
    """Editing in a citation that was never retrieved is caught."""
    output = _seed(store, source_chunk_ids=["doc-c0000", "doc-c0001"])

    service.edit(output.id, "nour", _mentor_payload("invented-chunk"))

    stored = service.get(output.id)
    assert stored.validation_passed is False
    assert any(
        violation["rule_name"] == "grounding_verification"
        for violation in stored.validation_report["guardrail_violations"]
    )


def test_edit_keeps_a_citation_that_was_retrieved(
    store: PlatformStore, service: ReviewService
) -> None:
    output = _seed(store, source_chunk_ids=["doc-c0000", "doc-c0001"])

    service.edit(output.id, "nour", _mentor_payload("doc-c0001"))

    assert service.get(output.id).validation_passed is True


def test_edit_without_a_payload_is_refused(
    store: PlatformStore, service: ReviewService
) -> None:
    output = _seed(store)

    with pytest.raises(ValueError):
        service.edit(output.id, "nour", {})


def test_unknown_schema_leaves_the_verdict_alone(
    store: PlatformStore, service: ReviewService
) -> None:
    """An unresolvable schema must not silently claim the edit validated."""
    run = AgentRun(agent_name="future-agent")
    store.save_agent_run(run)
    output = store.save_output(
        GeneratedOutput(
            agent_run_id=run.id,
            output_type="future",
            payload={"a": 1},
            schema_name="SchemaFromTheFuture",
            validation_passed=True,
            validation_report={"passed": True},
        )
    )

    service.edit(output.id, "nour", {"a": 2})

    stored = service.get(output.id)
    assert stored.payload == {"a": 2}
    assert stored.validation_report.get("revalidated") is False


# --------------------------------------------------------------------------- #
# Audit trail
# --------------------------------------------------------------------------- #


def test_history_reads_as_the_story_of_the_output(
    store: PlatformStore, service: ReviewService
) -> None:
    output = _seed(store)

    service.comment(output.id, "ahmed", notes="looks thin")
    service.edit(output.id, "nour", _mentor_payload("doc-c0000"))
    service.approve(output.id, "nour")

    history = service.history(output.id)
    assert [r.action for r in history] == [
        ReviewAction.COMMENT,
        ReviewAction.EDIT,
        ReviewAction.APPROVE,
    ]
    assert [r.new_status for r in history] == [
        OutputStatus.PENDING,
        OutputStatus.EDITED,
        OutputStatus.APPROVED,
    ]


def test_comment_still_available_after_approval(
    store: PlatformStore, service: ReviewService
) -> None:
    output = _seed(store)
    service.approve(output.id, "nour")

    service.comment(output.id, "ahmed", notes="agreed, shipping this")

    assert len(service.history(output.id)) == 2


def test_review_actions_are_logged_as_events(
    store: PlatformStore, service: ReviewService
) -> None:
    output = _seed(store)

    service.approve(output.id, "nour")

    events = store.list_events(event_type=REVIEW_ACTION)
    assert len(events) == 1
    assert events[0].output_id == output.id
    assert "nour approved output" in events[0].message


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        ("approve", "nour approved output"),
        ("reject", "nour rejected output"),
        ("comment", "nour commented on output"),
    ],
)
def test_event_messages_read_as_english(
    store: PlatformStore, service: ReviewService, action: str, expected: str
) -> None:
    """Guards against the 'approveed' that naive suffixing produces."""
    output = _seed(store)

    if action == "comment":
        service.comment(output.id, "nour", notes="n")
    else:
        getattr(service, action)(output.id, "nour")

    assert expected in store.list_events(event_type=REVIEW_ACTION)[0].message


def test_review_page_lists_the_pending_queue(
    store: PlatformStore, review_app: AppTest
) -> None:
    _seed(store)

    review_app.run()

    assert not review_app.exception
    assert "Review queue" in review_app.title[0].value
    assert any("1" in str(markdown.value) for markdown in review_app.markdown)


def test_review_page_refuses_to_act_without_a_reviewer(
    store: PlatformStore, review_app: AppTest
) -> None:
    """Every review record is attributed, so the buttons stay disabled."""
    _seed(store)

    review_app.run()

    # Guard against a vacuous pass: an empty button list would satisfy all().
    assert len(review_app.button) == 4
    assert all(button.disabled for button in review_app.button)
    assert any("sidebar" in str(w.value).lower() for w in review_app.warning)


def test_approving_through_the_page_persists_the_decision(
    store: PlatformStore, review_app: AppTest
) -> None:
    """The button really drives the service, not just the widget state."""
    output = _seed(store)

    review_app.run()
    review_app.sidebar.text_input(key="reviewer").set_value("nour").run()
    review_app.button[0].click().run()

    assert not review_app.exception
    assert store.get_output(output.id).status is OutputStatus.APPROVED
    assert store.list_reviews(output_id=output.id)[0].reviewer == "nour"


def test_rejecting_through_the_page_persists_the_decision(
    store: PlatformStore, review_app: AppTest
) -> None:
    output = _seed(store)

    review_app.run()
    review_app.sidebar.text_input(key="reviewer").set_value("nour").run()
    review_app.button[2].click().run()

    assert store.get_output(output.id).status is OutputStatus.REJECTED


def test_review_page_reports_a_failed_validation(
    store: PlatformStore, review_app: AppTest
) -> None:
    _seed(store, validation_passed=False)

    review_app.run()

    assert any("Validation failed" in str(error.value) for error in review_app.error)


def test_review_page_survives_invalid_edited_json(
    store: PlatformStore, review_app: AppTest
) -> None:
    """A typo in the payload box must report an error, not crash the page."""
    output = _seed(store)

    review_app.run()
    review_app.sidebar.text_input(key="reviewer").set_value("nour").run()
    review_app.text_area(key=f"payload-{output.id}").set_value("{not json").run()
    review_app.button[1].click().run()

    assert not review_app.exception
    assert any("not valid JSON" in str(error.value) for error in review_app.error)
    assert store.get_output(output.id).status is OutputStatus.PENDING


def test_review_page_explains_a_refused_action(
    store: PlatformStore, review_app: AppTest
) -> None:
    _seed(store, status=OutputStatus.APPROVED)

    review_app.run()
    review_app.multiselect[0].set_value([OutputStatus.APPROVED]).run()
    review_app.sidebar.text_input(key="reviewer").set_value("nour").run()
    review_app.button[0].click().run()

    assert not review_app.exception
    assert any("final" in str(error.value) for error in review_app.error)


def test_every_page_renders(store: PlatformStore, review_app: AppTest) -> None:
    """History, Export and Metrics must all survive a real run."""
    output = _seed(store)
    ReviewService(store).approve(output.id, "nour")

    for page in ("🕘 History", "📤 Export", "📊 Metrics"):
        review_app.run()
        review_app.sidebar.radio[0].set_value(page).run()
        assert not review_app.exception, f"{page} raised {review_app.exception}"


def test_grounded_context_from_the_run_is_reused_when_supplied(
    store: PlatformStore, service: ReviewService
) -> None:
    """An explicit grounded context takes precedence over the stored chunk ids."""
    output = _seed(store, source_chunk_ids=["doc-c0000"])
    context = GroundedContext(
        query="q",
        scope=RetrievalScope(document_id="doc"),
        chunks=[
            RetrievedChunk(
                chunk=Chunk(
                    chunk_id="doc-c0009", document_id="doc", ordinal=9, text="text"
                ),
                score=1.0,
                rank=1,
            )
        ],
    )

    service.edit(
        output.id, "nour", _mentor_payload("doc-c0009"), grounded_context=context
    )

    assert service.get(output.id).validation_passed is True
