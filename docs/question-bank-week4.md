# Week 4 — Question Bank & Test Help Foundation

## Overview

This sprint implements the **Question Bank** and **Test Help** feature as a complete vertical slice following the same architecture introduced in Week 3.

The implementation enables the generation of grounded educational assessments from retrieved learning content while ensuring that every AI-generated output is validated, reviewable, and never presented as final without human approval.

The feature integrates with the existing retrieval, validation, review, evaluation, and benchmarking pipelines without modifying the shared application architecture.

---

# Architecture

The feature follows the same layered architecture used throughout the project.

```
Educational Content
        │
        ▼
 Retrieval Layer
 (GroundedContext)
        │
        ▼
QuestionBankService
        │
        ▼
QuestionBankAgent / TestHelpAgent
        │
        ▼
LLM Provider
        │
        ▼
Structured JSON
        │
        ▼
Pydantic Validation
        │
        ▼
Quality Guardrails
        │
        ▼
Reference Verification
        │
        ▼
Support Validation
        │
        ▼
GeneratedOutput (Pending Review)
        │
        ▼
Streamlit Review UI
```

The user interface never communicates directly with the agents.

Instead, every generation request is routed through the **QuestionBankService**, which preserves the shared review lifecycle and integrates cleanly with the rest of the application.

---

# Implemented Features

## Question Bank Agent

The Question Bank agent generates structured educational question sets from grounded educational content.

Supported question types:

- Multiple Choice (MCQ)
- True / False
- Short Answer

Supported difficulty levels:

- Beginner
- Intermediate
- Advanced

Each generated question contains:

- Question
- Question Type
- Difficulty
- Options (when applicable)
- Correct Answer
- Rationale
- Grounding References

---

## Test Help Agent

The Test Help agent follows the same architecture as the Question Bank agent while focusing on producing exam-style practice questions.

It shares:

- Prompt loading
- Validation pipeline
- Grounding verification
- Review workflow
- Batch generation
- Evaluation metrics

This keeps both agents consistent while allowing future specialization without duplicating infrastructure.

---

# Prompt Templates

Both agents use dedicated YAML prompt templates.

Implemented prompt features include:

- Structured output instructions
- Difficulty placeholders
- Question type placeholders
- JSON schema guidance
- Citation requirements
- Human review reminder
- Grounding instructions

The prompts explicitly instruct the LLM to:

- answer only using retrieved educational content
- avoid hallucinations
- generate structured JSON
- include supporting references
- provide rationales for every answer

---

# Typed Output Schemas

The agents return strongly typed Pydantic models instead of raw JSON.

Each question contains:

- question
- type
- difficulty
- options
- correct_answer
- rationale
- references

Every generated output also contains:

- requires_human_review=True

This field is immutable and guarantees that AI-generated content cannot bypass the review workflow.

---

# Grounding Pipeline

Before generation, educational content is converted into a **GroundedContext**.

The agents generate questions only from this retrieved context.

After generation:

1. Every cited reference is verified.
2. Every answer key is checked against the retrieved content.
3. Every rationale is validated.
4. Unsupported outputs are rejected before reaching the UI.

This prevents fabricated questions or unsupported answer keys from entering the review workflow.

---

# Validation Pipeline

The implementation extends the shared validation framework with question-specific guardrails.

Implemented checks include:

## Multiple Choice

- Correct answer exists in options
- Duplicate options rejected
- Minimum option count enforced
- Empty options rejected

## True / False

- Valid answer options
- Correct answer validation

## Short Answer

- Options must be null

## General Validation

- Question text required
- Rationale required
- References required
- Difficulty validation
- Question type validation
- Immutable review flag

Outputs failing validation remain blocked from review until corrected.

---

# Human Review Workflow

The Question Bank feature follows the shared review lifecycle.

Generation Flow:

```
LLM Output
      │
      ▼
Validation
      │
      ▼
Support Check
      │
      ▼
Reference Verification
      │
      ▼
GeneratedOutput
(status=PENDING)
      │
      ▼
Human Review
```

Generated content is never presented as final.

Every output is marked:

```
Requires Human Review
```

and enters the application as a pending review artifact.

---

# Batch Generation

Both agents support batch generation.

Features include:

- Sequential generation
- Failure isolation
- Order preservation
- Partial success support
- Execution timing
- Detailed failure reporting

Batch generation is used to evaluate larger educational datasets without stopping when individual generations fail.

---

# Evaluation & Benchmarking

The feature integrates with the shared evaluation framework.

Implemented metrics include:

- Grounded Question Percentage
- Validation Pass Rate
- Reference Verification Rate
- Answer Correctness Sampling
- Quality Metrics

The benchmark implementation remains fully compatible with the existing Mentor and Concept evaluation pipelines.

---

# User Interface

The Streamlit interface provides:

- Mode selection
- Question type selection
- Difficulty selection
- Number of questions
- Generated question preview
- Correct answer
- Rationale
- Supporting citations
- Validation warnings
- Review status

Every generated output is displayed as:

```
⚠ Requires Human Review
Status: PENDING
```

The UI communicates exclusively through **QuestionBankService**, maintaining clean separation between presentation and generation logic.

---

# Testing

The implementation includes comprehensive automated tests covering:

- Question generation
- Test Help generation
- Prompt loading
- Reviewable outputs
- Validation rules
- Support validation
- Reference verification
- Batch generation
- Benchmark evaluation
- Review lifecycle
- UI integration

All offline tests pass successfully.

---

# Design Decisions

Several architectural decisions were intentionally made:

- Reused the existing Week 3 architecture instead of introducing parallel implementations.
- Kept Question Bank and Test Help as independent agents sharing common infrastructure.
- Integrated exclusively through shared contracts.
- Preserved the shared review lifecycle.
- Avoided bypassing validation or review gates.
- Maintained backward compatibility with Mentor and Concept agents.

---

# Summary

The Week 4 implementation delivers a complete Question Bank & Test Help feature built on the project's shared architecture.

The feature provides grounded educational question generation, deterministic validation, reviewable outputs, benchmark integration, and comprehensive testing while preserving compatibility with the existing Mentor and Concept pipelines.