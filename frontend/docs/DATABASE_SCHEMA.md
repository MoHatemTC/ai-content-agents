# Database Schema

Canonical TypeScript shapes live in `src/types/database.types.ts`.

## Tables

- **users** — Supabase `auth.users` (managed).
- **profiles** — `id (PK, FK auth.users)`, `full_name`, `initials`, `avatar_url`, `created_at`.
- **user_roles** — `id`, `user_id (FK auth.users)`, `role app_role('student'|'reviewer'|'admin')`, unique `(user_id, role)`. Roles NEVER live on `profiles`.
- **workspaces** — `id`, `owner_id (FK auth.users)`, `name`, `subject`, `description`, `accent`, `created_at`, `updated_at`.
- **documents** — `id`, `workspace_id (FK workspaces)`, `uploaded_by`, `title`, `kind`, `size_bytes`, `pages`, `chunk_count`, `status('uploaded'|'parsing'|'embedding'|'indexed'|'failed')`, `storage_path`, `notes`, `topics text[]`, `coverage`, `created_at`.
- **chunks** — `id`, `document_id (FK documents)`, `workspace_id`, `index`, `page`, `content`, `token_count`.
- **embeddings** — `id`, `chunk_id (FK chunks)`, `embedding vector(1536)`, `model`.
- **generations** — `id`, `workspace_id`, `created_by`, `kind('question_bank'|'flashcards'|'study_plan'|'revision_sheet'|'test_help')`, `model`, `title`, `payload jsonb`, `document_ids uuid[]`, `grounding_score`, `quality_score`, `review_status('pending'|'approved'|'rejected'|'needs_edit')`, `created_at`.
- **generation_versions** — `id`, `generation_id (FK)`, `version`, `payload jsonb`, `edited_by`, `created_at`.
- **reviews** — `id`, `generation_id (FK)`, `workspace_id`, `item_id`, `reviewer_id`, `status`, `comment`, `created_at`. Append-only: the audit trail is the full row history.
- **chats** — `id`, `workspace_id`, `user_id`, `kind('mentor'|'concept')`, `title`, `model`, `created_at`.
- **chat_messages** — `id`, `chat_id (FK chats)`, `role('user'|'assistant'|'system')`, `content`, `citations jsonb`, `created_at`.
- **notifications** — `id`, `user_id`, `workspace_id`, `roles app_role[]`, `kind`, `title`, `body`, `read`, `created_at`.
- **flashcard_favorites** — `id`, `user_id (FK profiles)`, `generation_id (FK generations, nullable)`, `front`, `back`, `topic`, `format`, `source_chunk_id`, `created_at`, unique `(user_id, front)` (per-user saved flashcards).
- **pipeline_telemetry** — singleton row (`id = 1`): `avg_retrieval_ms`, `top_k`, `embedding_model`, `validation_pass_rate`, `support_checked_pct`, `updated_at` (RAG pipeline health rollups).
- **history** — `id`, `workspace_id`, `user_id`, `generation_id`, `kind`, `title`, `model`, `review_status`, `created_at`.
- **analytics** — `workspace_id`, `captured_at`, `documents`, `generations`, `approvals`, `rejections`, `avg_grounding`, `avg_quality` (materialised or rolled up nightly).

## Relationships

```text
auth.users 1─1 profiles
auth.users 1─n user_roles
auth.users 1─n workspaces (owner_id)
workspaces 1─n documents 1─n chunks 1─1 embeddings
workspaces 1─n generations 1─n generation_versions
generations 1─n reviews
workspaces 1─n chats 1─n chat_messages
workspaces 1─n history, notifications, analytics
```

Everything user-visible is workspace-scoped: `workspace_id` is the isolation key and the primary index on every child table (plus `created_at DESC` for feeds and `vector` index on `embeddings.embedding`).

## Cascade rules

Deleting a workspace cascades to documents, chunks, embeddings, generations, reviews, chats, history and notifications. Deleting a user cascades profile and roles; workspaces should be transferred or soft-archived instead.
