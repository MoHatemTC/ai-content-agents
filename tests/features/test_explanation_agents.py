"""Contract checks for the Mentor and Concept agents.

These two were written as separate 85%-identical files and had already drifted:
Mentor resolved a GroundedContext itself, Concept relied on ``_build_prompt``'s
isinstance branch. They now share
:class:`~src.agents.explanation_agent_base.ExplanationAgentBase`, so every check
here runs against both - which is the point. Where they diverge, the divergence
fails here rather than hiding in two files nobody diffs.

The headline fix these guard: ``generate_reviewable`` used to build an AgentRun
and a GeneratedOutput and then drop both, so the UI said "PENDING" while the
output never reached the review queue.
"""

from __future__ import annotations

import json

import pytest

from src.agents.concept_agent import ConceptAgent
from src.agents.mentor_agent import MentorAgent
from src.llm_gateway import UpstreamResponseError
from src.retrieval.models import (
    Chunk,
    GroundedContext,
    RetrievalScope,
    RetrievedChunk,
)
from src.validation.review_schema import OutputStatus, RunStatus
from src.validation.schemas import ConceptOutput, MentorOutput
from src.validation.store import PlatformStore
from tests.conftest import FakeLLMClient, Reply

AGENTS = [
    pytest.param(MentorAgent, MentorOutput, id="mentor"),
    pytest.param(ConceptAgent, ConceptOutput, id="concept"),
]

SOURCE = (
    "A while loop evaluates a condition before each pass and repeats while that "
    "condition remains true. A for loop iterates over the items of a sequence."
)


def payload_for(schema, *, review=True, references=None):
    """A schema-valid reply for either agent."""
    common = {
        "explanation": "A while loop evaluates a condition before each pass.",
        "key_points": ["A while loop evaluates a condition before each pass."],
        "references": (
            [{"segment_id": "doc-1-c0000", "text": SOURCE}]
            if references is None
            else references
        ),
        "requires_human_review": review,
    }
    if schema is MentorOutput:
        common["next_steps"] = ["Re-read the loop section."]
    else:
        common["definition"] = "A while loop repeats while its condition holds."
    return json.dumps(common)


def agent_with(agent_class, schema, **kw):
    return agent_class(client=FakeLLMClient(payload_for(schema, **kw)), model="m")


def a_context(chunk_id="doc-1-c0000"):
    chunk = Chunk(chunk_id=chunk_id, document_id="doc-1", ordinal=0, text=SOURCE)
    return GroundedContext(
        query="loops",
        scope=RetrievalScope(document_id="doc-1"),
        chunks=[RetrievedChunk(chunk=chunk, score=1.0, rank=1)],
    )


# --------------------------------------------------------------------------- #
# The review gate has to actually gate something
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_a_reviewable_output_reaches_the_review_queue(
    agent_class, schema, tmp_path
) -> None:
    """The bug this file exists for.

    generate_reviewable built an AgentRun, copied its id onto a
    GeneratedOutput, and dropped both. The pages printed "Requires Human
    Review - PENDING" while nothing was saved, so a reviewer opening the queue
    saw nothing and the output could never be approved or exported.
    """
    store = PlatformStore(db_path=str(tmp_path / "platform.db"))
    agent = agent_with(agent_class, schema)

    output = agent.generate_reviewable(
        SOURCE, "Explain loops.", "beginner", store=store
    )

    queued = store.list_outputs(status=OutputStatus.PENDING)
    assert [o.id for o in queued] == [output.id], "the output never reached the queue"
    assert store.get_agent_run(output.agent_run_id) is not None, "run not persisted"


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_the_run_records_what_the_model_actually_saw(
    agent_class, schema, tmp_path
) -> None:
    """``content`` is discarded when a context is supplied.

    Recording it anyway made the review record assert an input that was never
    used - and a GroundedContext is not a str, so it raised a ValidationError
    straight out of a method typed to return a GeneratedOutput.
    """
    store = PlatformStore(db_path=str(tmp_path / "platform.db"))
    agent = agent_with(agent_class, schema)

    output = agent.generate_reviewable(
        "this string is discarded",
        "Explain loops.",
        "beginner",
        context=a_context(),
        store=store,
    )

    run = store.get_agent_run(output.agent_run_id)
    assert "this string is discarded" not in (run.input_context or "")
    assert SOURCE in (run.input_context or ""), "the passage was not recorded"
    assert run.source_chunk_ids == ["doc-1-c0000"]
    assert run.finished_at is not None, "the run was left unfinished"


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_a_grounded_context_as_content_does_not_crash(
    agent_class, schema, tmp_path
) -> None:
    """Passing the context positionally used to raise pydantic.ValidationError."""
    store = PlatformStore(db_path=str(tmp_path / "platform.db"))
    agent = agent_with(agent_class, schema)

    output = agent.generate_reviewable(a_context(), "Explain loops.", store=store)

    assert output.status is OutputStatus.PENDING


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_a_failed_run_is_recorded_not_lost(agent_class, schema, tmp_path) -> None:
    """A run that raises is a fact about the run; History should show it."""
    store = PlatformStore(db_path=str(tmp_path / "platform.db"))
    agent = agent_class(client=FakeLLMClient("not json at all"), model="m")

    with pytest.raises(ValueError):
        agent.generate_reviewable(SOURCE, "Explain loops.", store=store)

    runs = store.list_agent_runs()
    assert len(runs) == 1
    assert runs[0].status is RunStatus.FAILURE
    assert runs[0].error


# --------------------------------------------------------------------------- #
# The review flag is a control, not an output
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_the_model_cannot_switch_off_human_review(agent_class, schema, caplog) -> None:
    """A ``false`` reply used to fail the whole generation.

    That turned a prompt injection in an uploaded document into a denial of
    service. Coercing closes both that and the review bypass.
    """
    agent = agent_with(agent_class, schema, review=False)

    with caplog.at_level("WARNING"):
        result = agent.generate(SOURCE, "Explain loops.")

    assert result.requires_human_review is True
    assert "prompt injection" in caplog.text


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_a_compliant_reply_is_not_warned_about(agent_class, schema, caplog) -> None:
    """Control: a warning on every generation trains people to ignore it."""
    agent = agent_with(agent_class, schema, review=True)

    with caplog.at_level("WARNING"):
        agent.generate(SOURCE, "Explain loops.")

    assert "requires_human_review" not in caplog.text


# --------------------------------------------------------------------------- #
# Grounding
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_an_invented_citation_is_rejected(agent_class, schema) -> None:
    agent = agent_with(
        agent_class,
        schema,
        references=[{"segment_id": "doc-1-c9999", "text": "never retrieved"}],
    )

    with pytest.raises(ValueError, match="doc-1-c9999"):
        agent.generate(SOURCE, "Explain loops.", context=a_context())


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_an_uncited_answer_is_rejected_when_grounding_is_on(
    agent_class, schema
) -> None:
    """verify_references treats an empty citation list as trivially valid.

    So without this an uncited answer passed grounding, and the UI - which
    ignores validation_passed - rendered it identically to a cited one.
    """
    agent = agent_with(agent_class, schema, references=[])

    with pytest.raises(ValueError, match="cites no sources"):
        agent.generate(SOURCE, "Explain loops.", context=a_context())


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_a_genuine_citation_is_accepted(agent_class, schema) -> None:
    """Control: a check that rejects everything would pass the two above."""
    agent = agent_with(agent_class, schema)

    result = agent.generate(SOURCE, "Explain loops.", context=a_context())

    assert result.references[0].segment_id == "doc-1-c0000"


# --------------------------------------------------------------------------- #
# Controls and failures
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("agent_class,schema", AGENTS)
@pytest.mark.parametrize("bad", ["ESSAY_BANANA", "impossible", ""])
def test_an_invalid_difficulty_is_rejected(agent_class, schema, bad) -> None:
    client = FakeLLMClient(payload_for(schema))
    agent = agent_class(client=client, model="m")

    with pytest.raises(ValueError, match="[Dd]ifficulty"):
        agent.generate(SOURCE, "Explain loops.", bad)

    assert client.calls == [], "the model was called before the input was checked"


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_a_non_text_user_question_is_rejected(agent_class, schema) -> None:
    client = FakeLLMClient(payload_for(schema))

    with pytest.raises(ValueError, match="user_question"):
        agent_class(client=client, model="m").generate(SOURCE, {"not": "text"})

    assert client.calls == []


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_a_schema_failure_names_the_field(agent_class, schema) -> None:
    """A bare "does not match the schema" sends you to the model instead."""
    incomplete = json.loads(payload_for(schema))
    del incomplete["explanation"]
    agent = agent_class(client=FakeLLMClient(json.dumps(incomplete)), model="m")

    with pytest.raises(ValueError, match="explanation"):
        agent.generate(SOURCE, "Explain loops.")


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_a_batch_does_not_swallow_a_saturated_provider(agent_class, schema) -> None:
    """The one exception the codebase agrees is retryable.

    Swallowing it turned a 200-item batch into 200 permanent failures when a
    retry would have worked.
    """
    agent = agent_class(
        client=FakeLLMClient(*[Reply(error={"message": "saturated"})] * 4), model="m"
    )

    with pytest.raises(UpstreamResponseError):
        agent.generate_batch([{"content": SOURCE}, {"content": SOURCE}])


@pytest.mark.parametrize("agent_class,schema", AGENTS)
def test_a_batch_still_survives_a_per_item_failure(agent_class, schema) -> None:
    """Control: not everything may escape, or the batch stops being a batch."""
    agent = agent_class(
        client=FakeLLMClient("not json", payload_for(schema)), model="m"
    )

    result = agent.generate_batch([{"content": SOURCE}, {"content": SOURCE}])

    assert result.total_succeeded == 1
    assert result.total_failed == 1
    assert "ValueError" in result.failed_items[0].error
