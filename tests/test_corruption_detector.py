r"""The last line of defence when a LaTeX command is mis-read as an escape.

``loads_model_json`` protects the commands it knows. Anything it misses decodes
to a control character - ``\bowtie`` to BACKSPACE + "owtie" - and then nothing
downstream notices: the reply parses, satisfies the schema, passes grounding and
reaches the learner as mangled words.

These tests were listed in the plan for the previous change and not written,
which is exactly why the check shipped reading ``raw_response`` - a string in
which the control character cannot appear, because it only exists after
decoding. The check was dead and looked like a guarantee.
"""

from __future__ import annotations

import json

import pytest

from src.agents.mentor_agent import MentorAgent
from src.llm_gateway import CORRUPTION_MARKERS
from tests.conftest import FakeLLMClient

BACKSPACE = "\x08"
TAB = "\x09"
FORM_FEED = "\x0c"


def good_reply(explanation: str = "A vector space is closed under addition.") -> str:
    return json.dumps(
        {
            "explanation": explanation,
            "key_points": ["Closed under addition"],
            "next_steps": ["Try the exercises"],
            "references": [{"segment_id": "seg1", "text": "vector spaces"}],
            "requires_human_review": True,
        }
    )


def reply_containing(marker: str) -> str:
    """A structurally valid reply whose text carries a control character.

    The marker is followed by a space on purpose. A backslash-b followed by
    *letters* is now recovered as LaTeX before it can ever decode, so the only
    way a real backspace survives to be detected is when no command could
    plausibly follow it.
    """
    return good_reply(f"the value {marker} is wrong")


def test_markers_cover_the_characters_commands_decode_to() -> None:
    assert BACKSPACE in CORRUPTION_MARKERS  # \b, e.g. \beta \bowtie
    assert FORM_FEED in CORRUPTION_MARKERS  # \f, e.g. \frac \flat
    assert TAB in CORRUPTION_MARKERS  # \t, e.g. \times \theta
    assert "\n" not in CORRUPTION_MARKERS, (
        "a newline is ordinary in an explanation; flagging it would reject "
        "every well-formed reply"
    )


@pytest.mark.parametrize("marker", [BACKSPACE, TAB, FORM_FEED])
def test_a_reply_carrying_a_control_character_is_rejected(marker: str) -> None:
    """It parses and fits the schema. It is still wrong, and this is the only
    place left that can say so."""
    client = FakeLLMClient(reply_containing(marker), reply_containing(marker))
    agent = MentorAgent(client=client, model="m")

    with pytest.raises(ValueError, match="mis-read as an escape"):
        agent.generate("Vector spaces.", "Explain vector spaces.")


def test_a_b_command_no_list_knows_is_recovered_outright() -> None:
    r"""``\bowtie`` needs no retry and no list entry.

    A BACKSPACE followed by letters cannot be anything but a mis-read command,
    so it is repaired before decoding. This is the case the previous check
    claimed to handle and could not; it is now handled one layer earlier, and
    the answer is kept rather than thrown away.
    """
    corrupt = json.dumps(
        {
            "explanation": "a " + BACKSPACE + "owtie b",
            "key_points": ["x"],
            "next_steps": ["y"],
            "references": [{"segment_id": "seg1", "text": "t"}],
            "requires_human_review": True,
        }
    )
    client = FakeLLMClient(corrupt, good_reply())
    agent = MentorAgent(client=client, model="m")

    result = agent.generate("Vector spaces.", "Explain vector spaces.")

    assert r"\bowtie" in result.explanation
    assert len(client.calls) == 1, "recovery should not have cost a second sample"


def test_a_t_command_no_list_knows_is_rejected_and_retried() -> None:
    r"""``\triangleq`` is real LaTeX and deliberately not listed.

    ``\t`` is also a real tab, so unlike the b/f case it cannot be assumed to
    be a command - which is exactly when the detector has to earn its keep. The
    boundary check stops ``triangle`` matching the front of ``triangleq``, so
    this decodes to a tab and must be refused rather than served.
    """
    corrupt = json.dumps(
        {
            "explanation": "a" + TAB + "riangleq b",
            "key_points": ["x"],
            "next_steps": ["y"],
            "references": [{"segment_id": "seg1", "text": "t"}],
            "requires_human_review": True,
        }
    )
    client = FakeLLMClient(corrupt, good_reply())
    agent = MentorAgent(client=client, model="m")

    result = agent.generate("Vector spaces.", "Explain vector spaces.")

    assert result.explanation == "A vector space is closed under addition."
    assert len(client.calls) == 2, "the corrupt sample was served instead of retried"


def test_a_clean_reply_is_not_rejected() -> None:
    """Newlines and ordinary punctuation must not trip the detector."""
    client = FakeLLMClient(good_reply("First line.\nSecond line, e.g. this one."))
    agent = MentorAgent(client=client, model="m")

    result = agent.generate("Vector spaces.", "Explain vector spaces.")

    assert "\n" in result.explanation
    assert len(client.calls) == 1
