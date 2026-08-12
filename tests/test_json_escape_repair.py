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


# --------------------------------------------------------------------------- #
# Valid escapes that meant something else
#
# \t and \b ARE valid JSON escapes, so `\times` decodes to TAB + "imes" and
# `\beta` to BACKSPACE + "eta" without raising anything at all. Read out of
# chat_messages, a stored reply carried 0x09 twice and 0x08 four times, and
# reached the learner as "8imes300" and "y = Ξeta_0". Silent corruption, where
# the earlier bug at least failed loudly.
# --------------------------------------------------------------------------- #


def test_times_is_latex_not_a_tab() -> None:
    """The exact text from the corrupted reply."""
    parsed = loads_model_json(r'{"t": "forms an $8 \times 300$ matrix"}')

    assert parsed["t"] == r"forms an $8 \times 300$ matrix"
    assert "\t" not in parsed["t"]


def test_beta_is_latex_not_a_backspace() -> None:
    parsed = loads_model_json(r'{"t": "$y = \beta_0 + \beta_1 x$"}')

    assert parsed["t"] == r"$y = \beta_0 + \beta_1 x$"
    assert "\b" not in parsed["t"]


@pytest.mark.parametrize(
    "command",
    [r"\theta", r"\tau", r"\frac{a}{b}", r"\forall", r"\neq", r"\nu", r"\nabla",
     r"\rho", r"\rightarrow", r"\begin{bmatrix}", r"\textbf{x}", r"\bar{x}"],
)
def test_ambiguous_initial_commands_survive(command: str) -> None:
    r"""Every LaTeX command starting with b, f, n, r or t is exposed.

    Delimited, because that is how they arrive - the prompts require it and all
    29 commands in the stored replies obeyed. Undelimited is a separate case
    with a separate answer; see
    ``test_an_undelimited_command_is_left_for_the_detector``.
    """
    parsed = loads_model_json('{"t": "$%s$"}' % command)

    assert parsed["t"] == f"${command}$"


@pytest.mark.parametrize(
    ("raw_tail", "expected"),
    [
        # \ne would eat a paragraph beginning "e.g." - ordinary prose.
        (r"line one\ne.g. this", "line one\ne.g. this"),
        # \ni would eat one beginning "i.e."
        (r"line one\ni.e. that", "line one\ni.e. that"),
    ],
)
def test_short_commands_do_not_eat_real_control_characters(
    raw_tail: str, expected: str
) -> None:
    r"""Two-letter commands guess wrong more often than they help.

    ``\ne`` and ``\ni`` are real LaTeX, but so is a paragraph that starts
    "e.g." or "i.e.", and the second is far more common in an explanation than
    the first. Dropping them costs a rendered symbol; keeping them costs the
    reader a mangled sentence.
    """
    assert loads_model_json('{"t": "%s"}' % raw_tail)["t"] == expected


@pytest.mark.parametrize(
    "command",
    [r"\bowtie", r"\flat", r"\bigsqcup", r"\forall", r"\beta", r"\begin{bmatrix}"],
)
def test_backspace_and_formfeed_commands_survive_without_a_list(
    command: str,
) -> None:
    r"""``\b`` and ``\f`` are never legitimate here, so no list is needed.

    A BACKSPACE or FORM FEED has no meaning in a study explanation, so any
    ``\b``/``\f`` followed by letters is LaTeX by construction - which covers
    the commands a hand-written list was always going to miss.
    """
    parsed = loads_model_json('{"t": "%s"}' % command)

    assert parsed["t"] == command
    assert "\b" not in parsed["t"]
    assert "\f" not in parsed["t"]


def test_a_real_newline_followed_by_a_word_stays_a_newline() -> None:
    r"""The regression the obvious fix causes.

    "Escape every backslash before a letter" would turn this into a literal
    ``\nThe``. Every real newline in the stored replies is followed by a word -
    8 of 8 were ``The`` or ``Hello`` - so that fix breaks every paragraph break
    in the app.
    """
    parsed = loads_model_json(r'{"t": "First para.\nThe second one.\nHello again."}')

    assert parsed["t"] == "First para.\nThe second one.\nHello again."


def test_escapes_the_model_got_right_are_left_alone() -> None:
    r"""``\\mathbf`` appeared 16 times in the stored corpus, correctly escaped."""
    parsed = loads_model_json(r'{"t": "$\\mathbf{v}$ and $\\begin{bmatrix}$"}')

    assert parsed["t"] == r"$\mathbf{v}$ and $\begin{bmatrix}$"


def test_a_tab_that_is_really_a_tab_is_preserved() -> None:
    """``\\t`` not followed by a command is still a tab."""
    assert loads_model_json(r'{"t": "col1\tcol2"}')["t"] == "col1\tcol2"


# --------------------------------------------------------------------------- #
# Maths delimiters decide, so no list has to
#
# Measured across the stored replies: 29 LaTeX commands inside $...$, 0 outside.
# The model delimits everything, exactly as the prompts tell it to, so "is this
# backslash inside maths?" answers what a hand-written list of command names was
# guessing at - and answers it for commands nobody thought to list.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "command",
    [
        # The two the list had to drop: they collide with "e.g." and "i.e."
        # in prose, and are unambiguous once delimited.
        r"\ne", r"\ni",
        # Names no list contained.
        r"\bowtie", r"\ltimes", r"\curlyvee", r"\nrightarrow", r"\rtimes",
    ],
)
def test_any_command_inside_maths_survives(command: str) -> None:
    parsed = loads_model_json('{"t": "the value $x %s y$ holds"}' % command)

    assert parsed["t"] == f"the value $x {command} y$ holds"


def test_display_maths_survives() -> None:
    raw = r'{"t": "the sum $$\sum_{i=1}^{n} \alpha_i x_i = \beta$$ converges"}'

    parsed = loads_model_json(raw)

    assert parsed["t"] == (
        r"the sum $$\sum_{i=1}^{n} \alpha_i x_i = \beta$$ converges"
    )


def test_a_newline_inside_display_maths_stays_a_newline() -> None:
    r"""The model lays equations out across lines, and that must survive.

    Escaping every backslash inside a span turned ``$$A =`` newline
    ``\begin{bmatrix}`` into a literal ``\n``. A command has two letters or
    more; a control escape has exactly one, which is what separates them.
    """
    raw = r'{"t": "$$A =\n\begin{bmatrix} 1 \\ 2 \end{bmatrix}$$"}'

    parsed = loads_model_json(raw)

    assert "\n" in parsed["t"], "the line break was escaped away"
    assert r"\begin{bmatrix}" in parsed["t"]
    assert r"\n\begin" not in parsed["t"]


def test_a_newline_inside_prose_is_kept_when_dollars_are_unbalanced() -> None:
    r"""Two stray currency amounts must not turn the prose between them into maths.

    "costs $5 … worth $10" is ordinary writing, and a Leontief economics chapter
    is exactly where it shows up. Without a length cap the span between them
    would be treated as maths and the newline inside it escaped away.
    """
    raw = (
        r'{"t": "the process costs $5 per unit, which is a long way of saying '
        r'that the intermediate demand is not free and has to be accounted for '
        r'somewhere in the model.\nThe output is worth $10 per unit."}'
    )

    parsed = loads_model_json(raw)

    assert "\n" in parsed["t"]
    assert r"\nThe" not in parsed["t"]


def test_an_undelimited_command_is_left_for_the_detector() -> None:
    r"""Bare ``\theta`` is indistinguishable from a tab, and is not guessed at.

    Nothing here can tell them apart, so the reply keeps its tab and
    ``find_corruption`` refuses it - one more sample rather than a wrong answer.
    That is self-correcting in a way the list never was.
    """
    parsed = loads_model_json(r'{"t": "the angle \theta is small"}')

    assert "\t" in parsed["t"]


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
