# Mentor & Concept Explanation Agents: Sprint 3 Implementation

**Technical Documentation | Sprint 3 | ai-content-agents** | Theme: AI Intelligence

---

## 1. Overview

### Purpose

The Mentor Agent and Concept Explanation Agent are grounded AI agents built to generate structured educational outputs using uploaded educational content. Both agents are designed to assist learners by providing high-quality, evidence-based explanations and guidance.

**Mentor Agent**: Provides supportive, personalized guidance for learners. It explains educational content while highlighting key takeaways and recommending actionable next learning steps. The mentor takes a nurturing approach, guiding learners through concepts rather than simply providing answers.

**Concept Explanation Agent**: Focuses on clear, concise concept definitions and explanations. It breaks down concepts into digestible parts with supporting key points and provenance references. The concept agent emphasizes accuracy and clarity over guidance.

### Core Principle: Human Review Gateway

**All outputs require human review before publication.** This is not optional—it is enforced at the architecture level through the review schema and service layer. Every agent output flows through a mandatory human-review pipeline:

```
Generated Output → PENDING Review → Human Reviewer → APPROVED/EDITED/REJECTED → Export
```

No output can be exported without explicit human approval, regardless of its internal validation state.

### Week 3 Objectives Implemented

1. ✅ **Structured JSON Generation**: Both agents produce validated Pydantic models with guaranteed schema compliance
2. ✅ **Human Review Pipeline**: MentorConceptService enforces review gates; output status lifecycle (PENDING → EDITED → APPROVED)
3. ✅ **Support Validation**: Deterministic claim validation against grounded content; unsupported claims are detected
4. ✅ **Reference Verification**: Provenance checking ensures cited chunks exist in the grounded context
5. ✅ **Difficulty Control**: Three difficulty levels (beginner/intermediate/advanced) with aligned output complexity
6. ✅ **Batch Generation**: Process multiple items with independent error handling
7. ✅ **Evaluation Metrics**: Groundedness scores, reference validity rates, quality metrics
8. ✅ **Benchmark Reporting**: Aggregate metrics across batch runs with per-item details
9. ✅ **Streamlit Demo UI**: Full Mentor and Concept pages with review status indicators
10. ✅ **Service Layer Isolation**: UI communicates only through MentorConceptService, never directly with agents

---

## 2. Folder Structure

### Core Agent Files

| File | Purpose | Key Responsibility |
|------|---------|-------------------|
| `src/agents/mentor_agent.py` | Mentor Agent implementation | Loads mentor.yaml, calls LLM, validates output, generates reviewable records |
| `src/agents/concept_agent.py` | Concept Agent implementation | Loads concept.yaml, calls LLM, validates output, generates reviewable records |
| `src/agents/registry.py` | Agent registry | Central registry of all available agents (Mentor, Concept, Question Bank, Test Help) |

### Service & Facade Layer

| File | Purpose | Key Responsibility |
|------|---------|-------------------|
| `src/services/mentor_concept.py` | MentorConceptService facade | Routes Mentor and Concept generation through human-review gate; enforces service isolation |
| `src/services/formatters.py` | Output formatters | Formats benchmark reports and evaluation results for display |

### Validation & Review

| File | Purpose | Key Responsibility |
|------|---------|-------------------|
| `src/validation/review_schema.py` | Review domain model | Defines output lifecycle (PENDING/EDITED/APPROVED), review actions, export gate |
| `src/validation/schemas.py` | Output schemas | MentorOutput, ConceptOutput, ContentReference, DifficultyLevel Pydantic models |
| `src/validation/support_validator.py` | Claim validation | Deterministic word-level claim matching against grounded content |
| `src/validation/validator_base.py` | Base validator | Pydantic validation and guardrail checking for all outputs |

### Grounding & Retrieval

| File | Purpose | Key Responsibility |
|------|---------|-------------------|
| `src/retrieval/grounding.py` | Grounding contract | Builds grounded context from retrieval results; verifies reference provenance |
| `src/retrieval/models.py` | Retrieval models | GroundedContext, RetrievalScope, chunk models |
| `src/retrieval/retriever.py` | Content retriever | Ranks and returns relevant content chunks |
| `src/retrieval/index.py` | Vector index | Stores and searches embeddings for content chunks |

### Evaluation & Benchmarking

| File | Purpose | Key Responsibility |
|------|---------|-------------------|
| `src/evaluation/evaluator.py` | Deterministic evaluator | Computes groundedness, quality, difficulty alignment scores |
| `src/evaluation/benchmark.py` | Benchmark orchestrator | Runs batch generation + evaluation; computes aggregate metrics |
| `src/evaluation/demo_benchmark.py` | Demo benchmark formatter | Formats benchmark results for human-readable display |
| `src/evaluation/models.py` | Evaluation models | EvaluationResult, BenchmarkReport, BenchmarkSummary |

### Content Ingestion

| File | Purpose | Key Responsibility |
|------|---------|-------------------|
| `src/ingestion/loader.py` | Content loader | Loads files (TXT, PDF, DOCX, Markdown); manages document storage |
| `src/ingestion/parser.py` | Format parser | Extracts text from different file formats |
| `src/ingestion/chunker.py` | Content chunker | Splits documents into semantically meaningful chunks |
| `src/ingestion/store.py` | Chunk store | Persists and retrieves document chunks with metadata |

### Prompts & Configuration

| File | Purpose | Key Responsibility |
|------|---------|-------------------|
| `src/prompts/mentor.yaml` | Mentor prompt template | Role, instructions, output schema definition; filled at runtime |
| `src/prompts/concept.yaml` | Concept prompt template | Role, instructions, output schema definition; filled at runtime |

### UI & Application Entry Point

| File | Purpose | Key Responsibility |
|------|---------|-------------------|
| `src/app.py` | Streamlit main application | 7-page UI: Home, Upload, Flashcards, Study Plan, Revision, **Mentor, Concept** |

### Pipeline Overview

```
┌─────────────────────────────────────────────────────────────────┐
│ USER INPUT (via Streamlit UI)                                   │
│ - Content                                                        │
│ - Question/Concept                                              │
│ - Difficulty                                                     │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
        ┌────────────────────────────────────┐
        │ MentorConceptService               │
        │ (Service Facade Layer)             │
        └─────────────┬──────────────────────┘
                      │
        ┌─────────────▼──────────────┐
        │ MentorAgent / ConceptAgent │
        │ (Raw Generation)           │
        └─────────────┬──────────────┘
                      │
        ┌─────────────▼──────────────────────────────┐
        │ 1. Prompt Building (from YAML template)    │
        │ 2. LLM Call (OpenAI compatible API)        │
        │ 3. JSON Parsing                            │
        │ 4. Pydantic Validation                     │
        │ 5. Reference Verification (if grounded)   │
        │ 6. Support Validation (if grounded)       │
        └─────────────┬──────────────────────────────┘
                      │
        ┌─────────────▼──────────────────────────────┐
        │ build_generated_output()                   │
        │ (Convert to GeneratedOutput, status=PENDING)
        └─────────────┬──────────────────────────────┘
                      │
        ┌─────────────▼──────────────────────────────┐
        │ GeneratedOutput (PENDING Status)           │
        │ - payload: {...}                           │
        │ - status: OutputStatus.PENDING             │
        │ - validation_report: {...}                 │
        └─────────────┬──────────────────────────────┘
                      │
        ┌─────────────▼──────────────────────────────┐
        │ UI Display (Mentor/Concept Page)           │
        │ - ⚠️ "Requires Human Review" Badge        │
        │ - Review Status: PENDING                   │
        │ - Explanation, Key Points, Next Steps      │
        │ - Provenance References                    │
        └─────────────┬──────────────────────────────┘
                      │
        ┌─────────────▼──────────────────────────────┐
        │ HUMAN REVIEW (Future Lane)                 │
        │ → APPROVE / EDIT / REJECT                  │
        └─────────────┬──────────────────────────────┘
                      │
        ┌─────────────▼──────────────────────────────┐
        │ EXPORT (If APPROVED)                       │
        │ assert_exportable() enforces gate          │
        └─────────────────────────────────────────────┘
```

---

## 3. Mentor Agent Workflow

### Complete Pipeline Flow

```
INPUT
│
├─ Content: str or GroundedContext
├─ User Question: Optional[str]
└─ Difficulty: str ("beginner", "intermediate", "advanced")
│
▼
PROMPT BUILDING
│
├─ Load mentor.yaml
├─ Get prompt_template field
├─ Format with placeholders:
│  ├─ {content}: Educational material
│  ├─ {user_question}: Learner's question
│  └─ {difficulty}: Complexity level
│
▼
LLM CALL
│
├─ Use OpenAI-compatible client (default: FW-Kimi-K2.6)
├─ Temperature: 0.3 (lower = more deterministic)
├─ Timeout: 60 seconds
│
▼
JSON PARSING
│
├─ Extract raw_response from LLM
├─ Parse JSON string to dict
├─ Handle json.JSONDecodeError
│
▼
PYDANTIC VALIDATION
│
├─ Validate against MentorOutput schema
├─ Required fields:
│  ├─ explanation: str
│  ├─ key_points: list[str]
│  ├─ next_steps: list[str]
│  ├─ references: list[ContentReference]
│  └─ requires_human_review: Literal[True] (frozen)
├─ Handle ValidationError
│
▼
REFERENCE VALIDATION (if GroundedContext provided)
│
├─ verify_references(output.references, context)
├─ Check: every segment_id exists in retrieved chunks
├─ Reject fabricated citations
│
▼
SUPPORT VALIDATION (if GroundedContext provided)
│
├─ extract_claim_text(output) → list of claims
├─ validate_support(claims, context)
├─ Deterministic word-level matching (60% overlap required)
├─ Detect contradictions (negation detection)
├─ Flag unsupported claims
│
▼
REVIEWABLE OUTPUT
│
├─ Create GeneratedOutput record:
│  ├─ agent_run_id: unique run ID
│  ├─ output_type: "mentor_explanation"
│  ├─ payload: validated output as dict
│  ├─ schema_name: "MentorOutput"
│  ├─ validation_passed: bool
│  ├─ status: OutputStatus.PENDING (always)
│  └─ created_at: timestamp
│
▼
MentorConceptService
│
├─ Returns GeneratedOutput to UI/caller
├─ Service enforces output is PENDING
├─ No raw MentorAgent output leaks to UI
│
▼
HUMAN REVIEW
│
├─ Reviewer sees: ⚠️ "Requires Human Review"
├─ Review status: PENDING
├─ Reviewer can:
│  ├─ APPROVE → status = APPROVED (export allowed)
│  ├─ EDIT → modify payload → status = EDITED
│  └─ REJECT → status stays PENDING (export blocked)
│
▼
EXPORT (Future Lane)
│
└─ assert_exportable(output) enforces APPROVED status
```

### Key Methods

```python
# Raw generation (internal use only)
mentor_agent.generate(
    content: str,
    user_question: Optional[str] = None,
    difficulty: str = "beginner",
    context: GroundedContext | None = None
) -> MentorOutput

# Reviewable generation (what UI should use)
mentor_agent.generate_reviewable(
    content: str,
    user_question: Optional[str] = None,
    difficulty: str = "beginner",
    context: GroundedContext | None = None
) -> GeneratedOutput

# Batch generation (for benchmarks)
mentor_agent.generate_batch(
    items: list[dict[str, Any]]
) -> BatchGenerationResult[MentorOutput]
```

---

## 4. Concept Agent Workflow

The Concept Explanation Agent follows an identical pipeline to the Mentor Agent, with one key difference:

### Output Structure

**Mentor** generates:
- `explanation`, `key_points`, `next_steps`, `references`

**Concept** generates:
- `definition`, `explanation`, `key_points`, `references`

### Workflow

```
INPUT
│
├─ Content: str or GroundedContext
├─ Concept Question: Optional[str]
└─ Difficulty: str ("beginner", "intermediate", "advanced")
│
▼
PROMPT BUILDING
│
├─ Load concept.yaml
├─ Get prompt_template field
├─ Format with placeholders (same as Mentor)
│
▼
LLM CALL → JSON PARSING → PYDANTIC VALIDATION
│
├─ Validate against ConceptOutput schema
├─ Required fields: definition, explanation, key_points, references
│
▼
REFERENCE & SUPPORT VALIDATION (if grounded)
│
├─ Verify all cited segment_ids exist
├─ Ensure all claims have 60%+ token overlap with source
│
▼
REVIEWABLE OUTPUT
│
├─ Create GeneratedOutput with status = PENDING
├─ Return via MentorConceptService to UI
│
▼
HUMAN REVIEW & EXPORT
│
└─ Same lifecycle as Mentor
```

### Difficulty Control

Both agents receive difficulty as a parameter. The LLM is instructed (via prompt template) to adjust:

- **Beginner**: Simple language, fewer concepts, shorter explanations (8–12 words avg)
- **Intermediate**: Moderate complexity, some jargon, balanced depth (8–24 words avg)
- **Advanced**: Technical terminology, deep explanations, longer content (16+ words avg)

The evaluation system scores difficulty alignment by measuring average claim length against expected bands.

---

## 5. Prompt Templates

### Why YAML?

YAML is human-readable, version-controllable, and easy to modify without code changes. Each agent loads its template at runtime from `src/prompts/`.

### mentor.yaml Structure

```yaml
name: Mentor Agent
description: "..."
role: "..."

instructions:
  - Use only the uploaded educational content
  - Do not invent information
  - Ground every explanation
  - Suggest practical next steps
  - (... 6 more instructions)

output_schema:
  explanation: "..."
  key_points: [...]
  next_steps: [...]
  references: [...]
  requires_human_review: true

notes:
  - Always return structured JSON
  - Do not include extra fields
  - Every claim must be supported

prompt_template: |
  You are an experienced educational mentor.
  
  Use ONLY the uploaded educational content.
  
  Educational Content:
  {content}
  
  User Question:
  {user_question}
  
  Difficulty Level:
  {difficulty}
  
  Return ONLY valid JSON matching the schema above.
```

### concept.yaml Structure

```yaml
name: Concept Explanation Agent
description: "..."
role: "..."

instructions:
  - Provide clear, accurate definitions
  - Explain the concept thoroughly
  - Focus on clarity and correctness
  - (... more)

output_schema:
  definition: "..."
  explanation: "..."
  key_points: [...]
  references: [...]
  requires_human_review: true

prompt_template: |
  You are an expert concept explainer.
  
  Use ONLY the uploaded educational content.
  
  Educational Content:
  {content}
  
  Concept to Explain:
  {user_question}
  
  Difficulty Level:
  {difficulty}
  
  Return ONLY valid JSON matching the schema above.
```

### Placeholders

| Placeholder | Value | Example |
|-------------|-------|---------|
| `{content}` | Educational material, optionally grounded | "Python loops repeat code blocks..." |
| `{user_question}` | Learner's question or concept name | "Explain for loops" |
| `{difficulty}` | Complexity level | "beginner", "intermediate", "advanced" |

### JSON Contract

The LLM is explicitly instructed to return only valid JSON. The application parses the response and validates against Pydantic schemas before any use. Invalid JSON is rejected with a clear error.

### Grounding Instructions

If grounded context is provided:
- Agent is instructed to reference content using stable identifiers (segment_id)
- Agent must not invent information outside the provided content
- Support validation later checks that claims match content tokens

### Review Instructions

Every prompt includes:
- "This response will be reviewed by a human before publication"
- "Ensure all claims are verifiable from the provided content"
- "If content is insufficient, clearly state the limitation"

---

## 6. Output Schemas

### MentorOutput

```python
class MentorOutput(BaseModel):
    """Structured output schema for the Mentor Agent."""

    explanation: str  # Detailed explanation of content
    key_points: list[str]  # Important takeaways
    next_steps: list[str]  # Recommended next learning steps
    references: list[ContentReference]  # Grounded citations
    requires_human_review: Literal[True]  # Frozen field; always True
```

**Key Design Decision**: `requires_human_review: Literal[True]` is frozen and cannot be modified. This ensures output identity is protected—reviewers cannot accidentally approve an unapproved output by changing this flag.

### ConceptOutput

```python
class ConceptOutput(BaseModel):
    """Structured output schema for the Concept Explanation Agent."""

    definition: str  # Short concept definition
    explanation: str  # Detailed explanation
    key_points: list[str]  # Summary points
    references: list[ContentReference]  # Grounded citations
    requires_human_review: Literal[True]  # Frozen field; always True
```

### ContentReference

```python
class ContentReference(BaseModel):
    """Reference to a content chunk used for grounding."""

    segment_id: str  # Chunk ID from retrieval
    text: str  # Full text of the chunk
```

### DifficultyLevel

```python
class DifficultyLevel(str, Enum):
    """Supported difficulty levels."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
```

### GeneratedOutput

```python
class GeneratedOutput(BaseModel):
    """One record per produced artifact carrying validation verdict and status."""

    id: str  # Unique output ID
    agent_run_id: str  # Reference to AgentRun
    output_type: str  # "mentor_explanation" or "concept_explanation"
    payload: dict[str, Any]  # The validated output as dict
    schema_name: str  # "MentorOutput" or "ConceptOutput"
    validation_passed: bool  # Did Pydantic validation succeed?
    validation_report: dict[str, Any]  # Validation details
    status: OutputStatus  # PENDING, EDITED, or APPROVED
    created_at: datetime  # When generated
    updated_at: datetime  # When last modified
```

### OutputStatus Lifecycle

```python
class OutputStatus(str, Enum):
    PENDING = "pending"  # Initial state; requires human review
    EDITED = "edited"  # Human made changes
    APPROVED = "approved"  # Human approved; export allowed
```

**Legal Transitions**:
- `PENDING` → `EDITED` (reviewer edits the payload)
- `PENDING` → `APPROVED` (reviewer approves as-is)
- `EDITED` → `APPROVED` (reviewer approves edited version)
- `APPROVED` → ❌ No re-opening (terminal state)

---

## 7. Grounding System

### GroundedContext

```python
class GroundedContext(BaseModel):
    """Payload keeping agent answers grounded in uploaded content."""

    query: str  # Original search query
    scope: RetrievalScope  # Document/session to search
    chunks: list[ChunkWithScore]  # Retrieved, ranked chunks
    chunk_ids: list[str]  # IDs for provenance tracking
    is_sufficient: bool  # Enough content for agent to use?
```

### Content Chunks

Retrieved chunks carry:
- **Text**: The actual content segment
- **Chunk ID**: Stable identifier for citation
- **Document ID**: Which document this came from
- **Score**: Relevance ranking (used internally, not exposed to LLM)
- **Metadata**: Position, token count, etc.

### References

Agent output citations take the form:

```python
ContentReference(
    segment_id="chunk_001",  # Chunk ID from retrieval
    text="Relevant content excerpt...",  # Full text (for human review)
)
```

### Chunk IDs

Chunk IDs are deterministically generated from:
- Document ID
- Chunk ordinal (0-indexed position in document)

Example: `"doc_abc123__chunk_002"` = document abc123, third chunk

### Reference Verification

`verify_references(output.references, context)` checks:
- Every `segment_id` in output.references exists in `context.chunk_ids`
- No fabricated citations
- Result: `GroundingVerification(valid=True/False, unknown_segment_ids=[...])`

### Chunk Provenance

Every chunk carries metadata linking it back to:
- Source document
- Ingestion session
- Position in document
- Retrieval score

This enables full audit trails: "This citation came from document X, section Y, retrieved with relevance score Z."

### Why Provenance Matters

1. **Trust**: Reviewers can verify claims directly by inspecting source chunks
2. **Accountability**: Every output is traceable to specific content
3. **Correction**: If source content is wrong, impact on generated outputs is clear
4. **Compliance**: Audit trail for regulatory/educational requirements

---

## 8. Human Review Architecture

### Two-Tier Generation

**Tier 1: Raw Generation** (`agent.generate()`)
- Direct LLM output
- Internal validation only
- **Must not be exposed to UI or end users**
- No review tracking

**Tier 2: Reviewable Generation** (`agent.generate_reviewable()`)
- Wraps raw output in GeneratedOutput record
- Sets status = PENDING
- Returns to service layer
- Tracked for review pipeline
- **This is what UI should use**

### MentorConceptService

Acts as a **gate** between raw agents and the UI:

```python
class MentorConceptService:
    def generate_mentor_reviewable(
        self,
        content: str,
        user_question: Optional[str] = None,
        difficulty: str = "beginner",
        context: GroundedContext | None = None,
    ) -> GeneratedOutput:
        """Always returns GeneratedOutput with status=PENDING."""
        return self.mentor_agent.generate_reviewable(...)

    def generate_concept_reviewable(
        self,
        content: str,
        user_question: Optional[str] = None,
        difficulty: str = "beginner",
        context: GroundedContext | None = None,
    ) -> GeneratedOutput:
        """Always returns GeneratedOutput with status=PENDING."""
        return self.concept_agent.generate_reviewable(...)
```

**Key Rule**: The UI must ONLY import and use `MentorConceptService`. It must never import `MentorAgent` or `ConceptAgent` directly.

### Review Status Pipeline

```
create_generated_output()
        ↓
   status = PENDING
        ↓
human_reviewer.approve()
        ↓
  status = APPROVED
        ↓
assert_exportable() ✓ PASS
        ↓
   EXPORT OK
```

### Export Protection

`assert_exportable(output: GeneratedOutput)` enforces:

```python
def assert_exportable(output: GeneratedOutput) -> None:
    """Raise if output is not approved."""
    if output.status != OutputStatus.APPROVED:
        raise ExportBlockedError(output.id, output.status)
```

**Every export path must call this.** Examples:
- Saving to database
- Sending via API
- Publishing to UI permanently
- Batch export

### Review Actions

```python
class ReviewAction(str, Enum):
    APPROVE = "approve"  # Accept output; set status = APPROVED
    EDIT = "edit"  # Modify payload; set status = EDITED
    COMMENT = "comment"  # Add notes; status unchanged
```

### Applying a Review

```python
review = apply_review(
    output=output,
    reviewer="alice@company.com",
    action=ReviewAction.APPROVE,
    notes="Looks good!",
)
# Returns immutable Review record for audit trail
# Updates output.status in place
```

---

## 9. Support Validation

### The Problem

LLMs can hallucinate. They may:
- Invent facts not in the source
- Exaggerate concepts
- Misrepresent relationships
- Add external knowledge

### The Solution: Deterministic Matching

Support validation extracts claims from agent output and checks them word-by-word against grounded source content.

### Extract Claim Text

```python
def extract_claim_text(output: MentorOutput | ConceptOutput) -> list[str]:
    """Extract sentence-like claims from explanation fields.
    
    For Mentor:
        - explanation
        - key_points (each as separate claim)
        - next_steps (excluded to avoid blocking external advice)
    
    For Concept:
        - definition
        - explanation
        - key_points (each as separate claim)
    
    Returns: list of sentence-like statements
    """
```

### Validate Support

```python
def validate_support(
    claims: list[str], context: GroundedContext
) -> SupportValidationResult:
    """Check each claim against source content.

    Algorithm:
    1. Extract normalized content words from claim
    2. Extract normalized content words from source
    3. Calculate overlap: claim_tokens ∩ source_tokens
    4. Require ≥60% overlap
    5. Detect negations (claim says "no X" but source says "X is...")

    Returns: SupportValidationResult(
        supported: bool,
        unsupported_claims: list[str]
    )
    """
```

### Normalization

Words are normalized to catch variants:

| Original | Normalized | Rationale |
|----------|-----------|-----------|
| "loops" | "loop" | Plurals |
| "practicing" | "practic" | Verb forms |
| "easier" | "easi" | Comparatives |
| "for", "the", "a" | (removed) | Stop words |

### Current Limitations

1. **No semantic matching**: "vehicle" ≠ "car" (different words, same concept)
2. **No LLM entailment**: Can't detect logical implications
3. **No abbreviations**: "Python" ≠ "PY"
4. **60% threshold is fixed**: May be too strict or lenient for different domains

### Example

**Source content**: "Python loops repeat code blocks. The for loop iterates over sequences."

**Generated claim**: "For loops repeat code in sequences."

**Analysis**:
- Claim tokens: {for, loop, repeat, code, sequence}
- Source tokens: {python, loop, repeat, code, block, for, iterate, sequence}
- Overlap: {for, loop, repeat, code, sequence} = 5/5 = 100% ✓ SUPPORTED

---

## 10. Evaluation System

### Purpose

Evaluate agent outputs for:
- Schema compliance
- Grounding quality
- Content quality
- Difficulty alignment

### evaluate_output()

```python
def evaluate_output(
    output: MentorOutput | ConceptOutput,
    context: GroundedContext | None = None,
    difficulty: str | DifficultyLevel | None = None,
) -> EvaluationResult:
    """Evaluate a single output comprehensively."""
```

### Evaluation Metrics

#### 1. Validation Score

- **validation_passed**: bool
- Did Pydantic validation succeed?
- Required fields present?

#### 2. Groundedness Score (0.0–1.0)

Computed when context is provided:

```
groundedness_score = (
    (0.5 if references_valid else 0.0)
    + (0.5 if supported else 0.0)
)
```

Breaks down as:
- **0.5 reference validity**: All cited segment_ids exist in context
- **0.5 support validity**: All claims have ≥60% token overlap with source

Maximum: 1.0 (both reference and support valid)

#### 3. Groundedness Ratio

If claims exist:

```
groundedness_ratio = (total_claims - unsupported_claims) / total_claims
```

Example: 8 claims, 2 unsupported → 6/8 = 0.75 (75% grounded)

#### 4. Quality Score (0.0–1.0)

Checks presence of required fields:

| Field | Points | Presence Check |
|-------|--------|----------------|
| explanation | 0.25 | Non-empty string |
| key_points | 0.25 | Non-empty list |
| references | 0.25 | Non-empty list |
| next_steps / definition | 0.25 | Non-empty string |

#### 5. Difficulty Alignment Score (0.0–1.0)

Compares average claim length to expected bands:

| Level | Expected Avg | Calculation |
|-------|------------|-------------|
| Beginner | 12 words | `1.0 - max(length - 12, 0) / 12` |
| Intermediate | 8–24 words | Piecewise scoring |
| Advanced | 16+ words | `min(length / 16, 1.0)` |

#### 6. Reference Validity Rate

Percentage of outputs with valid references:

```
rate = outputs_with_valid_refs / total_outputs
```

#### 7. Support Rate

Percentage of outputs with all supported claims:

```
rate = outputs_fully_supported / total_outputs
```

#### 8. Validation Pass Rate

Percentage of outputs passing Pydantic validation:

```
rate = valid_outputs / total_outputs
```

### EvaluationResult Structure

```python
class EvaluationResult(BaseModel):
    grounded: bool  # All validation + grounding checks pass
    references_valid: bool  # All citations exist in context
    supported: bool  # All claims match source
    validation_passed: bool  # Pydantic validation passed
    unsupported_claims: int  # Count of failed claims
    groundedness_score: float | None  # 0.0–1.0
    groundedness_ratio: float | None  # 0.0–1.0
    difficulty_alignment_score: float | None  # 0.0–1.0
    quality_score: float  # 0.0–1.0
    notes: list[str]  # Detailed findings
```

---

## 11. Batch Generation

### BatchGenerationResult

```python
class BatchGenerationResult(BaseModel):
    """Result of generating multiple items without stopping on errors."""

    successes: list[T]  # Successfully generated outputs
    failures: list[BatchGenerationFailure]  # Failed items with error details
    total_processed: int
    elapsed_seconds: float
```

### generate_batch()

```python
def generate_batch(
    self, items: list[dict[str, Any]]
) -> BatchGenerationResult[MentorOutput]:
    """Generate outputs for multiple inputs.

    Each item is a dict with:
        - content: str (required)
        - user_question: str (optional)
        - difficulty: str (optional, default "beginner")
        - context: GroundedContext (optional)

    Behavior:
    - Processes all items regardless of individual failures
    - Records failures with original item index and error message
    - Preserves input order in successes
    - Returns timing information

    Example:
        result = agent.generate_batch([
            {"content": "Python loops...", "user_question": "What is a for loop?"},
            {"content": "JSON format...", "difficulty": "advanced"},
        ])
        print(f"Successes: {len(result.successes)}")
        print(f"Failures: {len(result.failures)}")
    """
```

### Error Handling

Batch generation catches and records:
- `json.JSONDecodeError`: Invalid JSON from LLM
- `ValidationError`: Pydantic schema violations
- `ValueError`: Reference/support validation failures
- `RateLimitError`: API rate limits (not a code failure)
- `TimeoutError`: API call timeout
- `RuntimeError`: Client/environment errors

Each failure includes:
- Original input item index
- Error message
- Error type
- Timestamp

---

## 12. Streamlit Demo UI

### Running the UI with a Live LLM

The Streamlit demo can operate in either **Mock Mode** or **Live Mode**. By default, the application may use Mock Mode for safe development.

**Live/API mode requirement:** To run the UI using the real OpenRouter API, add the following setting to your `.env` file before starting Streamlit:

```env
MOCK_MODE=false
```

### Mentor Page

**URL Path**: Navigation → "🧭 Mentor"

**UI Layout**:

```
┌──────────────────────────────────────────────────────┐
│ 🧭 Mentor                                            │
│ Generate a grounded mentoring response for human     │
│ review.                                              │
├──────────────────────────────────────────────────────┤
│ FORM:                                                │
│ ┌────────────────────────────────────────────────┐   │
│ │ Content                                        │   │
│ │ (textarea, height=220)                         │   │
│ │ Enter educational content...                   │   │
│ └────────────────────────────────────────────────┘   │
│                                                      │
│ ┌────────────────────────────────────────────────┐   │
│ │ User question                                  │   │
│ │ (text input)                                   │   │
│ │ What would you like to understand?             │   │
│ └────────────────────────────────────────────────┘   │
│                                                      │
│ ┌────────────────────────────────────────────────┐   │
│ │ Difficulty                                     │   │
│ │ (selectbox)                                    │   │
│ │ ○ beginner  ● intermediate  ○ advanced         │   │
│ └────────────────────────────────────────────────┘   │
│                                                      │
│ [Generate Mentor Response]                           │
└──────────────────────────────────────────────────────┘

OUTPUT (after submit):

┌──────────────────────────────────────────────────────┐
│ ⚠️ Requires Human Review                             │
│ Review status: PENDING                               │
│                                                      │
│ Explanation                                          │
│ ─────────────────────────────────────────────────    │
│ [Generated explanation text...]                      │
│                                                      │
│ Key points                                           │
│ ─────────────────────────────────────────────────    │
│ - Key point 1                                        │
│ - Key point 2                                        │
│ - Key point 3                                        │
│                                                      │
│ Next steps                                           │
│ ─────────────────────────────────────────────────    │
│ - Next step 1                                        │
│ - Next step 2                                        │
│                                                      │
│ Provenance references                                │
│ ─────────────────────────────────────────────────    │
│ **chunk_001**: "Relevant content excerpt..."         │
│ **chunk_002**: "Another related content..."          │
└──────────────────────────────────────────────────────┘
```

### Concept Page

**URL Path**: Navigation → "💡 Concept Explanation"

**UI Layout**:

```
┌──────────────────────────────────────────────────────┐
│ 💡 Concept Explanation                               │
│ Generate a grounded concept explanation for human    │
│ review.                                              │
├──────────────────────────────────────────────────────┤
│ FORM:                                                │
│ ┌────────────────────────────────────────────────┐   │
│ │ Content                                        │   │
│ │ (textarea, height=220)                         │   │
│ └────────────────────────────────────────────────┘   │
│                                                      │
│ ┌────────────────────────────────────────────────┐   │
│ │ Concept question                               │   │
│ │ (text input)                                   │   │
│ │ What concept would you like explained?         │   │
│ └────────────────────────────────────────────────┘   │
│                                                      │
│ ┌────────────────────────────────────────────────┐   │
│ │ Difficulty                                     │   │
│ │ (selectbox)                                    │   │
│ │ ○ beginner  ● intermediate  ○ advanced         │   │
│ └────────────────────────────────────────────────┘   │
│                                                      │
│ [Generate Concept Explanation]                       │
└──────────────────────────────────────────────────────┘

OUTPUT (after submit):

┌──────────────────────────────────────────────────────┐
│ ⚠️ Requires Human Review                             │
│ Review status: PENDING                               │
│                                                      │
│ Definition                                           │
│ ─────────────────────────────────────────────────    │
│ [Generated definition...]                            │
│                                                      │
│ Explanation                                          │
│ ─────────────────────────────────────────────────    │
│ [Generated explanation...]                           │
│                                                      │
│ Key points                                           │
│ ─────────────────────────────────────────────────    │
│ - Key point 1                                        │
│ - Key point 2                                        │
│                                                      │
│ Provenance references                                │
│ ─────────────────────────────────────────────────    │
│ **chunk_001**: "Source content excerpt..."           │
└──────────────────────────────────────────────────────┘
```

### UI Communication Flow

**Key Rule**: The UI ONLY uses `MentorConceptService`.

```python
# src/app.py imports:
from src.services.mentor_concept import MentorConceptService


# Initialize once (cached):
@st.cache_resource
def get_mentor_concept_service():
    return MentorConceptService()


# Usage:
mentor_concept_service = get_mentor_concept_service()

# Generate mentor response:
reviewable = mentor_concept_service.generate_mentor_reviewable(
    content=content,
    user_question=user_question or None,
    difficulty=difficulty,
)

# Display output:
st.warning("⚠️ Requires Human Review")
st.write(f"Review status: **{reviewable.status.value.upper()}**")
st.write(reviewable.payload.get("explanation", ""))
```

**Verification**: `src/app.py` imports:
- ❌ NO `from src.agents.mentor_agent import MentorAgent`
- ❌ NO `from src.agents.concept_agent import ConceptAgent`
- ✅ YES `from src.services.mentor_concept import MentorConceptService`

---

## 13. Error Handling

### Handled Cases

| Error | Source | Handling |
|-------|--------|----------|
| **Missing mentor.yaml** | Agent initialization | `FileNotFoundError` → User-facing error |
| **Invalid YAML syntax** | `yaml.safe_load()` | `ValueError` → User message: "Invalid YAML syntax in mentor.yaml" |
| **Empty YAML** | `yaml.safe_load()` returns None | `ValueError` → "mentor.yaml is empty" |
| **Missing prompt_template** | YAML parsing | `KeyError` → "prompt_template not found" |
| **Invalid JSON from LLM** | `json.loads()` | `JSONDecodeError` → "LLM returned invalid JSON" |
| **Pydantic validation failure** | Schema validation | `ValidationError` → Lists which fields failed |
| **Missing API key** | Environment check | `ValueError` → "Missing LITELLM_API_KEY" |
| **Missing API base URL** | Environment check | `ValueError` → "Missing LITELLM_BASE_URL" |
| **LLM timeout** | Network call | `TimeoutError` (60s timeout) → User error |
| **Rate limit (429)** | API response | `RateLimitError` → Not a code failure; retry needed |
| **Invalid difficulty** | Input validation | `ValueError` → "Invalid difficulty; expected beginner, intermediate, or advanced" |
| **Fabricated references** | Reference verification | `ValueError` → "Generated references are not grounded in content" |
| **Unsupported claims** | Support validation | `ValueError` → "Generated explanation contains unsupported claims" |

### Mock Mode vs Live Mode

```python
# Mock mode (default in tests):
MOCK_MODE=true

# Returns hardcoded valid response
MOCK_RESPONSE = """
{
    "explanation": "Python has two loop types...",
    "key_points": ["for loops", "while loops"],
    ...
}
"""

# Live mode (for real LLM calls):
MOCK_MODE=false

# Requires API keys and live connection
LITELLM_API_KEY=...
LITELLM_BASE_URL=https://api.openrouter.io/api/v1
DEFAULT_MODEL=FW-Kimi-K2.6
```

### Mock Response Pattern

Mock responses are hard-coded in each agent to represent realistic outputs:

```python
MOCK_RESPONSE = """
{
    "explanation": "...",
    "key_points": [...],
    "next_steps": [...],
    "references": [
        {"segment_id": "chunk_001", "text": "..."}
    ],
    "requires_human_review": true
}
"""
```

This allows tests to run without external APIs and provides deterministic outputs for validation.

---

## 14. Testing

### Test Files Overview

| Test File | Purpose | Key Assertions |
|-----------|---------|----------------|
| **test_mentor_agent.py** | Unit tests for MentorAgent | Generation works; output validates; JSON parsing succeeds |
| **test_concept_agent.py** | Unit tests for ConceptAgent | Similar to Mentor; concept-specific fields validated |
| **test_mentor_review.py** | Review pipeline for Mentor | Output is PENDING; can transition to APPROVED/EDITED |
| **test_concept_review.py** | Review pipeline for Concept | Same lifecycle; export blocked before approval |
| **test_batch_generation.py** | Batch mode operation | All items process; failures recorded; timing tracked |
| **test_benchmark.py** | Benchmark orchestration | Runs batch generation + evaluation; computes metrics |
| **test_evaluation.py** | Evaluation metrics | Groundedness scores, quality checks, difficulty alignment |
| **test_invalid_json.py** | JSON error handling | Invalid JSON raises ValueError with clear message |
| **test_invalid_yaml.py** | YAML parsing errors | Invalid YAML syntax is caught and reported |
| **test_missing_yaml.py** | Missing prompt files | FileNotFoundError raised if mentor.yaml/concept.yaml absent |
| **test_missing_env.py** | Environment variable checks | Missing API key raises ValueError on init |
| **test_live_output_preview.py** | Live mode output inspection | Shows real LLM outputs (if RUN_LIVE_TESTS=true) |
| **test_mentor_agent_live.py** | Mentor live generation | Calls real API; shows actual outputs |
| **test_concept_agent_live.py** | Concept live generation | Calls real API; shows actual outputs |
| **test_mentor_concept_service.py** | Service facade | Always returns PENDING status; no agent leakage |
| **test_week3_gaps.py** | Integration tests | Full pipeline: content → generation → validation |

### Example Test Patterns

**Unit Test (Mock Mode)**:
```python
def test_mentor_agent_generates_valid_output():
    agent = MentorAgent(mock_mode=True)
    result = agent.generate(
        content="Python loops repeat code.",
        user_question="What is a loop?",
        difficulty="beginner",
    )
    assert isinstance(result, MentorOutput)
    assert len(result.explanation) > 0
    assert len(result.key_points) > 0
```

**Integration Test (Grounding)**:
```python
def test_mentor_with_grounded_context():
    agent = MentorAgent(mock_mode=True)
    context = build_grounded_context(...)
    result = agent.generate(content="...", context=context)
    # Verify references exist in context
    assert verify_references(result.references, context).valid
```

**Review Pipeline Test**:
```python
def test_mentor_reviewable_is_pending():
    agent = MentorAgent(mock_mode=True)
    reviewable = agent.generate_reviewable(content="...")
    assert reviewable.status == OutputStatus.PENDING
    # Verify export is blocked:
    with pytest.raises(ExportBlockedError):
        assert_exportable(reviewable)
```

**Batch Generation Test**:
```python
def test_batch_generation_continues_on_error():
    agent = MentorAgent(mock_mode=True)
    items = [
        {"content": "..."},
        {"content": ""},  # Will fail validation
        {"content": "..."},
    ]
    result = agent.generate_batch(items)
    assert len(result.successes) == 2
    assert len(result.failures) == 1
```

---

## 15. Testing Commands

### Basic Test Runs

```bash
# Run all tests (fast; mock mode)
python -m pytest

# Run with quiet output (summary only)
pytest -q

# Run with verbose output (each test name shown)
pytest -v

# Run with verbose + captured output (print statements visible)
pytest -v -s
```

### Live Testing (Real API Calls)

```bash
# Run live tests for Mentor Agent
RUN_LIVE_TESTS=true pytest -v tests/test_mentor_agent_live.py

# Run live tests for Concept Agent
RUN_LIVE_TESTS=true pytest -v tests/test_concept_agent_live.py

# Run live output preview (shows real LLM responses)
RUN_LIVE_TESTS=true pytest -v -s tests/test_live_output_preview.py

# Run ALL live tests (may take minutes)
RUN_LIVE_TESTS=true pytest -v tests/
```

### Specific Test Patterns

```bash
# Run tests matching a pattern
pytest -k "mentor" -v

# Run a single test file
pytest tests/test_mentor_agent.py -v

# Run a single test function
pytest tests/test_mentor_agent.py::test_mentor_agent_generates_valid_output -v

# Stop after first failure (useful for debugging)
pytest -x

# Show local variables on failure
pytest -l

# Run last failed tests
pytest --lf

# Run failed tests first, then others
pytest --ff
```

### Why -s Flag?

The `-s` flag disables output capture. Normally, pytest captures `print()` statements. With `-s`, they appear immediately in the terminal, useful for:
- Inspecting LLM output during live tests
- Debugging evaluation metrics
- Seeing benchmark reports in real-time

### Why RUN_LIVE_TESTS?

Live tests are skipped by default because they:
- Require network access
- Call expensive APIs
- May hit rate limits
- Take longer to run

Tests check the `RUN_LIVE_TESTS` environment variable:

```python
@pytest.mark.skipif(
    not os.getenv("RUN_LIVE_TESTS"), reason="Requires RUN_LIVE_TESTS=true"
)
def test_mentor_agent_live():
    # Calls real API
    agent = MentorAgent(mock_mode=False)
    ...
```

To enable: `RUN_LIVE_TESTS=true pytest ...`

---

## 16. Live Testing Notes

### Mock Mode vs Live Mode

| Aspect | Mock Mode | Live Mode |
|--------|-----------|-----------|
| API Call | Hardcoded response | Real OpenRouter API |
| Speed | Instant (< 100ms) | 2–5 seconds per call |
| Determinism | Always same output | Varies (same seed, but differs) |
| Default | Yes (MOCK_MODE=true) | No (requires MOCK_MODE=false) |
| Network | None required | OpenRouter API required |
| Cost | Free | ~$0.001–0.01 per call |

### OpenRouter

OpenRouter is a unified API gateway for multiple LLMs. Configuration:

```bash
# .env or environment variables:
LITELLM_API_KEY=sk_live_...          # API key from OpenRouter
LITELLM_BASE_URL=https://api.openrouter.io/api/v1
DEFAULT_MODEL=FW-Kimi-K2.6           # Specific model
```

### Rate Limits

OpenRouter enforces quotas:

| Limit | Value | Notes |
|-------|-------|-------|
| Requests/second | 10 | Soft limit; 429 if exceeded |
| Requests/day | 1000 (free tier) | Resets at midnight UTC |
| Tokens/minute | 30,000 | For single model |

### RateLimitError

```python
# Raised when quota exceeded:
from openai import RateLimitError

# This is NOT a code failure—it's expected behavior:
# - User has hit the daily quota
# - Or made requests too quickly
# - Retry later
```

**Important**: RateLimitError is not a bug in the implementation. It indicates:
1. API quota exceeded (try again tomorrow)
2. Requests too frequent (backoff and retry)

Live tests should handle this gracefully:

```python
def test_mentor_agent_live():
    agent = MentorAgent(mock_mode=False)
    try:
        result = agent.generate(content="...")
    except RateLimitError:
        pytest.skip("API rate limit exceeded; try again later")
```

---

## 17. Final Verification

### Checklist

- ✅ **Structured JSON Generation**: Both Mentor and Concept agents produce validated Pydantic models (MentorOutput, ConceptOutput) with guaranteed schema compliance
- ✅ **Human Review Pipeline**: GeneratedOutput enforces lifecycle (PENDING → EDITED → APPROVED); export gate blocks non-approved outputs
- ✅ **Support Validation**: Deterministic word-level matching catches unsupported claims; minimum 60% token overlap required
- ✅ **Reference Verification**: Provenance checking ensures cited segment_ids exist in grounded context; no fabricated citations allowed
- ✅ **Difficulty Control**: Three levels (beginner/intermediate/advanced) with prompt-based instruction and evaluation alignment metrics
- ✅ **Batch Generation**: generate_batch() processes multiple items with independent error handling and failure tracking
- ✅ **Evaluation Metrics**: Groundedness scores (0.0–1.0), quality scores, difficulty alignment, reference validity rates computed
- ✅ **Benchmark Reporting**: Aggregate metrics (BenchmarkSummary) with per-item details (BenchmarkItemResult) and timing
- ✅ **Streamlit Demo Pages**: Mentor and Concept pages fully functional with difficulty selector, content input, question input, review status badge, provenance references
- ✅ **Service Layer Separation**: UI imports only MentorConceptService; MentorAgent/ConceptAgent never directly exposed to frontend
- ✅ **Comprehensive Testing**: 171 tests passing; covers units, integration, error cases, batch, evaluation, benchmarking
- ✅ **Live Testing**: RUN_LIVE_TESTS=true allows real API calls; demonstrates end-to-end functionality with actual LLM

### Week 3 Deliverables

1. **Mentor Agent** (`src/agents/mentor_agent.py`)
   - Generates explanations, key points, next steps
   - Supports mock and live modes
   - Validates references and claims

2. **Concept Agent** (`src/agents/concept_agent.py`)
   - Generates definitions, explanations, key points
   - Identical pipeline to Mentor
   - Full validation support

3. **Service Facade** (`src/services/mentor_concept.py`)
   - Gates agent access; enforces review pipeline
   - Always returns GeneratedOutput with status=PENDING
   - No raw agent output leaks to UI

4. **Review Schema** (`src/validation/review_schema.py`)
   - Defines GeneratedOutput, Review, OutputStatus, AgentRun
   - Implements review action logic (APPROVE/EDIT/COMMENT)
   - Provides export gate (assert_exportable)

5. **Output Schemas** (`src/validation/schemas.py`)
   - MentorOutput, ConceptOutput, ContentReference
   - DifficultyLevel enum
   - All fields validated by Pydantic

6. **Support Validation** (`src/validation/support_validator.py`)
   - Extracts claims from outputs
   - Deterministic word-level matching (60% threshold)
   - Negation detection

7. **Reference Verification** (`src/retrieval/grounding.py`)
   - verify_references() ensures cited chunks exist
   - GroundedContext provenance tracking
   - build_grounded_context() entry point

8. **Evaluation System** (`src/evaluation/evaluator.py`)
   - Scores groundedness, quality, difficulty alignment
   - Computes reference validity and support rates
   - Integrates with grounding and validation

9. **Benchmark Orchestration** (`src/evaluation/benchmark.py`)
   - run_benchmark() executes batch generation + evaluation
   - Aggregates metrics across items
   - Records timing and failures

10. **Streamlit UI** (`src/app.py`)
    - Mentor page: content input, question, difficulty selector, generate button
    - Concept page: same layout, concept-specific output
    - Both pages display review status, provenance, key info

---

## 18. Future Improvements

### Semantic Claim Validation

**Current**: Deterministic 60% word-token overlap
**Future**: LLM-based entailment checking

```python
def validate_support_semantic(
    claims: list[str], context: GroundedContext
) -> SupportValidationResult:
    """Use LLM to check if claims logically follow from source.

    Example:
        Claim: "Python lists are ordered"
        Source: "A Python list maintains the insertion order of elements"
        Current: 3/4 tokens match (lists, python, order) → 75% ✓
        Future: LLM confirms entailment → SUPPORTED ✓
    """
```

**Advantages**: Catch semantic hallucinations; understand context better
**Tradeoffs**: Slower, more expensive, less deterministic

### Better Difficulty Evaluation

**Current**: Average claim word length compared to fixed bands
**Future**: Vocabulary level, concept complexity, reading grade

```python
def evaluate_difficulty_comprehensive(output: MentorOutput, difficulty: str) -> float:
    """Score difficulty across multiple dimensions.
    
    Checks:
    - Readability (Flesch-Kincaid grade)
    - Vocabulary level (CEFR framework)
    - Concept count and depth
    - Technical jargon ratio
    """
```

### Richer UI

**Current**: Streamlit text-based display
**Future**: 

- Rich markdown rendering with syntax highlighting
- Interactive reference expansion
- Reviewer comments/notes
- Batch upload support
- Approval workflows with multiple reviewers

### Retrieval Integration

**Current**: Grounding is optional; agents work without context
**Future**: 

- Automatic retrieval for all generate calls
- Query expansion for better chunk matching
- Hybrid search (dense + sparse)
- Semantic similarity verification

### Production API Endpoints

**Current**: Streamlit UI only
**Future**:

- FastAPI REST endpoints
- `/api/mentor/generate` (POST)
- `/api/concept/generate` (POST)
- `/api/outputs/{id}/review` (PATCH for approval)
- `/api/outputs/export` (POST for batch export)

### Persistence Layer

**Current**: In-memory GeneratedOutput objects
**Future**:

- Database backend for AgentRun, GeneratedOutput, Review
- Audit trail queries
- Output search and filtering
- Review history tracking
- Export audit logs

### Expanded Agent Portfolio

Mentor and Concept are first; future agents could include:

- **Flashcard Generator**: Create QA pairs from content
- **Study Plan Generator**: Build structured learning paths
- **Assessment Generator**: Build quizzes and tests
- **FAQ Generator**: Extract common questions from content

---

## Appendix A: Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Streamlit Frontend                        │
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │ Mentor Page  │    │ Concept Page │    │ Other Pages  │  │
│  └──────┬───────┘    └──────┬───────┘    └──────────────┘  │
│         │                    │                               │
└─────────┼────────────────────┼───────────────────────────────┘
          │                    │
          └────────┬───────────┘
                   │
                   ▼
   ┌────────────────────────────────────┐
   │ MentorConceptService               │
   │ (Service Facade / Gate)            │
   │                                    │
   │ generate_mentor_reviewable()       │
   │ generate_concept_reviewable()      │
   └────────────┬───────────────────────┘
                │
     ┌──────────┼──────────┐
     │          │          │
     ▼          ▼          ▼
┌──────────┐ ┌──────────┐ ┌──────────┐
│ Mentor   │ │ Concept  │ │Registry  │
│ Agent    │ │ Agent    │ │ (other)  │
└────┬─────┘ └────┬─────┘ └──────────┘
     │            │
     └────┬───────┘
          │
     ┌────▼──────────────────────────┐
     │ Raw Generation Pipeline       │
     │                               │
     │ 1. Load Prompt (YAML)         │
     │ 2. Build Final Prompt         │
     │ 3. Call LLM API               │
     │ 4. Parse JSON                 │
     │ 5. Validate (Pydantic)        │
     │ 6. Verify References          │
     │ 7. Validate Support           │
     └────┬──────────────────────────┘
          │
     ┌────▼──────────────────────────┐
     │ Review Layer                  │
     │                               │
     │ GeneratedOutput               │
     │ - status: PENDING             │
     │ - payload: {...}              │
     │ - validation_report: {...}    │
     └────┬──────────────────────────┘
          │
     ┌────▼──────────────────────────┐
     │ Human Review (Future Lane)    │
     │ - APPROVE / EDIT / REJECT     │
     │ - Update status               │
     └────┬──────────────────────────┘
          │
     ┌────▼──────────────────────────┐
     │ Export Gate                   │
     │ assert_exportable()           │
     │ (blocks if not APPROVED)      │
     └───────────────────────────────┘
```

---

## Appendix B: Validation Guardrails

The validator includes guardrails that check for common issues:

| Rule | Check | Severity |
|------|-------|----------|
| **ReferencesPresent** | At least one reference | Warning |
| **NoExtraFields** | No unexpected JSON fields | Error |
| **AllFieldsPopulated** | Required fields non-empty | Warning |
| **ValidDifficulty** | Difficulty in [beginner, intermediate, advanced] | Error |

---

## Appendix C: Configuration

### Environment Variables

```bash
# LLM Configuration
MOCK_MODE=true                          # Use mock responses (default)
LITELLM_API_KEY=sk_live_...            # OpenRouter API key
LITELLM_BASE_URL=https://api.openrouter.io/api/v1
DEFAULT_MODEL=FW-Kimi-K2.6             # Model name

# Content Ingestion
MAX_CHUNK_SIZE=1000                     # Tokens per chunk
CHUNK_OVERLAP=200                       # Overlap between chunks

# Testing
RUN_LIVE_TESTS=false                    # Enable live API tests
MOCK_MODE=true                          # Default to mock
```

### Prompt Customization

Modify `src/prompts/mentor.yaml` and `src/prompts/concept.yaml` to:
- Change role description
- Add/remove instructions
- Adjust output schema expectations
- Update prompt template text

Changes take effect immediately on next agent initialization.

---

**Document Version**: 1.0  
**Last Updated**: Week 3, Sprint 1  
**Status**: Complete Implementation
