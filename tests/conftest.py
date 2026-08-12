"""Shared pytest configuration and test doubles.

Neutralises the parts of a developer's ``.env`` that would otherwise reach into
the suite, so a test run depends on the repository and nothing else.

This works because pytest imports ``conftest.py`` before any test module, and
``load_dotenv()`` (called at import time in several modules) defaults to
``override=False`` — a variable set here wins over ``.env``.

``CHROMA_DIR`` keeps tests out of a persisted retrieval index. Without this the
suite opened whatever the developer had built — for one of us a 105 MB index of
a physics textbook, embedded in live mode at 384 dimensions — and queried it
with the 256-dimension offline embedder, failing with ``Collection expecting
embedding with dimension of 384, got 256``.

That failure is invisible to CI, which has no ``.env`` at all and so always ran
in memory. A clean environment cannot reproduce a configuration bug, which is
exactly why ``test_the_suite_does_not_touch_a_persisted_index`` exists: it
passes trivially on CI and fails on the machine where the problem can occur.

``RETRIEVAL_EMBEDDER`` pins the offline hashing embedder, so no test downloads
an ONNX model or depends on one being cached.

**There is no ``MOCK_MODE``.** Agents take an injected client, and
:func:`src.llm_gateway.build_client` raises without credentials, so a test that
forgets to inject a double fails loudly instead of reaching the network. The
doubles below are what it injects; ``FakeLLMClient`` and the ``*_reply``
builders are importable from any test module (``from tests.conftest import
FakeLLMClient``) as well as available as fixtures.
"""

from __future__ import annotations

import os

import pytest

os.environ["CHROMA_DIR"] = ""
os.environ.setdefault("RETRIEVAL_EMBEDDER", "hashing")

# The FastAPI layer builds its own LLM client rather than taking an injected
# one, so this flag is the only thing standing between the backend tests and
# the real gateway. Without it they take whichever branch the environment
# offers: a developer with LITELLM_API_KEY in .env silently bills real calls
# and the tests pass, while CI has no key and every one of them returns 503.
# Both happened - the 503s are what caught it.
#
# This is the same defect PR #28 fixed for the main suite, where a developer's
# .env hid seven tests making real API calls. setdefault, so anyone who wants
# to exercise the live path can still export it as 0.
os.environ.setdefault("SENSEI_USE_TEST_DOUBLES", "1")


# The doubles themselves live in src/testing/compliant.py, because production
# instantiates them when SENSEI_USE_TEST_DOUBLES is set and must not import
# anything from tests/. They were *copied* here rather than imported, and the
# two copies drifted in both directions: this one grew the true_false/
# short_answer fix, that one grew the study-plan slicing, and the backend under
# doubles therefore behaved differently from the agents under doubles. Two
# copies of one double is the same defect the doubles exist to catch.
#
# Re-exported so `from tests.conftest import ...` keeps working everywhere.
from src.testing.compliant import (  # noqa: E402
    CompliantAgentsClient,
    CompliantStudyClient,
    FakeLLMClient,
    LatexAgentsClient,
    Reply,
    flashcard_reply,
    revision_reply,
    study_plan_reply,
    unescape_backslashes,
)

__all__ = [
    "CompliantAgentsClient",
    "CompliantStudyClient",
    "FakeLLMClient",
    "LatexAgentsClient",
    "Reply",
    "compliant_study_agents",
    "fake_client",
    "flashcard_reply",
    "revision_reply",
    "study_plan_reply",
    "unescape_backslashes",
]


def compliant_study_agents():
    """A (flashcard, plan, revision) triple wired to compliant fake gateways.

    What ``run_full_batch(dataset)`` needs: one agent per lane, each answering
    per-row prompts it cannot know in advance.
    """
    from src.study.flashcard_agent import FlashcardAgent
    from src.study.revision_agent import RevisionAgent
    from src.study.study_plan_agent import StudyPlanAgent

    return (
        FlashcardAgent(client=CompliantStudyClient(), model="test-model"),
        StudyPlanAgent(client=CompliantStudyClient(), model="test-model"),
        RevisionAgent(client=CompliantStudyClient(), model="test-model"),
    )


@pytest.fixture
def fake_client() -> FakeLLMClient:
    """An empty fake client; queue replies with ``client._replies`` or reuse."""
    return FakeLLMClient()
