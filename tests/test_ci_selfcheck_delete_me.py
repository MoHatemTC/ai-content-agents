"""Scratch: prove CI actually fails. Deleted immediately after."""


def test_this_must_fail() -> None:
    assert 1 == 2, "deliberate failure to prove the pytest gate works"


def test_undefined_name() -> Undefined:
    """Deliberate F821 to prove the ruff gate works."""
    return None
