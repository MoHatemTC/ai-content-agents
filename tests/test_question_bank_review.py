"""Week 4 review, grounding, and objective option-validation coverage."""

import pytest

from src.agents.question_bank_agent import QuestionBankAgent
from src.agents.test_help_agent import TestHelpAgent
from src.retrieval.models import Chunk, GroundedContext, RetrievedChunk, RetrievalScope
from src.validation.question_rules import QuestionItemQualityRule
from src.validation.review_schema import OutputStatus
from src.validation.schemas import QuestionBankOutput, TestHelpOutput


def _context() -> GroundedContext:
    return GroundedContext(
        query="Python loops",
        scope=RetrievalScope(document_id="doc-1"),
        chunks=[
            RetrievedChunk(
                chunk=Chunk(
                    chunk_id="chunk-1",
                    document_id="doc-1",
                    ordinal=0,
                    text="Python provides two loop types: for and while.",
                ),
                score=1.0,
                rank=1,
            )
        ],
    )


@pytest.mark.parametrize("agent_class", [QuestionBankAgent, TestHelpAgent])
def test_question_agents_generate_reviewable_grounded_output(agent_class):
    agent = agent_class(mock_mode=True)
    output = agent.generate_reviewable(
        content="Python provides two loop types: for and while.",
        question_type="mcq",
        num_questions=2,
        context=_context(),
    )

    assert output.status is OutputStatus.PENDING
    assert output.validation_passed is True
    assert len(output.payload["questions"]) == 2


@pytest.mark.parametrize("agent_class", [QuestionBankAgent, TestHelpAgent])
def test_question_agents_batch_continues_after_failure(monkeypatch, agent_class):
    agent = agent_class(mock_mode=True)
    original = agent.generate

    def generate(**item):
        if item["content"] == "bad":
            raise ValueError("generation failed")
        return original(**item)

    monkeypatch.setattr(agent, "generate", generate)
    result = agent.generate_batch([
        {"content": "first"}, {"content": "bad"}, {"content": "third"}
    ])

    assert result.total_succeeded == 2
    assert result.failed_items[0].index == 1


def test_question_quality_rule_flags_invalid_options():
    output = QuestionBankOutput.model_validate(
        {
            "questions": [{
                "question": "Which loop exists?",
                "options": ["for", "for"],
                "correct_answer": "while",
                "rationale": "Python has for and while loops.",
                "difficulty": "beginner",
                "type": "mcq",
                "references": [{"segment_id": "chunk-1", "text": "loops"}],
            }],
            "requires_human_review": True,
        }
    )

    violation = QuestionItemQualityRule().check(output, None)  # context unused
    assert violation is not None
    assert "duplicate options" in violation.message
    assert "correct_answer is not one of its options" in violation.message


def test_question_output_cannot_disable_human_review():
    with pytest.raises(Exception):
        TestHelpOutput.model_validate({"questions": [], "requires_human_review": False})


def test_question_bank_service_generate_reviewable():
    from src.services.question_bank import QuestionBankService

    service = QuestionBankService(mock_mode=True)
    qbank_out = service.generate_question_bank_reviewable(
        content="Python loops", question_type="mcq", difficulty="beginner", num_questions=1
    )
    assert qbank_out.output_type == "question_bank"
    assert qbank_out.status is OutputStatus.PENDING
    assert qbank_out.validation_passed is True

    test_out = service.generate_test_help_reviewable(
        content="Python loops", question_type="true_false", difficulty="beginner", num_questions=1
    )
    assert test_out.output_type == "test_help"
    assert test_out.status is OutputStatus.PENDING
    assert test_out.validation_passed is True


def test_question_quality_rule_flags_short_answer_with_options():
    output = QuestionBankOutput.model_validate(
        {
            "questions": [{
                "question": "Name Python loop types.",
                "options": ["for", "while"],
                "correct_answer": "for and while",
                "rationale": "Python provides for and while loops.",
                "difficulty": "beginner",
                "type": "short_answer",
                "references": [{"segment_id": "chunk-1", "text": "loops"}],
            }],
            "requires_human_review": True,
        }
    )
    violation = QuestionItemQualityRule().check(output, None)
    assert violation is not None
    assert "short_answer but options must be null" in violation.message


def test_question_quality_rule_flags_duplicate_stems_and_missing_references():
    output = QuestionBankOutput.model_validate(
        {
            "questions": [
                {
                    "question": "Which loop repeats?",
                    "options": ["for", "while", "if", "else"],
                    "correct_answer": "while",
                    "rationale": "While loops repeat.",
                    "difficulty": "beginner",
                    "type": "mcq",
                    "references": [],
                },
                {
                    "question": "Which loop repeats?",
                    "options": ["for", "while", "if", "else"],
                    "correct_answer": "for",
                    "rationale": "For loops repeat.",
                    "difficulty": "beginner",
                    "type": "mcq",
                    "references": [{"segment_id": "chunk-1", "text": "text"}],
                },
            ],
            "requires_human_review": True,
        }
    )
    violation = QuestionItemQualityRule().check(output, None)
    assert violation is not None
    assert "has no grounding references" in violation.message
    assert "duplicates a previous question stem" in violation.message


def test_invalid_question_type_and_difficulty():
    from src.validation.schemas import validate_difficulty, validate_question_type

    with pytest.raises(ValueError, match="Invalid question type"):
        validate_question_type("fill_in_the_blank")

    with pytest.raises(ValueError, match="Invalid difficulty"):
        validate_difficulty("expert")


def test_verify_references_handles_none_gracefully():
    from src.retrieval.grounding import verify_references

    ctx = _context()
    res = verify_references(None, ctx)
    assert res.valid is False
    assert res.unknown_segment_ids == ["<None>"]


def test_question_quality_rule_handles_empty_rationale():
    output = QuestionBankOutput.model_validate(
        {
            "questions": [{
                "question": "Which loop repeats?",
                "options": ["for", "while", "if", "else"],
                "correct_answer": "while",
                "rationale": "  ",
                "difficulty": "beginner",
                "type": "mcq",
                "references": [{"segment_id": "chunk-1", "text": "text"}],
            }],
            "requires_human_review": True,
        }
    )
    violation = QuestionItemQualityRule().check(output, None)
    assert violation is not None
    assert "has an empty rationale" in violation.message


@pytest.mark.parametrize("qtype", ["mcq", "true_false", "short_answer"])
@pytest.mark.parametrize("diff", ["beginner", "intermediate", "advanced"])
def test_question_agents_support_all_question_types_and_difficulties(qtype, diff):
    agent = QuestionBankAgent(mock_mode=True)
    out = agent.generate(
        content="Python loop content",
        question_type=qtype,
        difficulty=diff,
        num_questions=2,
        context=_context(),
    )
    assert len(out.questions) == 2
    for q in out.questions:
        assert q.type.value == qtype
        assert q.difficulty.value == diff


