# Demo Dataset Notes

## Overview

The ingestion pipeline includes a built-in demo dataset that populates the Content Library with sample educational documents. This dataset is intended for demonstrations, testing, and development without requiring users to prepare their own files.

---

## Demo Documents

The demo dataset includes the following educational documents:

- Introduction to Python
- Database Fundamentals
- Computer Networks
- Operating Systems
- Object-Oriented Programming

Each document is automatically processed through the complete ingestion pipeline, including:

- Parsing
- Text cleaning
- Quality validation
- Deduplication
- Chunk generation
- SQLite storage

---

## Loading the Demo Dataset

1. Start the Streamlit application:

```bash
streamlit run src/app.py
```

2. Open the **Demo Dataset** tab.

3. Click **Load Demo Dataset**.

---

## Verification

After loading the dataset:

- Open the **Content Library** tab.
- Verify that the demo documents appear in the library.
- Confirm that document metadata (title, source, size, chunk count, and ingestion date) is displayed correctly.

---

## Reproducibility

The demo dataset provides a consistent set of educational documents that can be loaded repeatedly for demonstrations, testing, and benchmarking. Duplicate documents are handled by the ingestion pipeline's deduplication mechanism, preventing duplicate records from being stored.

---

## Expected Result

After successful execution:

- All demo documents are available in the Content Library.
- Documents are stored in the SQLite database.
- Chunks are generated for each document.
- The dataset is ready for demonstrations, testing, and downstream retrieval.