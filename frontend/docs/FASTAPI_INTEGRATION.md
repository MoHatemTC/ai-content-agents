# FastAPI Integration

Base URL: `VITE_API_BASE_URL`. All routes expect `Authorization: Bearer <supabase_access_token>` unless noted. Responses may be bare JSON or `{ "data": ... }` — the client accepts both.

## Auth

`POST /auth/login` → `{ "session": { "access_token": "...", "refresh_token": "...", "expires_at": 0, "user": { "id": "...", "email": "...", "name": "...", "initials": "AR", "role": "student" } } }` (public)
`POST /auth/logout` → `204`
`GET /auth/me` → `{ "user": { ... } }`
`POST /auth/refresh` `{ "refresh_token": "..." }` → `{ "session": { ... } }`

## Workspaces

`GET /workspaces` → `{ "workspaces": [ { "id": "python-course", "name": "Python Course", "subject": "CS", "description": "", "docs": 4, "assets": 12, "pendingReview": 2, "lastActive": "2h ago", "accent": "primary" } ] }`
`GET /workspaces/{id}` → `{ "workspace": {...}, "data": { "docs": [], "questions": [], "flashcards": [], "chats": [], "history": [], "weakTopics": [], "audit": [] } }`
`POST /workspaces` `{ "name": "...", "description": "..." }` → `{ "workspace": {...} }`
`PATCH /workspaces/{id}` `{ "name?": "...", "description?": "...", "subject?": "..." }` → `204`

## Documents & upload pipeline

`POST /upload` (multipart: `workspace_id`, `file`) → `{ "document": { "id": "doc-1", "title": "...", "kind": "PDF", "size": "4.2 MB", "pages": 148, "uploaded": "2026-07-21", "status": "Ready", "tags": [], "chunks": [] }, "storage_path": "ws/doc-1/file.pdf" }`
`POST /documents/{id}/parse` → `{ "documentId": "doc-1", "pages": 148, "text_length": 91234 }`
`POST /documents/{id}/chunk` → `{ "documentId": "doc-1", "chunks": [ { "id": "c-1", "page": 3, "tokens": 412, "text": "...", "tags": [], "section": "1.2" } ] }`
`POST /documents/{id}/embed` → `{ "documentId": "doc-1", "embedded": 412, "model": "text-embedding-3-small" }`
`GET /documents?workspace_id=` → `{ "documents": [ ... ] }`
`GET /documents/{id}/chunks` → `{ "chunks": [ ... ] }`
`PATCH /documents/{id}` `{ "title?" | "notes?" | "tags?" }` → `204`
`DELETE /documents/{id}` → `204`

## Generation

Common body: `{ "workspaceId": "...", "documentIds": ["doc-1"], "model": "gemini", "options": {} }`

`POST /generate/questions` (+`count`, `difficulty`, `types`) →```json
{
  "generationId": "gen-1",
  "kind": "question_bank",
  "grounding_score": 100,
  "quality_score": 9.2,
  "questions": [
    {
      "id": "q-1",
      "prompt": "...",
      "type": "MCQ",
      "difficulty": "Intermediate",
      "options": ["a", "b"],
      "answer": "a",
      "rationale": "...",
      "bloom": "Understanding",
      "quality": 9.2,
      "grounded": 100,
      "estMinutes": 2,
      "review": "Pending",
      "citations": [{ "doc": "doc-1", "page": 12, "chunk": "c-9", "snippet": "...", "score": 0.92 }]
    }
  ]
}
```

`POST /generate/test-help` → same shape (`options.durationMinutes`).
`POST /generate/flashcards` → `{ "generationId": "...", "kind": "flashcards", "flashcards": [ { "front": "...", "back": "..." } ] }`
`POST /generate/flashcard-topics` → suggested topics for the flashcard form
`POST /generate/study-plan` (+`days`, `hoursPerDay`) → `{ "generationId": "...", "kind": "study_plan", "summary": "...", "sections": [], "days": [ { "day": 1, "topics": ["..."], "hours": 2 } ] }`
`POST /generate/revision` → `{ "generationId": "...", "kind": "revision_sheet", "summary": "...", "sections": [], "weakTopics": [ { "topic": "...", "strength": 42, "action": "..." } ] }`

## Chat

`POST /chats` `{ "workspaceId", "kind": "mentor|concept", "title", "model" }` → `{ "chatId": "chat-1" }`
`POST /mentor/chat` and `POST /concept/chat` `{ "workspaceId", "chatId", "message", "model", "documentIds": [] }` →

```json
{
  "message": { "id": "m-1", "role": "assistant", "text": "...", "time": "14:03" },
  "citations": [{ "docId": "doc-1", "docTitle": "...", "page": 12, "snippet": "..." }]
}
```

`GET /chats?workspace_id=` → `{ "chats": [ { "id", "title", "agent", "model", "date", "messages": [] } ] }`

## Review

`GET /review?workspace_id=` → `{ "itemIds": ["q-1"] }`
`GET /review/items?workspace_id=` → `{ "items": [ { "id", "kind", "status", "items": 2, "createdAt" } ] }` (reload-safe pending queue)
`POST /review/approve` | `/review/reject` | `/review/needs-edit` | `/review/flag` | `/review/comment`
body `{ "workspaceId", "itemId", "comment?", "label?" }` →

```json
{
  "itemId": "q-1",
  "status": "Approved",
  "audit": {
    "id": "aud-1",
    "itemId": "q-1",
    "itemLabel": "...",
    "action": "Approved",
    "actor": "Name 3",
    "at": "2026-08-02 14:03",
    "comment": "..."
  }
}
```

`GET /review/audit?workspace_id=` → `{ "audit": [ ... ] }`

## Export

`POST /exports` `{ "workspaceId", "format": "csv"|"json", "title", "output_id?" }` →
file attachment; `Content-Disposition` carries the filename.
`GET /exports?workspace_id=` → `{ "exports": [ { "id", "format", "status", "created_at" } ] }`
Approved content only — an unapproved item returns `403 not_exportable`.

## Search

`GET /search?q=&workspace_id=` → scored matches across documents, questions,
flashcards and history, each with chunk citations.

## Catalogue & pipeline

`GET /agents` → the 7-agent catalogue · `GET /agents/{slug}` → agent detail
`GET /pipeline/steps` · `GET /pipeline/stages` → pipeline visualisation data
`GET /notifications` → `{ "notifications": [...] }` · `POST /notifications/{id}/read` ·
`POST /notifications/read-all`
`GET /catalogue` → combined catalogue payload

## Admin

`GET /admin/stats` → `{ "documents", "questions", "quality", "chunksIndexed" }`
(staff only, site-wide totals from the platform database).

## Health

`GET /health` → `{ "status": "ok" }` (no auth required — used by `BackendStatus`).

## History & analytics

`GET /history?workspace_id=` → `{ "history": [ { "id", "date", "agent", "doc", "status": "Completed", "quality": 9.2, "review": "Pending", "items": 5, "chatId?" } ] }`
`POST /history` `{ "workspaceId", "row": {...} }` → the row
`GET /analytics?workspace_id=&range=30d` → `{ "bloomDistribution": [{"name":"Analysis","value":12}], "typeDistribution": [...], "activitySeries": [{"week":"W1","questions":20,"flashcards":12,"quality":9.1}], "topicCoverage": [{"topic":"Loops","covered":true,"pct":83}] }`
`GET /models` → `{ "models": [ { "id": "gemini", "name": "Gemini 1.5", "vendor": "Google", "desc": "...", "available": true } ] }`

## Errors

Non-2xx returns `{ "error": { "code": "invalid_credentials", "message": "…", "details": {} } }`.
`400` validation · `401` missing/expired token · `403` role not permitted · `404` unknown id · `409` duplicate workspace slug · `422` unsupported file · `429` model rate limit · `500` provider failure.
