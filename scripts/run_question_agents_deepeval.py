"""Evidence generator for the Sprint-4 QA report.

Runs the LLM-judged metrics over the question agents N times and prints
min/median/max per metric. A single judge score is not reportable: the same
code scores differently run to run, so a report quoting one number is quoting
noise. The spread is the finding.

Also runs the negative controls, because a metric that cannot fail is not
evidence that anything passed. Two of these three metrics were wrong on the
first attempt and only the controls showed it.

Usage::

    pip install -e ".[eval]"
    python scripts/run_question_agents_deepeval.py            # 3 repeats
    python scripts/run_question_agents_deepeval.py --repeats 5

Costs real API calls: roughly 40 judge calls per repeat.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_ROOT / ".env")

os.environ.setdefault("RUN_DEEPEVAL_TESTS", "true")

from deepeval.metrics import FaithfulnessMetric, GEval  # noqa: E402
from deepeval.test_case import LLMTestCase, SingleTurnParams  # noqa: E402

from src.agents.question_bank_agent import QuestionBankAgent  # noqa: E402
from src.agents.test_help_agent import TestHelpAgent  # noqa: E402
from src.llm_gateway import default_model, gateway_availability  # noqa: E402
from tests.features.test_question_agents_deepeval import (  # noqa: E402
    SOURCE,
    THRESHOLD,
    assertive_rendering,
    derivability_metric,
    full_rendering,
)
from tests.support.deepeval_judge import LiteLLMJudge, judge_model  # noqa: E402

AGENTS = {"question_bank": QuestionBankAgent, "test_help": TestHelpAgent}
ASK = "Write beginner multiple-choice questions about this passage."

# Each control names the behaviour it proves the metric can detect. If one of
# these stops behaving as stated, the corresponding metric's passing scores
# below mean nothing.
CONTROLS = [
    (
        "derivability",
        "fabricated: GPU/CUDA claim absent from the passage",
        "Which Python loop runs on the GPU by default?\n"
        "The correct answer is: the parallel-for loop\n"
        "Because: Python compiles for loops to CUDA kernels automatically.",
        "fail",
    ),
    (
        "derivability",
        "true in general, absent from the passage",
        "Which keyword defines a Python function?\n"
        "The correct answer is: def\n"
        "Because: Python functions are introduced with the def keyword.",
        "fail",
    ),
    (
        "derivability",
        "genuinely derived from the passage",
        "Which loop evaluates a condition before each pass?\n"
        "The correct answer is: a while loop\n"
        "Because: a while loop evaluates a condition before each pass and "
        "repeats while it remains true.",
        "pass",
    ),
    (
        "answer_key",
        "mis-keyed on purpose",
        "Which loop iterates over the items of a sequence?\n- for\n- while\n"
        "- break\n- continue\nMarked correct: while\n"
        "Rationale: while loops iterate over sequences.",
        "fail",
    ),
    (
        "answer_key",
        "correctly keyed",
        "Which loop iterates over the items of a sequence?\n- for\n- while\n"
        "- break\n- continue\nMarked correct: for\n"
        "Rationale: a for loop iterates over the items of a sequence.",
        "pass",
    ),
    (
        "distractors",
        "absurd distractors",
        "Which loop repeats while a condition is true?\n- while\n- a banana\n"
        "- Tuesday\n- the colour blue\nMarked correct: while\n"
        "Rationale: A while loop repeats while its condition is true.",
        "fail",
    ),
]


def build_metrics(judge):
    faithfulness = FaithfulnessMetric(
        threshold=THRESHOLD, model=judge, async_mode=False, include_reason=True
    )
    distractors = GEval(
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
    answer_key = GEval(
        name="Answer key correctness",
        model=judge,
        async_mode=False,
        threshold=THRESHOLD,
        evaluation_params=[
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.CONTEXT,
        ],
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
    return {
        "faithfulness": faithfulness,
        "derivability": derivability_metric(judge),
        "distractors": distractors,
        "answer_key": answer_key,
    }


def spread(values: list[float]) -> str:
    if not values:
        return "no scores"
    return (
        f"min {min(values):.2f}  median {statistics.median(values):.2f}  "
        f"max {max(values):.2f}   (n={len(values)})"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--questions", type=int, default=3)
    args = parser.parse_args(argv)

    available, why_not = gateway_availability()
    if not available:
        print(f"Gateway unreachable: {why_not}", file=sys.stderr)
        return 2

    judge = LiteLLMJudge()
    metrics = build_metrics(judge)

    print("=" * 78)
    print("Sprint-4 QA evidence: Question Bank / Test Help, LLM-judged")
    print("=" * 78)
    print(f"generated at   : {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    print(f"agent model    : {default_model()}")
    print(f"judge model    : {judge_model()}")
    print(f"threshold      : {THRESHOLD}  (a floor, not a grade)")
    print(f"repeats        : {args.repeats}")
    print(f"questions asked: {args.questions}")
    print()
    print("Model ids ending in '-latest' float, so these numbers are tied to")
    print("this date. Scores are LLM-judged and vary run to run; that is why")
    print("the spread is reported rather than a single number.")
    print()

    print("-" * 78)
    print("NEGATIVE CONTROLS - a metric that cannot fail proves nothing")
    print("-" * 78)
    controls_ok = True
    for metric_name, label, output, expected in CONTROLS:
        metric = metrics[metric_name]
        case = LLMTestCase(
            input=ASK,
            actual_output=output,
            **(
                {"retrieval_context": [SOURCE]}
                if metric_name == "faithfulness"
                else {"context": [SOURCE]}
            ),
        )
        metric.measure(case)
        score = metric.score or 0.0
        got = "pass" if score >= THRESHOLD else "fail"
        ok = got == expected
        controls_ok = controls_ok and ok
        print(
            f"  [{'OK ' if ok else 'BAD'}] {metric_name:<13} {label:<48} "
            f"score={score:.2f} -> {got} (expected {expected})"
        )
    if not controls_ok:
        print()
        print("  !! A control behaved unexpectedly. Treat the scores below as")
        print("     unreliable until the metric is fixed.")
    print()

    print("-" * 78)
    print("AGENT SCORES")
    print("-" * 78)
    for agent_name, agent_class in AGENTS.items():
        print(f"\n### {agent_name}")
        collected: dict[str, list[float]] = {name: [] for name in metrics}
        counts: list[int] = []

        for run in range(1, args.repeats + 1):
            output = agent_class().generate(SOURCE, "mcq", "beginner", args.questions)
            counts.append(len(output.questions))
            print(
                f"  run {run}: asked {args.questions}, got {len(output.questions)} "
                f"question(s), requires_human_review="
                f"{output.requires_human_review}"
            )

            for index, item in enumerate(output.questions, start=1):
                claims = assertive_rendering(item)
                whole = full_rendering(item)

                metrics["faithfulness"].measure(
                    LLMTestCase(
                        input=ASK,
                        actual_output=claims,
                        retrieval_context=[SOURCE],
                    )
                )
                collected["faithfulness"].append(metrics["faithfulness"].score or 0.0)

                for name, rendering in (
                    ("derivability", claims),
                    ("distractors", whole),
                    ("answer_key", whole),
                ):
                    metrics[name].measure(
                        LLMTestCase(
                            input=ASK, actual_output=rendering, context=[SOURCE]
                        )
                    )
                    collected[name].append(metrics[name].score or 0.0)

                print(f"    Q{index}: {item.question}")
                print(
                    f"         marked={item.correct_answer!r} "
                    f"options={item.options} type={item.type.value} "
                    f"difficulty={item.difficulty.value} "
                    f"refs={len(item.references)}"
                )

        print(f"\n  count control: asked {args.questions} each run, got {counts}")
        for name in ("faithfulness", "derivability", "distractors", "answer_key"):
            print(f"  {name:<14} {spread(collected[name])}")

    print()
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
