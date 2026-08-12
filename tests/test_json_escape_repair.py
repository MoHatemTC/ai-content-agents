"""Tests for parsing model JSON that carries LaTeX.

The agents ask for mathematics as LaTeX, and the model writes it inside JSON
string values: ``$x_1, \\dots, x_n$``. ``\\d`` is not one of JSON's escapes
(``\\" \\\\ \\/ \\b \\f \\n \\r \\t \\uXXXX``), so a reply that is otherwise
complete and correct is rejected by the parser.

``chat_json`` sends ``response_format: json_object`` to prevent this and its
docstring records that fixing 8 of 8 cases. It no longer holds for
``gemini/gemini-flash-lite-latest``: measured against the real textbook, 3 of 6
identical Mentor requests came back with ``Invalid \\escape``.
"""

from __future__ import annotations

import json

import pytest

from src.llm_gateway import loads_model_json


def test_parses_ordinary_json_untouched() -> None:
    assert loads_model_json('{"explanation": "no maths here"}') == {
        "explanation": "no maths here"
    }


def test_repairs_the_latex_that_broke_mentor() -> None:
    """The exact shape observed live, from the real Linear Algebra textbook."""
    raw = r'{"explanation": "such as $x_1, \dots, x_n$ in $\mathbb{R}^n$"}'

    parsed = loads_model_json(raw)

    # The backslashes survive: the model meant LaTeX and the reader needs it.
    assert parsed["explanation"] == r"such as $x_1, \dots, x_n$ in $\mathbb{R}^n$"


def test_repairs_a_u_that_is_not_a_unicode_escape() -> None:
    r"""``\underline`` starts with ``\u`` but is not ``\uXXXX``.

    Treating every ``\u`` as valid leaves LaTeX's ``\underline`` and
    ``\uparrow`` unrepaired and still failing.
    """
    parsed = loads_model_json(r'{"t": "$\underline{x}$ and $\uparrow$"}')

    assert parsed["t"] == r"$\underline{x}$ and $\uparrow$"


def test_preserves_escapes_that_were_already_correct() -> None:
    r"""A correct ``\\`` must not be doubled again.

    Scanning naively turns an already-escaped ``\\d`` into ``\\\d`` - valid
    input corrupted by the repair meant to help it.
    """
    raw = '{"a": "line\\nbreak", "b": "back\\\\slash", "c": "quote\\"inside"}'

    parsed = loads_model_json(raw)

    assert parsed["a"] == "line\nbreak"
    assert parsed["b"] == "back\\slash"
    assert parsed["c"] == 'quote"inside'


def test_unicode_escapes_still_decode() -> None:
    assert loads_model_json(r'{"t": "éè"}')["t"] == "éè"


def test_structurally_broken_json_still_raises() -> None:
    """Repair fixes escapes, not truncation. A cut-off reply is still an error."""
    with pytest.raises(json.JSONDecodeError):
        loads_model_json('{ "explanation": "cut off')


def test_prose_instead_of_json_still_raises() -> None:
    with pytest.raises(json.JSONDecodeError):
        loads_model_json("this is not valid json")


def test_repaired_latex_round_trips_through_a_realistic_reply() -> None:
    """A full agent-shaped payload, the way the failure actually arrived."""
    raw = (
        r'{"explanation": "A solution is a list $(s_1, \dots, s_n)$ '
        r'that makes each equation true.", '
        r'"key_points": ["Row reduce to $\mathrm{RREF}$"], '
        r'"references": [{"segment_id": "doc-c0027", "text": "\Delta x"}], '
        r'"requires_human_review": true}'
    )

    parsed = loads_model_json(raw)

    assert r"$(s_1, \dots, s_n)$" in parsed["explanation"]
    assert parsed["key_points"] == [r"Row reduce to $\mathrm{RREF}$"]
    assert parsed["references"][0]["text"] == r"\Delta x"
    assert parsed["requires_human_review"] is True
