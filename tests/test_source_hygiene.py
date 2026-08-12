"""No stray control characters in the source.

A literal ``0x08`` was committed into two agent modules - inside the comment
explaining how a backslash-b gets mis-read as a control character. It was
written through a shell heredoc, which ate the backslash and left the byte.

Nothing else in the suite could see it: it sat in a comment, so it changed no
behaviour, passed every test, and lints do not look for it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIRS = ("src", "backend", "tests", "scripts")

#: Newline and tab are the only control characters a source file should hold.
ALLOWED = {"\n", "\t", "\r"}


def python_sources() -> list[Path]:
    files: list[Path] = []
    for directory in SOURCE_DIRS:
        files.extend(
            path
            for path in (PROJECT_ROOT / directory).rglob("*.py")
            if "__pycache__" not in path.parts
        )
    return sorted(files)


@pytest.mark.parametrize("path", python_sources(), ids=lambda p: p.name)
def test_source_has_no_stray_control_characters(path: Path) -> None:
    text = path.read_text(encoding="utf-8")

    found = {
        hex(ord(char)) for char in set(text) if ord(char) < 32 and char not in ALLOWED
    }

    assert not found, (
        f"{path.relative_to(PROJECT_ROOT)} contains {sorted(found)}. A literal "
        "control character in source is almost always a backslash escape that "
        "a shell or editor consumed - write it as an escape sequence instead."
    )
