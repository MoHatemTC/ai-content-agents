/**
 * Central registry of every backend endpoint the frontend calls.
 *
 * Single source of truth for URL paths. This is the file a backend team reads
 * to know exactly what the frontend will request. It is derived from
 * docs/FASTAPI_INTEGRATION.md + docs/BACKEND_CONTRACT.md and, where the api
 * modules already call an endpoint the docs have not listed yet, from the
 * calling api module itself (marked "consumer-defined" below).
 *
 * Rules:
 * - Paths are relative; src/api/http.ts prefixes them with env.API_BASE_URL.
 * - When an endpoint is added, update this file FIRST, then the matching
 *   contract type in src/types/api/*.contracts.ts, then the api function and
 *   its service (BACKEND_CONTRACT.md rule 4).
 * - Never hardcode a path string inside an api module — import it from here.
 */

export const paths = {
  /** POST /auth/login · POST /auth/logout · GET /auth/me · POST /auth/refresh */
  auth: {
    login: "/auth/login",
    logout: "/auth/logout",
    me: "/auth/me",
    refresh: "/auth/refresh",
  },

  /** GET/POST /workspaces · GET/PATCH /workspaces/{id} */
  workspaces: {
    list: "/workspaces",
    detail: (id: string) => `/workspaces/${id}`,
  },

  /** Multipart POST /upload · GET/DELETE /documents · GET/PATCH /documents/{id} */
  documents: {
    upload: "/upload",
    list: "/documents",
    detail: (id: string) => `/documents/${id}`,
    parse: (id: string) => `/documents/${id}/parse`,
    chunk: (id: string) => `/documents/${id}/chunk`,
    embed: (id: string) => `/documents/${id}/embed`,
    chunks: (id: string) => `/documents/${id}/chunks`,
    notes: (id: string) => `/documents/${id}/notes`,
  },

  /** POST /generate/{kind} */
  generation: {
    questions: "/generate/questions",
    testHelp: "/generate/test-help",
    flashcards: "/generate/flashcards",
    flashcardTopics: "/generate/flashcard-topics",
    studyPlan: "/generate/study-plan",
    revision: "/generate/revision",
  },

  /** POST /chats · GET /chats · POST /mentor/chat · POST /concept/chat */
  chat: {
    chats: "/chats",
    mentor: "/mentor/chat",
    concept: "/concept/chat",
  },

  /** GET /review · GET /review/items · POST /review/{action} · GET /review/audit */
  review: {
    queue: "/review",
    items: "/review/items",
    approve: "/review/approve",
    reject: "/review/reject",
    needsEdit: "/review/needs-edit",
    flag: "/review/flag",
    comment: "/review/comment",
    audit: "/review/audit",
  },

  /** GET/POST /history */
  history: "/history",

  /** POST /exports (file) · GET /exports?workspace_id= */
  exports: {
    create: "/exports",
    list: "/exports",
  },

  /** GET /health — infra liveness probe (no auth required). */
  health: "/health",

  /** GET /analytics?workspace_id=&range= */
  analytics: "/analytics",

  /** GET /models */
  models: "/models",

  /**
   * Agents, pipeline, notifications and catalogue endpoints. NOT yet listed in
   * docs/FASTAPI_INTEGRATION.md — they are called by src/api/catalogue.api.ts
   * today and recorded here as consumer-defined so the backend has the full
   * inventory.
   */
  catalogue: {
    agents: "/agents",
    agent: (slug: string) => `/agents/${slug}`,
    pipelineSteps: "/pipeline/steps",
    pipelineStages: "/pipeline/stages",
    notifications: "/notifications",
    notificationRead: (id: string) => `/notifications/${id}/read`,
    notificationsReadAll: "/notifications/read-all",
    catalogue: "/catalogue",
  },

  /** GET /search?q= — consumer-defined (src/api/search.api.ts), see note above. */
  search: "/search",

  /** GET /admin/stats — live site-wide totals (staff only, admin dashboard). */
  admin: {
    stats: "/admin/stats",
  },
} as const;
