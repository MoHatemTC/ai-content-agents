"""Shared pytest configuration and test doubles.

Neutralises the parts of a developer's ``.env`` that would otherwise reach into
the suite, so a test run depends on the repository and nothing else.

This works because pytest imports ``conftest.py`` before any test module, and
``load_dotenv()`` (called at import time in several modules) defaults to
``override=False`` — a variable set here wins over ``.env``.

``CHROMA_DIR`` keeps tests out of a persisted retrieval index. Without this the
suite opened whatever the developer had built — for one of us a 105 MB index of
a physics textbook, embedded in live mode at 384 dimensions — and queried it
with the 256-dimension offline embedder, failing with ``Collection expecting
embedding with dimension of 384, got 256``.

That failure is invisible to CI, which has no ``.env`` at all and so always ran
in memory. A clean environment cannot reproduce a configuration bug, which is
exactly why ``test_the_suite_does_not_touch_a_persisted_index`` exists: it
passes trivially on CI and fails on the machine where the problem can occur.

``RETRIEVAL_EMBEDDER`` pins the offline hashing embedder, so no test downloads
an ONNX model or depends on one being cached.

**There is no ``MOCK_MODE``.** Agents take an injected client, and
:func:`src.llm_gateway.build_client` raises without credentials, so a test that
forgets to inject a double fails loudly instead of reaching the network. The
doubles below are what it injects; ``FakeLLMClient`` and the ``*_reply``
builders are importable from any test module (``from tests.conftest import
FakeLLMClient``) as well as available as fixtures.
"""

from __future__ import annotations

import json
import re
import os
from datetime import date, timedelta
from typing import Any

import pytest

os.environ["CHROMA_DIR"] = ""
os.environ.setdefault("RETRIEVAL_EMBEDDER", "hashing")

# The FastAPI layer builds its own LLM client rather than taking an injected
# one, so this flag is the only thing standing between the backend tests and
# the real gateway. Without it they take whichever branch the environment
# offers: a developer with LITELLM_API_KEY in .env silently bills real calls
# and the tests pass, while CI has no key and every one of them returns 503.
# Both happened - the 503s are what caught it.
#
# This is the same defect PR #28 fixed for the main suite, where a developer's
# .env hid seven tests making real API calls. setdefault, so anyone who wants
# to exercise the live path can still export it as 0.
os.environ.setdefault("SENSEI_USE_TEST_DOUBLES", "1")


class _Message:
    def __init__(self, content: str | None) -> None:
        self.content = content


class _Choice:
    def __init__(self, content: str | None, finish_reason: str = "stop") -> None:
        self.message = _Message(content)
        self.finish_reason = finish_reason


class Reply:
    """A stand-in for one OpenAI SDK response.

    Args:
        content: The reply body. ``None`` with ``choices=[]`` models the
            error-shaped success the gateway actually returns when a provider
            is saturated.
        finish_reason: ``"length"`` models a reply truncated by the output cap.
        error: The gateway's error payload, when there are no choices.
    """

    def __init__(
        self,
        content: str | None = None,
        *,
        finish_reason: str = "stop",
        error: Any = None,
        choices: list[Any] | None = None,
    ) -> None:
        if choices is None:
            choices = [] if content is None else [_Choice(content, finish_reason)]
        self.choices = choices or None
        self.error = error


class FakeLLMClient:
    """An OpenAI-compatible client that returns queued replies and records calls.

    Replaces the ``mock_mode`` flag the agents used to carry. A flag that swaps
    real output for fake output is a production feature that can be left on by
    accident — and was, for weeks. A fake client cannot be left on in
    production, because nothing in production constructs one.

    Args:
        replies: Reply bodies, in order. A plain string is wrapped in
            :class:`Reply`. Once exhausted, an empty JSON object is returned.
    """

    def __init__(self, *replies: str | Reply) -> None:
        self._replies = [
            reply if isinstance(reply, Reply) else Reply(reply) for reply in replies
        ]
        self.calls: list[dict] = []
        self.chat = self
        self.completions = self

    def create(self, **kwargs: Any) -> Reply:
        self.calls.append(kwargs)
        return self._replies.pop(0) if self._replies else Reply("{}")

    @property
    def prompt(self) -> str:
        """The prompt from the most recent call."""
        return self.calls[-1]["messages"][0]["content"]


# --------------------------------------------------------------------------- #
# Grounded reply builders
#
# These were `_mock_response` on the agents themselves, which is what made mock
# mode a production feature in the first place. They are test doubles, so they
# live with the tests. Each produces output that satisfies the agent's own
# grounding validators, so a test that wants to exercise the happy path can,
# and a test that wants a rejection can corrupt one field.
# --------------------------------------------------------------------------- #


def flashcard_reply(
    topics: list[str],
    *,
    card_format: str = "term-definition",
    card_count: int = 10,
    title: str = "Grounded flashcard set",
) -> str:
    """Build a FlashcardSet JSON reply grounded in ``topics``."""
    chosen = (topics or ["General topic"])[: max(1, min(card_count, len(topics) or 1))]
    cards = [
        {
            "front": topic if card_format == "term-definition" else f"What is {topic}?",
            "back": f"{topic} is covered in the supplied passages.",
            "format": card_format,
            "source_topic": topic,
            "source_chunk_id": None,
            "tags": [topic.lower()],
        }
        for topic in chosen
    ]
    return json.dumps(
        {
            "title": title,
            "description": f"{len(cards)} {card_format} cards.",
            "cards": cards,
            "source_topics": sorted({c["source_topic"] for c in cards}),
            "source_chunk_ids": [],
            "needs_human_review": True,
        }
    )


def study_plan_reply(
    topics: list[str],
    *,
    start_date: date,
    end_date: date,
    learner_goal: str = "Master the content topics",
    difficulty: str = "medium",
    hours_per_week: float | None = None,
) -> str:
    """Build a StudyPlan JSON reply that schedules only ``topics``."""
    chosen = topics or ["General topic"]
    total_days = max(1, (end_date - start_date).days)
    days_per_topic = max(1, total_days // len(chosen))
    weekly = hours_per_week if hours_per_week else 10.0
    per_topic = max(0.5, (weekly * max(1, total_days / 7.0)) / len(chosen))

    schedule = []
    for i, topic in enumerate(chosen):
        t_start = start_date + timedelta(days=i * days_per_topic)
        t_end = min(end_date, t_start + timedelta(days=days_per_topic - 1))
        schedule.append(
            {
                "topic": topic,
                "start_date": max(t_start, start_date).isoformat(),
                "end_date": max(t_end, t_start).isoformat(),
                "duration_hours": round(per_topic, 2),
                "difficulty": difficulty,
                "resources": [f"Content section: {topic}"],
            }
        )

    return json.dumps(
        {
            "goal": learner_goal,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "overall_difficulty": difficulty,
            "available_hours_per_week": hours_per_week,
            "topic_schedule": schedule,
            "source_topics": sorted(chosen),
            "needs_human_review": True,
        }
    )


def revision_reply(
    selected_topics: list[str],
    *,
    session_date: date,
    difficulty: str = "medium",
) -> str:
    """Build a RevisionSession JSON reply covering ``selected_topics``."""
    offsets = {"easy": 7, "medium": 3, "hard": 1}
    items = [
        {
            "topic": topic,
            "description": f"Revise {topic} using active recall.",
            "next_revision_date": (
                session_date + timedelta(days=offsets[difficulty])
            ).isoformat(),
            "difficulty": difficulty,
            "confidence_prompt": f"On a 1-5 scale, how confident are you about {topic}?",
            "source_chunk_id": None,
        }
        for topic in selected_topics
    ]
    return json.dumps(
        {
            "session_date": session_date.isoformat(),
            "items": items,
            "notes": "Generated revision session.",
            "selected_weak_topics": sorted(selected_topics),
            "source_topics": sorted(selected_topics),
            "needs_human_review": True,
        }
    )


class CompliantStudyClient:
    """A fake gateway that answers whatever study-agent prompt it is given.

    Queued replies are no use when something else builds the prompt - a UI test
    does not know which topics the retriever will surface, and a batch run asks
    once per dataset row. This reads the allow-list and parameters back out of
    the prompt and answers within them, which is what a well-behaved model does.

    It serves all three study agents, told apart by the fields their prompts
    carry. An unrecognised prompt raises rather than returning something empty:
    a double that silently answers nothing turns a wiring mistake into a
    confusing assertion failure somewhere else.

    Before agents took an injected client, the tests that drive real pages and
    real batch runs relied on mock mode. With the flag gone they would otherwise
    make real API calls - and did, briefly, which took the suite from 27 s to
    111 s and would have failed outright on CI, which has no credentials.
    """

    _TOPICS = re.compile(r"extracted_topics[^:]*:\s*(\[.*?\])\s*\n", re.DOTALL)
    _SELECTED = re.compile(r"selected_topics[^:]*:\s*(\[.*?\])\s*\n", re.DOTALL)
    _FORMAT = re.compile(r"card_format:\s*(\S+)")
    _COUNT = re.compile(r"card_count:\s*(\d+)")
    _GOAL = re.compile(r"learner_goal:\s*(.*)")
    _DIFFICULTY = re.compile(r"difficulty:\s*(\S+)")
    _START = re.compile(r"start_date:\s*(\d{4}-\d{2}-\d{2})")
    _END = re.compile(r"end_date:\s*(\d{4}-\d{2}-\d{2})")
    _SESSION = re.compile(r"session_date:\s*(\d{4}-\d{2}-\d{2})")
    _HOURS = re.compile(r"hours_per_week:\s*(\S+)")

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.chat = self
        self.completions = self

    @staticmethod
    def _json_list(match: re.Match | None) -> list[str]:
        return json.loads(match.group(1)) if match else []

    def create(self, **kwargs: Any) -> Reply:
        self.calls.append(kwargs)
        prompt = kwargs["messages"][0]["content"]
        topics = self._json_list(self._TOPICS.search(prompt))

        session = self._SESSION.search(prompt)
        if session:
            return Reply(
                revision_reply(
                    self._json_list(self._SELECTED.search(prompt)),
                    session_date=date.fromisoformat(session.group(1)),
                )
            )

        card_count = self._COUNT.search(prompt)
        if card_count:
            card_format = self._FORMAT.search(prompt)
            return Reply(
                flashcard_reply(
                    topics,
                    card_format=(
                        card_format.group(1) if card_format else "term-definition"
                    ),
                    card_count=int(card_count.group(1)),
                )
            )

        start, end = self._START.search(prompt), self._END.search(prompt)
        if start and end:
            goal = self._GOAL.search(prompt)
            difficulty = self._DIFFICULTY.search(prompt)
            hours = self._HOURS.search(prompt)
            return Reply(
                study_plan_reply(
                    topics,
                    start_date=date.fromisoformat(start.group(1)),
                    end_date=date.fromisoformat(end.group(1)),
                    learner_goal=goal.group(1).strip() if goal else "Learn the content",
                    difficulty=difficulty.group(1) if difficulty else "medium",
                    hours_per_week=(
                        float(hours.group(1))
                        if hours and hours.group(1) != "unspecified"
                        else None
                    ),
                )
            )

        raise AssertionError(
            "CompliantStudyClient does not recognise this prompt; it serves the "
            f"flashcard, study-plan and revision agents. Prompt began: {prompt[:200]!r}"
        )


_OPTIONS_FOR = {
    "mcq": ["for", "while", "if", "switch"],
    "true_false": ["True", "False"],
    "short_answer": None,
}
# correct_answer must be one of the options character for character when options
# is not null, and free text when it is.
_ANSWER_FOR = {"mcq": "while", "true_false": "False", "short_answer": "a while loop"}


class CompliantAgentsClient:
    """A fake gateway for the four content agents in ``src/agents``.

    Mentor, concept, question-bank and test-help prompts each open with a
    distinct role line, and all four render grounded content as ``[chunk_id]``
    marker lines followed by the chunk text. This reads both back out and
    answers with output that cites real ids and quotes real text, so the
    grounding and support validators see something they can actually verify -
    which is what the deleted ``_mock_response`` bodies did, from inside the
    production classes.

    An unrecognised prompt raises. A double that answers a prompt it does not
    understand turns a wiring mistake into a confusing failure elsewhere.
    """

    _CHUNK = re.compile(r"^\[([^\]\n]+)\]\n(.*?)(?=\n\n\[|\Z)", re.DOTALL | re.MULTILINE)
    _CONTENT = re.compile(
        r"Educational Content:\n(.*?)\n\s*(?:User Question|Requested Question Type):",
        re.DOTALL,
    )
    _DIFFICULTY = re.compile(r"Difficulty:\n\s*(\S+)")
    _COUNT = re.compile(r"Number of Questions:\s*\n?\s*(\d+)")
    _TYPE = re.compile(r"Requested Question Type:\n\s*(\S+)")

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.chat = self
        self.completions = self

    def _grounding(self, prompt: str) -> tuple[str, str]:
        """Return a ``(segment_id, text)`` pair drawn from the prompt itself."""
        block = self._CONTENT.search(prompt)
        content = block.group(1).strip() if block else ""

        chunks = self._CHUNK.findall(content)
        if chunks:
            chunk_id, text = chunks[0]
            return chunk_id.strip(), text.strip()

        # Ungrounded call: the agent was handed a plain string, so there are no
        # ids to cite. Quote the content so support validation still has
        # something real to check.
        return "chunk_001", (content or "Relevant content excerpt.")

    def _questions(self, prompt: str, segment_id: str, text: str) -> str:
        count_match = self._COUNT.search(prompt)
        type_match = self._TYPE.search(prompt)
        difficulty = self._DIFFICULTY.search(prompt)
        question_type = type_match.group(1) if type_match else "mcq"
        questions = [
            {
                "question": f"Question {index + 1} about the supplied content?",
                # Must match what question_bank.yaml:72-79 tells the model and
                # what the schema enforces: ["True", "False"] for true_false,
                # null for short_answer, and correct_answer drawn from options.
                # The double used to answer None for every non-mcq type, so a
                # true_false generation failed schema validation.
                "options": _OPTIONS_FOR.get(question_type),
                "correct_answer": _ANSWER_FOR.get(question_type, "while"),
                "rationale": text[:240],
                "difficulty": difficulty.group(1) if difficulty else "beginner",
                "type": question_type,
                "references": [{"segment_id": segment_id, "text": text[:240]}],
            }
            for index in range(int(count_match.group(1)) if count_match else 1)
        ]
        return json.dumps({"questions": questions, "requires_human_review": True})

    def create(self, **kwargs: Any) -> Reply:
        self.calls.append(kwargs)
        prompt = kwargs["messages"][0]["content"]
        segment_id, text = self._grounding(prompt)
        references = [{"segment_id": segment_id, "text": text[:240]}]

        if "educational mentor" in prompt:
            return Reply(
                json.dumps(
                    {
                        "explanation": text,
                        "key_points": [text],
                        "next_steps": [text],
                        "references": references,
                        "requires_human_review": True,
                    }
                )
            )

        if "concept explanation assistant" in prompt:
            return Reply(
                json.dumps(
                    {
                        "definition": text,
                        "explanation": text,
                        "key_points": [text],
                        "references": references,
                        "requires_human_review": True,
                    }
                )
            )

        if "assessment specialist" in prompt or "test preparation assistant" in prompt:
            return Reply(self._questions(prompt, segment_id, text))

        raise AssertionError(
            "CompliantAgentsClient does not recognise this prompt; it serves the "
            "mentor, concept, question-bank and test-help agents. Prompt began: "
            f"{prompt[:200]!r}"
        )


def compliant_study_agents():
    """A (flashcard, plan, revision) triple wired to compliant fake gateways.

    What ``run_full_batch(dataset)`` needs: one agent per lane, each answering
    per-row prompts it cannot know in advance.
    """
    from src.study.flashcard_agent import FlashcardAgent
    from src.study.revision_agent import RevisionAgent
    from src.study.study_plan_agent import StudyPlanAgent

    return (
        FlashcardAgent(client=CompliantStudyClient(), model="test-model"),
        StudyPlanAgent(client=CompliantStudyClient(), model="test-model"),
        RevisionAgent(client=CompliantStudyClient(), model="test-model"),
    )


@pytest.fixture
def fake_client() -> FakeLLMClient:
    """An empty fake client; queue replies with ``client._replies`` or reuse."""
    return FakeLLMClient()
