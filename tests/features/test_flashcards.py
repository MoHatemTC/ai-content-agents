"""Tests for the flashcard agent, formatters, and topic extraction."""

from __future__ import annotations


import pytest

from src.study.batch import default_demo_dataset, run_flashcard_batch
from src.study.flashcard_agent import (
    FlashcardAgent,
    GroundingError,
)
from src.study.formatters import format_flashcard_set


SAMPLE_CONTENT = (
    "Python Programming Basics. Python is a high-level interpreted language. "
    "Key concepts: Functions, Loops, Classes, Lists, Dictionaries. "
    "Functions are reusable pieces of code defined with the def keyword. "
    "Loops iterate over sequences: for loops and while loops. "
    "Classes enable object-oriented programming. "
    "Lists store ordered sequences; Dictionaries map keys to values."
)


class TestTopicExtraction:
    def test_extract_topics_is_deterministic_subset_of_content(self):
        topics = FlashcardAgent.extract_topics(SAMPLE_CONTENT)
        assert isinstance(topics, list)
        # Should capture the capitalised concept names. `expected` used to be
        # built and then never used, while the loop below checked three of its
        # six entries - so the test named an intent it did not enforce.
        found = {topic.lower() for topic in topics}
        expected = {"functions", "loops", "classes", "lists", "dictionaries", "python"}
        for word in expected:
            assert any(word in topic for topic in found), word

    def test_extract_topics_handles_empty_content(self):
        assert FlashcardAgent.extract_topics("") == []
        assert FlashcardAgent.extract_topics("   ") == []

    def test_extract_topics_respects_max_topics_cap(self):
        long_content = " ".join([f"Topic{i}" for i in range(100)])
        topics = FlashcardAgent.extract_topics(long_content, max_topics=5)
        assert len(topics) <= 5


class TestFlashcardAgent:
    def test_generate_term_definition(self):
        agent = FlashcardAgent(mock_mode=True)
        card_set = agent.generate(
            SAMPLE_CONTENT, card_format="term-definition", card_count=5
        )
        assert card_set.needs_human_review is True
        assert len(card_set.cards) == 5
        for c in card_set.cards:
            assert c.format == "term-definition"
            assert c.source_topic is not None

    def test_generate_qa_format(self):
        agent = FlashcardAgent(mock_mode=True)
        card_set = agent.generate(
            SAMPLE_CONTENT, card_format="qa", card_count=3
        )
        assert all(c.format == "qa" for c in card_set.cards)
        assert len(card_set.cards) == 3

    def test_invalid_format_raises(self):
        agent = FlashcardAgent(mock_mode=True)
        with pytest.raises(ValueError):
            agent.generate(SAMPLE_CONTENT, card_format="bad", card_count=3)

    def test_empty_content_raises(self):
        agent = FlashcardAgent(mock_mode=True)
        with pytest.raises(ValueError):
            agent.generate("", card_count=3)

    def test_source_topics_are_subset_of_extracted(self):
        agent = FlashcardAgent(mock_mode=True)
        extracted = FlashcardAgent.extract_topics(SAMPLE_CONTENT)
        card_set = agent.generate(SAMPLE_CONTENT, card_count=5)
        used_topics = {c.source_topic for c in card_set.cards if c.source_topic}
        assert used_topics.issubset(set(extracted) | {None})

    def test_grounding_validation_rejects_out_of_list(self, monkeypatch):
        agent = FlashcardAgent(mock_mode=True)
        original = agent._mock_response

        def _bad(*_a, **_kw):
            good = original(*_a, **_kw)
            # Inject a fabricated card with a source_topic that is NOT in the
            # extraction allow-list to trigger the validation failure.
            bad_card = good.cards[0].model_copy(
                update={"source_topic": "Completely Fake Hallucinated Topic"}
            )
            good.cards.append(bad_card)
            return good

        monkeypatch.setattr(agent, "_mock_response", _bad)
        with pytest.raises(GroundingError):
            agent.generate(SAMPLE_CONTENT, card_count=3)


class TestFlashcardFormatters:
    def test_format_flashcard_set_is_json_safe(self):
        agent = FlashcardAgent(mock_mode=True)
        card_set = agent.generate(SAMPLE_CONTENT, card_count=3)
        as_dict = format_flashcard_set(card_set)
        # Should be dict-of-primitives only (no date objects needed here, but
        # still validate that a round-trip via json works).
        import json

        text = json.dumps(as_dict)
        assert text
        round_tripped = json.loads(text)
        assert round_tripped["needs_human_review"] is True


class TestFlashcardBatch:
    def test_batch_runs_over_default_dataset(self):
        dataset = default_demo_dataset()
        results = run_flashcard_batch(dataset, card_count=5)
        assert len(results) == len(dataset)
        for r in results:
            assert r.error is None
            assert len(r.card_set.cards) >= 1
            assert r.card_set.needs_human_review is True
