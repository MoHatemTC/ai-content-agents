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
doubles live in :mod:`src.testing.compliant` (never in this module — importing
this module from production code would wipe gateway credentials at import time)
and are re-exported here so tests can keep writing ``from tests.conftest import
CompliantAgentsClient``.
"""

from __future__ import annotations

import os

import pytest

from src.testing.compliant import (
    FakeLLMClient,
    Reply,
    CompliantAgentsClient,
    CompliantStudyClient,
    flashcard_reply,
    revision_reply,
    study_plan_reply,
)

os.environ["CHROMA_DIR"] = ""
os.environ.setdefault("RETRIEVAL_EMBEDDER", "hashing")

# Keep the suite offline: a developer's ``.env`` carries live gateway
# credentials, and ``_get_llm_client`` would otherwise hand the integration
# tests a real client and reach the network. The generation/chat endpoints
# construct their clients internally, so the only way those tests stay
# deterministic is for the gateway to raise and the compliant doubles to be
# used (mirrors ``test_missing_env.py`` and the M3 doubles philosophy).
#
# The doubles are the ONLY allowed use of fabricated content. Production
# must never serve them: ``backend/generation/service._get_llm_client``
# returns a double only when this flag is set and raises a 503 otherwise.
os.environ["LITELLM_API_KEY"] = ""
os.environ["LITELLM_BASE_URL"] = ""
os.environ.setdefault("SENSEI_USE_TEST_DOUBLES", "1")


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
