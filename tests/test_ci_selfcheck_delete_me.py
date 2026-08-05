"""Scratch: prove the pytest gate fails. Deleted immediately after."""


def test_this_must_fail() -> None:
    assert 1 == 2, "deliberate failure to prove the pytest gate works"
