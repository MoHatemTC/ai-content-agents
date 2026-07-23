
# Sprint 2: Content Ingestion & Processing Lane

## Overview
This lane handles the ingestion, parsing, cleaning, chunking, deduplication, and storage of various content types for use by other lanes (like the Study Agent lane).

## Features

### 1. Document & Chunk Schema
- **Document Model**: Represents a processed document with title, content, source type, file type, creation date, and content hash
- **Chunk Model**: Represents a smaller, retrievable section of a Document with parent document ID, content, index, and character positions

### 2. Multi-Format Parsing
- **TXT**: Plain text parsing
- **PDF**: Using PyMuPDF (fitz)
- **DOCX**: Using python-docx
- **Markdown**: Using markdown library + HTML stripping

### 3. Text Cleaning
- Removes extra whitespace
- Normalizes line breaks
- Trims leading/trailing spaces

### 4. Text Chunking
- Splits long documents into configurable-sized chunks
- Supports overlapping chunks for better context retention
- Default: 1000-character chunks with 100-character overlap

### 5. Deduplication
- Uses SHA-256 hashing of document content
- Prevents storing duplicate documents
- Returns existing document if hash matches

### 6. SQLite Storage
- Stores documents and chunks in a SQLite database
- Auto-initializes tables on first use
- Supports querying chunks by document ID

### 7. Streamlit UI
- **Upload File**: Accepts TXT, PDF, DOCX, Markdown
- **Paste Text**: Direct text input
- **View Processed Content**: Shows document and chunk info

### 8. Combined UI
Integrated with Sprint 1's study tools in [src/app.py](file:///d:/Sprint/Sprint_Task1/ai-content-agents/src/app.py)

## Architecture
```
src/features/ingestion/
├── schema.py       # Pydantic models (Document, Chunk)
├── parser.py       # Multi-format file parsing
├── cleaner.py      # Text cleaning and normalization
├── chunker.py      # Text splitting into chunks
├── dedupe.py       # Content hashing for deduplication
├── store.py        # SQLite storage layer
├── loader.py       # High-level API for content loading
└── ui.py           # Standalone Streamlit UI
```

## Usage

### Programmatic Usage
```python
from src.features.ingestion.loader import ContentLoader

# Initialize loader
loader = ContentLoader()

# Load from file
with open("study_material.pdf", "rb") as f:
    doc = loader.load_file(f.read(), "study_material.pdf")

# Load from text
doc = loader.load_text("This is my study content.", "My Notes")

# Get chunks
chunks = loader.store.get_chunks_by_document_id(doc.id)
```

### Streamlit UI Usage
```bash
# Full combined app (recommended)
streamlit run src/app.py

# Standalone ingestion UI
streamlit run src/features/ingestion/ui.py
```

## Dependencies
- streamlit
- pydantic
- pymupdf
- python-docx
- markdown
- pyyaml (already included in Sprint 1)
