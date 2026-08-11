from __future__ import annotations

import re

# What a PDF leaves behind where a maths symbol used to be.
#
# A textbook typesets maths in symbol fonts whose glyph codes are not Unicode,
# so PyMuPDF emits the raw code. Measured on Linear Algebra and Its
# Applications: 781 of 861 chunks affected - 91% - and 21,199 characters in
# total, 0x00 alone appearing 9,920 times.
#
#     '... the only solution of the original system is (1, 0, \x021) ...'
#
# That \x02 is almost certainly a minus sign.
#
# Tab, newline and carriage return are excluded: they are whitespace, and the
# rule below already collapses them.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]+")

# What replaces them. A visible marker rather than nothing, because the model
# has to be able to tell that something was lost.
#
# Stripping is the tempting option and it is the dangerous one: '(1, 0, \x021)'
# would become '(1, 0, 1)', turning a minus into its opposite and presenting the
# result as fact. Mapping them to real symbols is no better - the encoding is
# font-dependent, and in this document 0x15 appears both as a relation and as a
# Greek letter, so a fixed table would silently corrupt some equations while
# fixing others.
#
# So the gap is marked and the prompts are told to say the source is unclear
# there rather than reconstruct it. A visible gap the agent can report beats an
# invisible one it guesses at.
UNREADABLE_MARKER = "[?]"


class TextCleaner:
    """Normalize raw extracted text before chunking."""

    @staticmethod
    def clean(text: str) -> str:
        """Mark unreadable characters, then collapse all whitespace runs.

        Note this flattens the document onto one line: newlines are whitespace,
        so paragraph structure does not survive. That is the established
        behaviour and ``test_text_cleaner`` asserts it.

        Args:
            text:
                Raw extracted text.

        Returns:
            Cleaned text, with control characters replaced by
            :data:`UNREADABLE_MARKER` and whitespace collapsed.
        """
        marked = _CONTROL_CHARS.sub(UNREADABLE_MARKER, text)
        return re.sub(r"\s+", " ", marked).strip()
