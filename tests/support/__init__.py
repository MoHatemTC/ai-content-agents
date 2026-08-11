"""Test-only helpers that are too heavy for ``conftest.py``.

``conftest.py`` is imported before every test module, so anything that pulls
an optional dependency belongs here instead - importing it is then a choice
the importing module makes, not a cost every test run pays.
"""
