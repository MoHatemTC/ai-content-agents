# End-to-End Demo Guide

## Overview

This guide demonstrates the complete Content Agents workflow, from document ingestion to review and export gate verification.


---


Start the application:

```bash
streamlit run src/app.py
```

---

# Demo Workflow

## Step 1 — Upload Content

1. Open the **Upload File** page.
2. Upload a supported document (TXT, PDF, DOCX, or Markdown).
3. Wait for the ingestion process to complete.

### Verify

- Upload succeeds.
- Document is parsed.
- Chunks are generated.
- Document is stored.

---

## Step 2 — Content Library

Open the **Content Library**.

Verify:

- Title
- Source
- File type
- File size
- Chunk count
- Ingestion date

---

## Step 3 — Retrieval

Select the uploaded document.

Verify that retrieval returns only chunks belonging to the selected document.

No cross-document content should appear.

---

## Step 4 — AI Generation

Generate a Mentor Agent response.

Verify that:

- A structured response is generated.
- References are included.
- The output is marked for human review.

---

## Step 5 — Validation

Run the generated output through the validation pipeline.

Verify:

- Schema validation passes.
- Guardrail checks execute.
- Validation report is generated.

---

## Step 6 — Evaluation

Run the output through the evaluation pipeline.

Verify:

- Validation status
- Quality score
- Grounding information
- Evaluation notes

---

## Step 7 — Human Review

Apply review actions to the generated output.

Verify the review lifecycle:

- Pending → Edited
- Edited → Approved

Illegal transitions should be rejected.

---

## Step 8 — Export Gate

Attempt to export:

- Pending output
- Edited output
- Approved output

Verify:

- Pending outputs are blocked.
- Edited outputs are blocked.
- Approved outputs are eligible for export.

---

# Expected Outcome

The complete workflow demonstrates that:

- Content is successfully ingested.
- Metadata is correctly stored.
- Retrieval remains document-scoped.
- AI outputs pass validation.
- Evaluation completes successfully.
- Human review controls approval.
- Only approved outputs are permitted through the export gate.