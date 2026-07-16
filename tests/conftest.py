"""Shared pytest configuration for the test suite.

Pins ``MOCK_MODE=true`` for the entire test session so agent tests can never
make live LLM calls by accident, regardless of what a local ``.env`` contains.

This works because pytest imports ``conftest.py`` before any test module, and
``load_dotenv()`` (called at import time in the agent modules) does not override
environment variables that are already set. Tests that need the real API must
opt in explicitly and should not run in the default suite.
"""

import os

os.environ["MOCK_MODE"] = "true"
