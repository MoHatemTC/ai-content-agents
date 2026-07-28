# Content Ingestion & Processing

## Overview

The Content Ingestion & Processing lane is responsible for transforming raw educational content into structured documents that can be consumed by downstream study agents.

The ingestion pipeline supports single-file uploads, batch ingestion, directory ingestion, and pasted text while ensuring that only validated, high-quality content is stored.

---

## Supported Formats

- TXT
- PDF
- DOCX
- Markdown

---

## Processing Pipeline

```
Upload / Paste Text
        ↓
      Parse
        ↓
      Clean
        ↓
Quality Validation
        ↓
 Deduplication
        ↓
     Chunking
        ↓
 SQLite Storage
        ↓
 Content Library
```

---

## Schema Contracts

### Document

Represents an ingested document and stores:

- Document ID
- Title
- Content
- Source type
- File type
- Content hash
- Creation timestamp

### Chunk

Represents a section of a document generated during chunking.

Each chunk stores:

- Chunk ID
- Document ID
- Chunk text
- Ordinal position
- Character offsets
- Optional session ID

### BatchResult

Represents the outcome of a batch ingestion operation.

Contains:

- Successfully ingested documents
- Failed files and their associated error messages

---

## Features

- Single-file ingestion
- Batch ingestion
- Directory ingestion
- Text paste ingestion
- Content quality validation
- Duplicate detection using content hashes
- Automatic text cleaning
- Text chunking
- SQLite persistence
- Content Library
- Document deletion
- Upload progress indicators
- Demo dataset loading

---

## Demo Dataset

The application includes a built-in educational sample dataset for demonstration and testing.

To load the dataset:

1. Open the **Demo Dataset** tab.
2. Click **Load Demo Dataset**.
3. Wait for the loading process to complete.
4. Open the **Content Library** tab to view the imported documents and their metadata.

---

## Testing

Run the complete test suite:

```bash
pytest
```

Current status:

- 132 tests passed
- All ingestion, library, batch, quality, parsing, chunking, and deduplication tests pass successfully.

## Getting Started

Run the Streamlit application:

```bash
streamlit run src/app.py
```