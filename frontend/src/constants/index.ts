/** App-wide constants. No component should hardcode these. */

export const APP_NAME = "Sensei";

export const ROLES = ["student", "reviewer", "admin"] as const;

export const ROLE_HOME: Record<(typeof ROLES)[number], string> = {
  student: "/home",
  reviewer: "/review",
  admin: "/admin",
};

/** Permissions per role — consumed via useAuth().can(), never inline. */
export const ROLE_PERMISSIONS = {
  student: ["review:read", "generation:create", "workspace:read", "document:upload"],
  reviewer: [
    "review:read",
    "review:approve",
    "review:reject",
    "review:edit",
    "review:comment",
    "generation:create",
    "workspace:read",
    "document:upload",
  ],
  admin: [
    "review:read",
    "review:approve",
    "review:reject",
    "review:edit",
    "review:comment",
    "review:manage_queue",
    "analytics:read",
    "reports:read",
    "generation:create",
    "workspace:read",
    "workspace:manage",
    "document:upload",
  ],
} as const;

export type Permission = (typeof ROLE_PERMISSIONS)[keyof typeof ROLE_PERMISSIONS][number];

export const STORAGE_KEYS = {
  session: "cortexa.session",
  workspaceActive: "cortexa.workspace",
  workspaceState: "cortexa.workspace.state",
  theme: "cortexa.theme",
  /** "1" = keep me signed in (session persisted to localStorage); "0" = memory only. */
  remember: "cortexa.remember",
} as const;

export const GENERATION_KINDS = [
  "question_bank",
  "flashcards",
  "study_plan",
  "revision_sheet",
  "test_help",
] as const;
