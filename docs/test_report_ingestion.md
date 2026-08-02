# Content Ingestion & Library Test Report

## Overview

This report documents the end-to-end testing performed on the Content Ingestion and Content Library features.

The objective was to verify that supported document formats are correctly ingested, parsed, validated, chunked, stored, and displayed in the content library while ensuring reliable metadata persistence, duplicate prevention, quality validation, and document isolation.

---

## Test Environment

| Item | Value |
|------|-------|
| Operating System | Windows 10 |
| Python | 3.14 |
| Framework | Streamlit |
| Database | SQLite |
| Test Date | August 2026 |
| Branch | PR #12 |

## Test Cases

### TC-01 Multi-Format Upload

**Objective**

Verify that supported file formats are successfully ingested into the content library.

**Supported formats**

- TXT
- PDF
- DOCX
- Markdown

**Steps**

1. Launch the Streamlit application.
2. Navigate to **Upload File**.
3. Upload one file of each supported format.
4. Wait for ingestion to complete.
5. Open the Content Library.

**Expected Result**

- File uploads successfully.
- Content is parsed correctly.
- Chunks are generated.
- Metadata is stored.
- Document appears in the Content Library.

**Actual Result**

All supported file formats were successfully uploaded, parsed, chunked, and stored. Each uploaded document appeared correctly in the Content Library.

**Status**

 Pass


 ### TC-02 Library Metadata Verification

**Objective**

Verify that document metadata is accurately stored and displayed in the Content Library after ingestion.

### Verification Evidence

| Metadata Field | Verified | Result |
|---------------|----------|--------|
| Title | Yes | Matches uploaded document |
| Source | Yes | Correctly displayed |
| File Type | Yes | Matches uploaded format |
| File Size | Yes | Correctly stored |
| Chunk Count | Yes | Matches generated chunks |
| Ingestion Date | Yes | Correct timestamp recorded |


**Steps**

1. Launch the Streamlit application.
2. Upload one or more supported documents.
3. Navigate to the **Content Library** tab.
4. Verify the displayed metadata for each document.
5. Compare the displayed metadata with the corresponding records stored in the SQLite database.

**Expected Result**

- The document title matches the uploaded file.
- The source is correctly recorded.
- The file type matches the uploaded document format.
- The file size is accurately displayed.
- The chunk count reflects the number of generated chunks.
- The ingestion date is correctly recorded.

**Actual Result**

All metadata fields were correctly stored and displayed in the Content Library. The metadata matched the corresponding records in the SQLite database, including document title, source, file type, file size, chunk count, and ingestion timestamp.

**Status**

 Pass

### TC-03 Deduplication

**Objective**

Verify that uploading an identical document multiple times does not create duplicate document or chunk records.


### Verification Evidence

| Upload | Documents Before | Documents After | Result |
|---------|-----------------:|----------------:|--------|
| First upload | 5 | 6 | Document added |
| Second upload (identical file) | 6 | 6 | No duplicate created |


**Steps**

1. Launch the Streamlit application.
2. Upload a supported document.
3. Confirm that the document appears in the Content Library.
4. Upload the exact same document again.
5. Check the Content Library and SQLite database for duplicate records.

**Expected Result**

- The duplicate document is detected using the content hash.
- A second document record is not created.
- Duplicate chunks are not generated.
- The existing document remains unchanged.

**Actual Result**

The ingestion pipeline successfully detected the duplicate document using the content hash. No additional document or chunk records were created, and the original document remained unchanged in the Content Library.

**Status**

Pass

### TC-04 Quality Safeguards & Error Handling

**Objective**

Verify that invalid or low-quality content is rejected before ingestion, appropriate error messages are displayed to the user, and invalid documents are not stored in the Content Library.

**Test Cases**

- Empty text file
- Near-empty text file
- Corrupted PDF
- Corrupted DOCX
- Empty pasted text
- Batch upload containing both valid and invalid files

**Steps**

1. Launch the Streamlit application.
2. Attempt to upload each invalid file individually.
3. Verify that an appropriate error message is displayed.
4. Confirm that the invalid document is not added to the Content Library.
5. Perform a batch upload containing both valid and invalid files.
6. Verify that valid files are ingested successfully while invalid files are reported without stopping the batch process.

**Expected Result**

- Empty, near-empty, and corrupted files are rejected.
- User-friendly error messages are displayed.
- Invalid documents are not stored in the database.
- Batch ingestion continues processing valid files even if one or more files fail.

**Actual Result**

The ingestion pipeline correctly rejected invalid content and displayed clear error messages to the user. Invalid documents were not stored in the Content Library or SQLite database. During batch ingestion, invalid files were reported individually while valid files continued to be processed successfully.

**Status**

Pass

### TC-05 Batch Upload Error Isolation

**Objective**

Verify that batch uploads continue processing valid files even when one or more files fail validation.

**Steps**

1. Launch the Streamlit application.
2. Navigate to the **Batch Upload** tab.
3. Select multiple files including:
   - At least one valid supported document.
   - At least one invalid or low-quality document.
4. Start the batch upload.
5. Verify the upload results in the UI.
6. Open the Content Library.

**Expected Result**

- Valid files are successfully ingested.
- Invalid files are rejected with clear error messages.
- The batch process continues without stopping after encountering an invalid file.
- Only valid documents appear in the Content Library.

**Actual Result**

The batch ingestion process successfully uploaded all valid documents while rejecting invalid files individually. Appropriate error messages were displayed for failed uploads, and the remaining files continued processing without interruption.

**Status**

Pass

### TC-06 Document Selection Contract

**Objective**

Verify that selecting a document returns only the chunks belonging to that document without exposing chunks from other stored documents.

**Steps**

1. Upload multiple documents containing different topics.
2. Retrieve the chunks for each document using its document ID.
3. Compare the returned chunks with the original document content.
4. Verify that no chunks from other documents are returned.

**Expected Result**

Only the chunks belonging to the selected document are returned.

**Actual Result**

Each document returned only its own content. No chunks from other documents were included, confirming that document retrieval is correctly scoped by document ID.

**Status**

Pass

### TC-07 Demo Dataset Reproducibility

**Objective**

Verify that the built-in demo dataset loads successfully and can be reproduced consistently for demonstrations and testing.

**Steps**

1. Launch the Streamlit application.
2. Open the **Demo Dataset** tab.
3. Click **Load Demo Dataset**.
4. Verify that the demo documents appear in the Content Library.
5. Repeat the loading process and verify consistent behavior.

**Expected Result**

- The demo dataset loads successfully.
- All demo documents are stored in the SQLite database.
- Metadata is correctly displayed in the Content Library.
- Duplicate documents are handled according to the ingestion pipeline's deduplication mechanism.

**Actual Result**

The demo dataset loaded successfully into the Content Library. All demo documents were processed through the ingestion pipeline, stored in the SQLite database, and displayed with the correct metadata. Repeated execution produced consistent behavior without environment-related issues.

**Status**

Pass



---


## Bug Log

The following edge-case scenarios were tested to identify potential defects. All scenarios behaved as expected, and no functional defects were observed during testing.

### BR-01 Empty File Upload

**Status:** Expected Behavior (No Defect)

**Steps to Reproduce**
1. Open the Upload File page.
2. Upload an empty TXT file.

**Expected Result**
The file is rejected with a user-friendly error message and is not stored.

**Actual Result**
The application displayed an error message and prevented ingestion.

**Conclusion**
No defect observed.

### BR-02 Corrupted PDF

**Status:** Expected Behavior (No Defect)

**Steps to Reproduce**
1. Rename a text file to `.pdf`.
2. Upload it.

**Expected Result**
The upload is rejected and the document is not stored.

**Actual Result**
The application rejected the file and displayed an appropriate error message.

**Conclusion**
No defect observed.

### BR-03 Near-Empty Document

**Status:** Expected Behavior (No Defect)

**Steps to Reproduce**
1. Upload a document containing only a few words.

**Expected Result**
The quality validation blocks the upload.

**Actual Result**
The upload was rejected by the quality validation rules.

**Conclusion**
No defect observed.


## Summary

A total of **7 functional test cases** were executed covering multi-format uploads, metadata verification, deduplication, quality validation, batch upload behavior, document retrieval isolation, and demo dataset reproducibility.

All test cases passed successfully. The ingestion pipeline correctly parsed supported documents, generated chunks, persisted metadata in SQLite, prevented duplicate content, rejected invalid input, and isolated document retrieval without cross-document leakage.

Overall Result: **PASS**
