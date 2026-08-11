# Backend Contract

Single source of truth: every frontend action → endpoint → auth requirement.
Request/response JSON examples are in `docs/FASTAPI_INTEGRATION.md`; TypeScript contracts in `src/types/api/`.

| Frontend action             | Caller (service)                          | Endpoint                          | Auth          | Roles                             | Errors        |
| --------------------------- | ----------------------------------------- | --------------------------------- | ------------- | --------------------------------- | ------------- |
| Sign in                     | `AuthService.login`                       | `POST /auth/login`                | none          | any                               | 400, 401      |
| Sign out                    | `AuthService.logout`                      | `POST /auth/logout`               | bearer        | any                               | 401           |
| Load current user           | `AuthService.getCurrentUser`              | `GET /auth/me`                    | bearer        | any                               | 401           |
| Refresh session             | `AuthService.refreshSession`              | `POST /auth/refresh`              | refresh token | any                               | 401           |
| List workspaces             | `WorkspaceService.listWorkspaces`         | `GET /workspaces`                 | bearer        | any                               | 401           |
| Open workspace              | `WorkspaceService.getWorkspace`           | `GET /workspaces/{id}`            | bearer        | member                            | 403, 404      |
| Create workspace            | `WorkspaceService.createWorkspace`        | `POST /workspaces`                | bearer        | any                               | 400, 409      |
| Rename workspace            | `WorkspaceService.updateWorkspace`        | `PATCH /workspaces/{id}`          | bearer        | owner/admin                       | 403, 404      |
| Upload file                 | `UploadService.upload`                    | `POST /upload`                    | bearer        | any member                        | 413, 422      |
| Parse / chunk / embed       | `UploadService.parse/chunk/embed`         | `POST /documents/{id}/{stage}`    | bearer        | any member                        | 404, 422, 500 |
| List documents              | `DocumentService.listDocuments`           | `GET /documents?workspace_id=`    | bearer        | member                            | 403           |
| List chunks                 | `DocumentService.listChunks`              | `GET /documents/{id}/chunks`      | bearer        | member                            | 403, 404      |
| Save lecture notes          | `DocumentService.saveNotes`               | `PATCH /documents/{id}/notes`     | bearer        | member                            | 403, 404      |
| Delete document             | `DocumentService.deleteDocument`          | `DELETE /documents/{id}`          | bearer        | owner/admin                       | 403           |
| Generate question bank      | `GenerationService.generateQuestions`     | `POST /generate/questions`        | bearer        | any member                        | 422, 429, 500 |
| Generate exam               | `GenerationService.generateExam`          | `POST /generate/test-help`        | bearer        | any member                        | 422, 429      |
| Generate flashcards         | `GenerationService.generateFlashcards`    | `POST /generate/flashcards`       | bearer        | any member                        | 422, 429      |
| Generate study plan         | `GenerationService.generateStudyPlan`     | `POST /generate/study-plan`       | bearer        | any member                        | 422, 429      |
| Generate revision sheet     | `GenerationService.generateRevisionSheet` | `POST /generate/revision`         | bearer        | any member                        | 422, 429      |
| Start chat                  | `ChatService.createChat`                  | `POST /chats`                     | bearer        | any member                        | 400           |
| Mentor message              | `ChatService.send({kind:'mentor'})`       | `POST /mentor/chat`               | bearer        | any member                        | 429, 500      |
| Concept message             | `ChatService.send({kind:'concept'})`      | `POST /concept/chat`              | bearer        | any member                        | 429, 500      |
| Review queue                | `ReviewService.queue`                     | `GET /review?workspace_id=`       | bearer        | reviewer, admin                   | 403           |
| Approve                     | `ReviewService.approve`                   | `POST /review/approve`            | bearer        | reviewer, admin                   | 403, 404, 409 |
| Reject                      | `ReviewService.reject`                    | `POST /review/reject`             | bearer        | reviewer, admin                   | 403, 404      |
| Request edits               | `ReviewService.requestEdits`              | `POST /review/needs-edit`         | bearer        | reviewer, admin                   | 403           |
| Comment                     | `ReviewService.comment`                   | `POST /review/comment`            | bearer        | reviewer, admin                   | 403           |
| Auto-flag low grounding     | `ReviewService.flag`                      | `POST /review/flag`               | bearer        | system/admin                      | 403           |
| Read review status/comments | `ReviewService.auditHistory`              | `GET /review/audit?workspace_id=` | bearer        | student (own), reviewer, admin    | 403           |
| History list                | `HistoryService.list`                     | `GET /history?workspace_id=`      | bearer        | member                            | 403           |
| Write history row           | `HistoryService.append`                   | `POST /history`                   | bearer        | member                            | 400           |
| Analytics / reports         | `AnalyticsService.get`                    | `GET /analytics?workspace_id=`    | bearer        | admin (workspace metrics: member) | 403           |
| Model catalogue             | `ModelService.fetch`                      | `GET /models`                     | bearer        | any                               | 401           |
| Global search               | `SearchService.search`                    | `GET /search?q=&workspace_id=`    | bearer        | any member                        | 403           |
| Export approved content     | `ExportService.exportApproved`            | `POST /exports`                   | bearer        | any member                        | 403 (not_exportable), 422 |
| List exports                | `ExportService.list`                      | `GET /exports?workspace_id=`      | bearer        | member                            | 403           |
| Admin dashboard stats       | `AdminService.stats`                      | `GET /admin/stats`                | bearer        | admin                             | 403           |
| Backend health probe        | `BackendStatus` (component)               | `GET /health`                     | none          | any                               | —            |
| Agent catalogue             | `AgentService`                            | `GET /agents` · `GET /agents/{slug}` | bearer     | any                               | 401           |
| Notifications               | `NotificationService`                     | `GET /notifications` · `POST .../read` | bearer | any                            | 401           |
| Pipeline stages             | (pipeline page)                           | `GET /pipeline/steps` · `/pipeline/stages` | bearer | any                    | 401           |

## Rules

1. All non-auth endpoints require `Authorization: Bearer <token>`; workspace access is enforced server-side, never by the client.
2. Errors always use `{ "error": { "code", "message", "details" } }`.
3. Permission names used by the UI live in `src/constants/index.ts` (`ROLE_PERMISSIONS`) and must mirror the backend's role checks.
4. Adding an endpoint means updating this table, `src/types/api/`, the matching `*.api.ts` function and its service — in that order. UI stays untouched.
