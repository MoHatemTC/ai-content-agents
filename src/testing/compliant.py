"""Test doubles for the LLM gateway, importable by production and tests alike.

These doubles live OUTSIDE ``tests/`` on purpose. ``tests/conftest.py`` wipes
gateway credentials and pins env flags at import time to keep the suite
offline; importing it from production code therefore pollutes a running server
(the historical cause of the "Question 1 about the supplied content?" bug).
This module has no import-time side effects. Production only instantiates these
doubles when ``SENSEI_USE_TEST_DOUBLES`` is set; tests reach them via the
re-exports in ``tests/conftest.py``.
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Any


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
    chosen = (topics or ["General topic"])[: max(1, (end_date - start_date).days)]
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

    _CHUNK = re.compile(
        r"^\[([^\]\n]+)\]\n(.*?)(?=\n\n\[|\Z)", re.DOTALL | re.MULTILINE
    )
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
        question_type = (
            type_match.group(1).lower() if type_match else "mcq"
        )
        questions = [
            {
                "question": f"Question {index + 1} about the supplied content?",
                "options": ["for", "while", "if", "switch"]
                if question_type == "mcq"
                else None,
                "correct_answer": "while",
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
