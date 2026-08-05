"""Tests for the flashcard agent, formatters, and topic extraction."""

from __future__ import annotations

from datetime import date

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
        # Should capture the capitalised concept names.
        tokens_lower = {t.lower() for t in topics}
        expected = {"functions", "loops", "classes", "lists", "dictionaries", "python"}
        for word in {"functions", "python", "classes"}:
            assert any(word in t.lower() for t in topics) or word in tokens_lower

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


# --------------------------------------------------------------------------- #
# The topic allow-list is the grounding contract, not a display detail
# --------------------------------------------------------------------------- #


# Shaped like the real thing: in the 1,598-page physics textbook "Fig" is the
# 13th most frequent token in the whole book, ahead of "mass", "speed" and
# "charge". A fixture where the furniture is rare would let the ranking exclude
# it and never exercise the filter at all - verified by mutation, where an
# earlier version of this fixture passed with the filter removed.
TEXTBOOK_EXTRACT = (
    "The electric field near a point charge falls off with distance. "
    "See Fig. 21.5 for the field lines drawn around a positive charge. "
    "Fig. 21.6 and Fig. 21.7 repeat the construction for a dipole. "
    "Example 21.3 works through the electric field of a dipole. "
    "Example 21.4 and Example 21.5 extend it to a ring of charge. "
    "Section 21.4 introduces the electric field of continuous charge "
    "distributions, and Figure 21.7 shows the same field as a vector map. "
    "Section 21.5 and Section 21.6 continue, as shown in Figure 21.8, and "
    "Figure 21.9 is shown alongside Problem 21.9 and Problem 21.10. "
    "The kinetic energy of the charge changes as it moves through the field, "
    "while its potential energy falls. Kinetic energy and potential energy "
    "together give the total energy. The net force on the charge is the "
    "product of charge and electric field. Problem 21.9 asks for the net "
    "force when two charges act at once. "
) * 3


class TestTopicAllowListQuality:
    def test_document_furniture_is_not_a_topic(self):
        """A physics textbook is not about figures, sections and examples.

        In the real 1,598-page book "Fig" is the 13th most frequent token -
        ahead of "mass", "speed" and "charge" - so frequency ranking alone put
        the typesetting at the top of the syllabus, and the flashcards drilled
        "Fig", "Section" and "Example".
        """
        topics = {t.lower() for t in FlashcardAgent.extract_topics(TEXTBOOK_EXTRACT, 30)}

        for junk in ("fig", "figure", "example", "section", "problem", "shown"):
            assert junk not in topics, f"{junk!r} is typesetting, not subject matter"

    def test_function_words_are_not_topics(self):
        """The old stopword list held ~50 entries and let these through."""
        topics = {t.lower() for t in FlashcardAgent.extract_topics(TEXTBOOK_EXTRACT, 30)}

        for junk in ("between", "each", "same", "which", "use", "the"):
            assert junk not in topics

    def test_real_subject_matter_survives(self):
        """Filtering must not be so aggressive that the topics vanish."""
        topics = {t.lower() for t in FlashcardAgent.extract_topics(TEXTBOOK_EXTRACT, 30)}

        assert {"charge", "energy", "field"} & topics

    def test_multi_word_terms_are_preferred(self):
        """Real topics look like "kinetic energy", not "energy"."""
        topics = {t.lower() for t in FlashcardAgent.extract_topics(TEXTBOOK_EXTRACT, 30)}

        assert any(" " in topic for topic in topics), topics
        assert "kinetic energy" in topics or "potential energy" in topics

    def test_topics_are_literal_substrings_of_the_content(self):
        """The anti-hallucination property: a topic is quoted, never invented."""
        for topic in FlashcardAgent.extract_topics(TEXTBOOK_EXTRACT, 30):
            assert topic in TEXTBOOK_EXTRACT, topic

    def test_surface_form_is_preserved(self):
        """Grounding matches by exact string, so casing is load-bearing.

        The demo dataset's hand-authored weak_topics are capitalised
        ("Gradient Descent", "DNA Replication"); lowercasing the allow-list
        would drop them out of it and silently break revision grounding.
        """
        content = "Gradient Descent is iterative. Gradient Descent minimises loss."

        assert "Gradient Descent" in FlashcardAgent.extract_topics(content, 10)

    def test_extraction_is_deterministic(self):
        first = FlashcardAgent.extract_topics(TEXTBOOK_EXTRACT, 20)
        second = FlashcardAgent.extract_topics(TEXTBOOK_EXTRACT, 20)

        assert first == second

    def test_demo_weak_topics_stay_in_the_allow_list(self):
        """Revision grounding fails outright if a selected topic is missing."""
        from src.study.batch import default_demo_dataset

        for item in default_demo_dataset():
            allowed = set(FlashcardAgent.extract_topics(item.content))
            missing = [w for w in (item.weak_topics or []) if w not in allowed]
            assert not missing, f"{item.title}: {missing}"


# --------------------------------------------------------------------------- #
# Mock output is made of the document, not about it
# --------------------------------------------------------------------------- #


class TestMockOutputIsGrounded:
    CONTENT = (
        "Conduction moves energy through a material by direct molecular contact. "
        "Convection carries heat in the bulk motion of a fluid. "
        "Radiation needs no medium: energy crosses a vacuum as electromagnetic waves."
    )

    def test_no_placeholder_phrases(self):
        """What the app actually displayed for weeks.

        Every card of every document read "X is a key concept described in the
        supplied content. See the source text for a fuller treatment." A card
        that says where the answer is instead of what it is teaches nothing,
        and the UI forced mock mode, so this was the product.
        """
        card_set = FlashcardAgent(mock_mode=True).generate(self.CONTENT, card_count=3)

        body = " ".join(card.back.lower() for card in card_set.cards)
        for phrase in ("see the source", "supplied content", "fuller treatment"):
            assert phrase not in body, f"placeholder text: {phrase!r}"

    def test_card_backs_are_quoted_from_the_content(self):
        card_set = FlashcardAgent(mock_mode=True).generate(self.CONTENT, card_count=3)

        for card in card_set.cards:
            assert card.back in self.CONTENT, card.back

    def test_cards_are_not_all_identical(self):
        """The failure mode this replaces produced one sentence, repeated."""
        card_set = FlashcardAgent(mock_mode=True).generate(self.CONTENT, card_count=3)

        assert len({card.back for card in card_set.cards}) > 1
