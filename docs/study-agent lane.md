# Flashcards, Study Plan, Revision Tools & Content Ingestion

This repository contains both Sprint 1 (Flashcards, Study Plan & Revision) and Sprint 2 (Content Ingestion & Processing) implementations.

## Sprint 1: Flashcards, Study Plan & Revision
Includes Pydantic schemas, YAML prompts, a shared agent registry, and baseline generation code.

## Sprint 2: Content Ingestion & Processing
Adds content ingestion, multi‑format parsing, cleaning, chunking, deduplication, and Streamlit UI for uploading content.

## Project Structure
```
.
├── pyproject.toml
├── src/
│   ├── __init__.py
│   ├── study/
│   │   ├── flashcard_agent.py
│   │   ├── study_plan_agent.py
│   │   ├── revision_agent.py
│   │   ├── schemas.py
│   │   ├── ui.py
│   │   └── prompts/
│   │       ├── flashcards.yaml
│   │       ├── study_plan.yaml
│   │       └── revision.yaml
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── flashcards.py
│   └── features/
│       └── ingestion/
│           ├── README.md
│           ├── __init__.py
│           ├── schema.py
│           ├── parser.py
│           ├── cleaner.py
│           ├── chunker.py
│           ├── dedupe.py
│           ├── store.py
│           ├── loader.py
│           └── ui.py
└── tests/
    └── features/
        ├── __init__.py
        ├── test_ingestion.py
        └── test_ingestion_core.py
```

## Installation
Install all dependencies:
```bash
pip install -e .
```

Or install individually:
```bash
pip install pydantic pyyaml streamlit pymupdf python-docx markdown
```

## Usage

### Test suite
```bash
python -m pytest tests/
```

### Sprint 2: Combined UI (Recommended!)
Launch the full AI Study Assistant (combines content ingestion and study tools):
```bash
streamlit run src/app.py
```

### Sprint 2: Standalone Content Ingestion UI
Launch only the content ingestion app:
```bash
streamlit run src/features/ingestion/ui.py
```

### Sprint 2: Programmatic Usage
```python
from src.features.ingestion.loader import ContentLoader

loader = ContentLoader()

# Load from text
doc = loader.load_text("Your text here", title="My Document")

# Load from file
with open("file.pdf", "rb") as f:
    doc = loader.load_file(f.read(), "file.pdf")

# Get chunks
chunks = loader.store.get_chunks_by_document_id(doc.id)
```

## Sprint 1: Schemas
- **FlashcardSet**: Contains Flashcard objects with front/back content and tags
- **StudyPlan**: Defines a learning goal and topic schedule with dates and durations
- **RevisionSession**: Organizes RevisionItem objects with scheduled review dates and difficulty

## Sprint 1: Agents
The shared registry (`AgentRegistry`) manages three agents:
1. `flashcard_generator` - Generate flashcards from study materials
2. `study_plan_generator` - Create structured study plans with goals and schedules
3. `revision_plan_generator` - Build spaced repetition revision plans

## Sprint 2: Key Features
- **Multi‑format parsing**: TXT, PDF, DOCX, Markdown
- **Text cleaning & normalization**
- **Text chunking** (with configurable size/overlap)
- **Content deduplication** (via SHA-256 hashing)
- **SQLite persistence**
- **Streamlit UI** for easy content upload/paste

For more details, see [src/features/ingestion/README.md](file:///d:/Sprint/Sprint_Task1/ai-content-agents/src/features/ingestion/README.md)

