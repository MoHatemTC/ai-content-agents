"""Sprint-4 QA: LLM-judged quality checks for the question agents.

The deterministic suite in ``test_question_agents.py`` proves what can be
proved by inspection - counts, types, whether the answer key is among the
options. It cannot answer the question the brief actually leads with: *are the
generated questions derived from the selected source content?* That is a
semantic judgement, so it needs a judge.

**These tests deliberately run against the real agent and the real gateway.**
Judging ``CompliantAgentsClient`` output would be theatre: it emits
``"Question 1 about the supplied content?"`` with ``correct_answer="while"``
regardless of input, so any score would describe the fixture.

Consequently they are double-gated - on ``RUN_DEEPEVAL_TESTS`` and on the
gateway actually being reachable - and excluded from CI by construction, since
``requirements.txt`` installs ``.[ocr,dev]`` and deepeval lives in ``.[eval]``.

Run with::

    pip install -e ".[eval]"
    RUN_DEEPEVAL_TESTS=true python -m pytest tests/features/test_question_agents_deepeval.py -v

Scores are non-deterministic. Treat a failure as a prompt to look, not as a
number to quote: the report quotes min/median/max over repeated runs, produced
by ``scripts/run_question_agents_deepeval.py``.
"""

from __future__ import annotations

import os

import pytest

from src.llm_gateway import gateway_availability

RUN = os.getenv("RUN_DEEPEVAL_TESTS", "").lower() == "true"
_AVAILABLE, _WHY_NOT = gateway_availability()

pytestmark = [
    pytest.mark.deepeval,
    pytest.mark.skipif(
        not RUN,
        reason="Set RUN_DEEPEVAL_TESTS=true and pip install -e '.[eval]' to run.",
    ),
    pytest.mark.skipif(
        RUN and not _AVAILABLE,
        reason=f"deepeval judges a live agent, and the gateway is not reachable: {_WHY_NOT}",
    ),
]

# Imported inside the gate so a machine without deepeval - which is every CI
# machine - never tries to import it. `pytest.importorskip` at module scope
# would still execute this module's imports on collection.
if RUN and _AVAILABLE:
    from deepeval.metrics import FaithfulnessMetric, GEval
    from deepeval.test_case import LLMTestCase, SingleTurnParams

    from src.agents.question_bank_agent import QuestionBankAgent
    from src.agents.test_help_agent import TestHelpAgent
    from tests.support.deepeval_judge import LiteLLMJudge


# A passage with enough structure that a question can be *wrong* about it -
# two loop kinds with distinguishable behaviour, so a distractor can be
# plausible-but-false rather than obviously absurd.
SOURCE = (
    "Python provides two kinds of loop. A for loop iterates over the items of "
    "a sequence, such as a list or a string, and stops when the sequence is "
    "exhausted. A while loop evaluates a condition before each pass and "
    "repeats for as long as that condition remains true; if the condition "
    "never becomes false the loop runs forever. The break statement exits the "
    "innermost enclosing loop immediately, while continue skips the rest of "
    "the current pass and begins the next one."
)

THRESHOLD = 0.7
"""A floor, not a grade.

Set loosely on purpose. An LLM judge scoring a three-question bank has a wide
run-to-run spread, so a tight threshold would produce flaky failures that teach
people to rerun until green. This is a smoke alarm.
"""


@pytest.fixture(scope="module")
def judge():
    return LiteLLMJudge()


@pytest.fixture(scope="module")
def generated():
    """Generate one question bank per agent, once, and reuse it.

    Module-scoped because each generation is a real API call, and every metric
    below scores the same output - regenerating per test would multiply cost
    and, worse, mean the metrics disagreed about different outputs.
    """
    results = {}
    for name, agent_class in (
        ("question_bank", QuestionBankAgent),
        ("test_help", TestHelpAgent),
    ):
        agent = agent_class()
        results[name] = agent.generate(SOURCE, "mcq", "beginner", 3)
    return results


def assertive_rendering(item) -> str:
    """The question as a set of claims, with the distractors removed.

    This is the single most important detail in this file. Distractors are
    *deliberately false statements*; a faithfulness metric extracts claims from
    ``actual_output`` and checks them against the source, so including the
    options would make a perfectly correct question bank score near zero. What
    the agent asserts is the stem, the marked answer, and the rationale.
    """
    return (
        f"{item.question}\n"
        f"The correct answer is: {item.correct_answer}\n"
        f"Because: {item.rationale}"
    )


def full_rendering(item) -> str:
    """The whole question including options - for judging the distractors."""
    options = "\n".join(f"- {o}" for o in (item.options or []))
    return (
        f"{item.question}\n{options}\n"
        f"Marked correct: {item.correct_answer}\n"
        f"Rationale: {item.rationale}"
    )


def derivability_metric(judge) -> "GEval":
    """Penalise claims the source does not state - not merely ones it contradicts.

    This exists because ``FaithfulnessMetric`` does not answer the brief's
    question. Measured, not assumed: a wholly fabricated question -

        "Which Python loop runs on the GPU by default?
         The correct answer is: the parallel-for loop
         Because: Python compiles for loops to CUDA kernels automatically."

    - scored **1.00** against this passage, with the reason "completely
    faithful to the retrieval context with no contradictions found". The
    passage says nothing about GPUs, so nothing in the invention *contradicts*
    it, and Faithfulness is a contradiction detector.

    "Grounded in the selected content" means derived *from* the source, so
    absence has to be penalised explicitly. That is what these steps do.
    """
    return GEval(
        name="Source derivability",
        model=judge,
        async_mode=False,
        threshold=THRESHOLD,
        evaluation_params=[
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.CONTEXT,
        ],
        evaluation_steps=[
            "Read the source passage in 'context'. It is the only admissible "
            "information.",
            "List the factual claims in 'actual_output': the question stem, "
            "the marked answer, and the rationale.",
            "A claim counts as SUPPORTED when the passage states it or "
            "directly implies it. Rewording, paraphrase, summarising and "
            "changes of grammatical form are all still supported - judge the "
            "meaning, not the wording.",
            "A claim counts as UNSUPPORTED only when it introduces information "
            "the passage does not contain. Note that a claim can be perfectly "
            "true in general and still be unsupported here.",
            "Score high when every claim is supported. Score low in proportion "
            "to how much unsupported information has been introduced.",
        ],
    )


@pytest.mark.parametrize("agent_name", ["question_bank", "test_help"])
def test_questions_are_derived_from_the_source_content(
    judge, generated, agent_name
) -> None:
    """The brief's first requirement, and the one nothing in the code checks.

    Neither agent runs verify_references or validate_support - and
    validate_support would be vacuous for them anyway, since _CLAIM_FIELDS
    covers definition/explanation/key_points/next_steps and QuestionItem has
    none of those (BUG-12). These metrics are the only grounding signal that
    exists for these two agents.

    Both are applied because they catch different failures: Faithfulness
    catches a question that *contradicts* the source, derivability catches one
    invented alongside it. Faithfulness alone passes pure fabrication - see
    :func:`derivability_metric`.
    """
    output = generated[agent_name]
    assert output.questions, "the agent returned no questions to judge"

    faithfulness = FaithfulnessMetric(
        threshold=THRESHOLD, model=judge, async_mode=False, include_reason=True
    )
    derivability = derivability_metric(judge)

    failures = []
    for index, item in enumerate(output.questions, start=1):
        claims = assertive_rendering(item)
        faithfulness.measure(
            LLMTestCase(
                input="Write beginner multiple-choice questions about this passage.",
                actual_output=claims,
                retrieval_context=[SOURCE],
            )
        )
        if faithfulness.score is None or faithfulness.score < THRESHOLD:
            failures.append(
                f"  Q{index} contradicts the source "
                f"({faithfulness.score}): {faithfulness.reason}"
            )

        derivability.measure(
            LLMTestCase(
                input="Write beginner multiple-choice questions about this passage.",
                actual_output=claims,
                context=[SOURCE],
            )
        )
        if derivability.score is None or derivability.score < THRESHOLD:
            failures.append(
                f"  Q{index} not derivable from the source "
                f"({derivability.score}): {derivability.reason}"
            )

    assert not failures, (
        f"{agent_name}: questions not grounded in the source passage:\n"
        + "\n".join(failures)
    )


@pytest.mark.parametrize("agent_name", ["question_bank", "test_help"])
def test_distractors_are_plausible(judge, generated, agent_name) -> None:
    """A distractor nobody would pick makes the question worthless.

    Nothing built into deepeval expresses this, and nothing deterministic can:
    "wrong but tempting" is exactly the judgement a rubric is for.
    """
    output = generated[agent_name]

    metric = GEval(
        name="Distractor plausibility",
        model=judge,
        async_mode=False,
        threshold=THRESHOLD,
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.CONTEXT,
        ],
        evaluation_steps=[
            "Read the source material given in 'context'.",
            "In 'actual_output', identify the marked correct answer and the "
            "remaining options, which are the distractors.",
            "Penalise heavily any distractor that is absurd, off-topic, or a "
            "joke, since no learner would ever select it.",
            "Penalise any distractor that gives itself away by being much "
            "longer, much shorter, or grammatically inconsistent with the others.",
            "Penalise any distractor that is also defensibly correct according "
            "to the source, since that makes the question unanswerable.",
            "Reward distractors that describe a real, related idea from the "
            "source that a learner who half-understood the passage would "
            "plausibly choose.",
        ],
    )

    failures = []
    for index, item in enumerate(output.questions, start=1):
        if not item.options:
            failures.append(f"  Q{index} has no options at all (see BUG-05)")
            continue
        case = LLMTestCase(
            input="Write beginner multiple-choice questions about this passage.",
            actual_output=full_rendering(item),
            context=[SOURCE],
        )
        metric.measure(case)
        if metric.score is None or metric.score < THRESHOLD:
            failures.append(f"  Q{index} scored {metric.score}: {metric.reason}")

    assert not failures, f"{agent_name}: weak distractors:\n" + "\n".join(failures)


@pytest.mark.parametrize("agent_name", ["question_bank", "test_help"])
def test_the_marked_answer_is_the_defensible_one(judge, generated, agent_name) -> None:
    """Is the answer key right?

    The deterministic suite can check the key is *among* the options
    (BUG-04). Whether it is the *correct* one given the source is a semantic
    question, and it is the failure that would do the most damage: a confidently
    mis-keyed question teaches the wrong thing and marks the right answer wrong.
    """
    output = generated[agent_name]

    metric = GEval(
        name="Answer key correctness",
        model=judge,
        async_mode=False,
        threshold=THRESHOLD,
        evaluation_params=[
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.CONTEXT,
        ],
        # Deliberately phrased as qualities, not as "score 1 if / score 0 if".
        # Prescribing literal numbers fights GEval's own continuous scoring:
        # an earlier version using that wording returned 0.1 while its stated
        # reason was "the actual output correctly marks 'break' as the correct
        # answer ... this aligns with a score of 1". The reason and the number
        # disagreed, which makes the metric unusable as evidence.
        evaluation_steps=[
            "Read the source passage in 'context'.",
            "Read the question and its options in 'actual_output', and note "
            "which option is marked correct.",
            "Determine which single option the passage best supports.",
            "Reward the output when the marked option is the one the passage "
            "best supports.",
            "Penalise the output when a different option is better supported, "
            "or when the passage does not settle the question at all.",
            "Judge correctness against the passage only. Ignore style, "
            "wording, difficulty and how plausible the other options are.",
        ],
    )

    failures = []
    for index, item in enumerate(output.questions, start=1):
        case = LLMTestCase(
            input="Write beginner multiple-choice questions about this passage.",
            actual_output=full_rendering(item),
            context=[SOURCE],
        )
        metric.measure(case)
        if metric.score is None or metric.score < THRESHOLD:
            failures.append(
                f"  Q{index} scored {metric.score}: {metric.reason}\n"
                f"      question: {item.question}\n"
                f"      marked  : {item.correct_answer}"
            )

    assert not failures, (
        f"{agent_name}: answer key not defensible from the source:\n"
        + "\n".join(failures)
    )
