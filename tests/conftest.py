"""Shared pytest configuration for the test suite.

Neutralises the parts of a developer's ``.env`` that would otherwise reach into
the suite, so a test run depends on the repository and nothing else.

This works because pytest imports ``conftest.py`` before any test module, and
``load_dotenv()`` (called at import time in several modules) defaults to
``override=False`` — a variable set here wins over ``.env``.

``MOCK_MODE`` keeps agent tests from making live LLM calls by accident. Tests
that need the real API must opt in explicitly and should not run in the default
suite.

``CHROMA_DIR`` keeps them out of a persisted retrieval index. Without this the
suite opened whatever the developer had built — for one of us a 105 MB index of
a physics textbook, embedded in live mode at 384 dimensions — and queried it
with the 256-dimension offline embedder, failing with ``Collection expecting
embedding with dimension of 384, got 256``.

That failure is invisible to CI, which has no ``.env`` at all and so always ran
in memory. A clean environment cannot reproduce a configuration bug, which is
exactly why ``test_the_suite_does_not_touch_a_persisted_index`` exists: it
passes trivially on CI and fails on the machine where the problem can occur.
"""

import os

os.environ["MOCK_MODE"] = "true"
os.environ["CHROMA_DIR"] = ""
