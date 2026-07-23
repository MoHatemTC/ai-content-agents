
# Content Ingestion & Processing Module

## Overview
This module handles ingestion, parsing, cleaning, chunking, deduplication, and storage of various content types.

## Files
- `schema.py`: Defines Pydantic models for Document and Chunk
- `parser.py`: Parses TXT, PDF, DOCX, and Markdown files into clean text
- `cleaner.py`: Cleans and normalizes text
- `chunker.py`: Splits text into manageable chunks
- `dedupe.py`: Computes content hashes for deduplication
- `store.py`: SQLite storage layer for documents and chunks
- `loader.py`: High-level API for loading files and text
- `ui.py`: Streamlit UI for uploading content

## Usage
### Streamlit UI
```bash
streamlit run src/ingestion/ui.py
```

### Programmatic Usage
```python
from src.ingestion.loader import ContentLoader

loader = ContentLoader()

# Load from text
doc = loader.load_text("Your text here", title="My Document")

# Load from file
with open("file.pdf", "rb") as f:
    doc = loader.load_file(f.read(), "file.pdf")

# Get chunks
chunks = loader.store.get_chunks_by_document_id(doc.id)
```

## Dependencies
- pymupdf (for PDF parsing)
- python-docx (for DOCX parsing)
- markdown (for Markdown parsing)
- streamlit (for UI)
