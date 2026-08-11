/**
 * Domain model types.
 *
 * These are the shapes the UI renders and the shapes the FastAPI backend must
 * return. They live here — never inside `src/mock` — so no component, hook or
 * service ever needs to import a mock module.
 */

/* ── Question bank ─────────────────────────────────────────────────────── */

export type Difficulty = "Beginner" | "Intermediate" | "Advanced";
export type QuestionType = "MCQ" | "True/False" | "Short Answer";
export type ReviewState = "Pending" | "Approved" | "Needs Edit" | "Rejected";
export type BloomLevel =
  "Knowledge" | "Understanding" | "Application" | "Analysis" | "Evaluation" | "Creation";

export interface Citation {
  doc: string;
  page: number;
  chunk: string;
  snippet: string;
  score: number;
}

export interface GeneratedQuestion {
  id: string;
  prompt: string;
  type: QuestionType;
  difficulty: Difficulty;
  options?: string[];
  answer: string;
  rationale: string;
  bloom: BloomLevel;
  quality: number;
  grounded: number;
  estMinutes: number;
  review: ReviewState;
  citations: Citation[];
}

/* ── Catalogue documents (marketing / demo library) ────────────────────── */

export interface DocItem {
  id: string;
  title: string;
  kind: "PDF" | "DOCX" | "PPTX" | "TXT";
  size: string;
  pages: number;
  chunks: number;
  uploaded: string;
  status: "Indexed" | "Embedding" | "Parsing" | "Failed";
  topics: string[];
  coverage: number;
}

export interface HistoryItem {
  id: string;
  date: string;
  agent: string;
  doc: string;
  status: "Completed" | "Running" | "Failed";
  quality: number;
  review: ReviewState;
  items: number;
}

/* ── Agents & pipeline ────────────────────────────────────────────────── */

export type AgentIcon =
  "compass" | "lightbulb" | "list-checks" | "target" | "layers" | "calendar" | "sparkle";

export interface Agent {
  slug: string;
  name: string;
  tagline: string;
  bullets: string[];
  icon: AgentIcon;
  runs: number;
}

export interface PipelineStep {
  key: string;
  label: string;
  detail: string;
}

/* ── Workspace-scoped entities ────────────────────────────────────────── */

export type DocKind = "PDF" | "DOCX" | "PPTX" | "TXT" | "Note";

export interface WsChunk {
  id: string;
  page: number;
  tokens: number;
  text: string;
  tags: string[];
  section: string;
}

export interface WsDoc {
  id: string;
  title: string;
  kind: DocKind;
  size: string;
  pages: number;
  uploaded: string;
  status: "Ready" | "Processing";
  tags: string[];
  notes?: string;
  chunks: WsChunk[];
  /** Backend storage path for file-backed documents (uploaded files). */
  storagePath?: string;
  /** Raw byte size, carried through so the record can be persisted accurately. */
  sizeBytes?: number;
}

export interface ChatCitation {
  docId: string;
  docTitle: string;
  page?: number;
  snippet: string;
}

export interface WsChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  time: string;
  /** Chunks the assistant reply was grounded on (present on chat replies). */
  citations?: ChatCitation[];
}

export interface WsChat {
  id: string;
  title: string;
  agent: string;
  model: string;
  date: string;
  messages: WsChatMessage[];
}

export interface WsHistoryRow {
  id: string;
  date: string;
  agent: string;
  doc: string;
  status: "Completed" | "Running" | "Failed";
  quality: number;
  review: ReviewState;
  items: number;
  chatId?: string;
  /** Supabase generations row this run is persisted under (for reopen). */
  generationId?: string;
}

export interface WsFlashcard {
  front: string;
  back: string;
  tag?: string;
  /** "term-definition" or "qa". */
  format?: string;
  /** Real content topic the card drills (from the PDF's topic allow-list). */
  topic?: string;
  /** Ingestion chunk id the card cites, when the model produced one. */
  sourceChunkId?: string;
  citations?: Citation[];
}

export type AuditAction = "Approved" | "Rejected" | "Needs Edit" | "Flagged" | "Comment";

export interface WsAuditEntry {
  id: string;
  itemId: string;
  itemLabel: string;
  action: AuditAction;
  actor: string;
  at: string;
  comment?: string;
}

export interface WeakTopic {
  topic: string;
  strength: number;
  action: string;
  /** One-line summary of what to revisit for this topic. */
  description?: string;
  /** Per-topic difficulty: easy / medium / hard. */
  difficulty?: string;
  /** Suggested review-by date (ISO). */
  nextRevisionDate?: string;
  /** Optional self-check prompt for this topic. */
  confidencePrompt?: string;
}

export interface WorkspaceData {
  docs: WsDoc[];
  questions: GeneratedQuestion[];
  flashcards: WsFlashcard[];
  chats: WsChat[];
  history: WsHistoryRow[];
  weakTopics: WeakTopic[];
  audit?: WsAuditEntry[];
}

export type WorkspaceAccent = "primary" | "info" | "success" | "warning";

export interface Workspace {
  id: string;
  name: string;
  subject: string;
  description?: string;
  docs: number;
  assets: number;
  pendingReview: number;
  generations: number;
  reviewStatus: ReviewState;
  lastActive: string;
  accent: WorkspaceAccent;
  owner: {
    id: string;
    name: string;
    email: string;
  };
}

/* ── Search ───────────────────────────────────────────────────────────── */

export type SearchResultKind = "document" | "question" | "flashcard" | "concept" | "history";

export interface SearchResult {
  id: string;
  kind: SearchResultKind;
  title: string;
  subtitle?: string;
  /** In-app route the result opens. */
  to: string;
}

/* ── Studio outputs, notifications & pipeline stages ──────────────────── */

export type OutputStatus = "Draft" | "Pending Review" | "Approved" | "Rejected" | "Needs Editing";

export interface SourceRef {
  doc: string;
  page: number;
  chunk: string;
  snippet: string;
  score: number;
}

export interface AssetCard {
  id: string;
  agent: string;
  model: string;
  kind: "Question" | "Flashcard" | "Explanation" | "Plan" | "Revision sheet" | "Mentor note";
  title: string;
  body: string;
  meta: string[];
  answer?: string;
  rationale: string;
  status: OutputStatus;
  confidence: number;
  grounding: number;
  validation: { schema: boolean; support: boolean; duplicates: boolean; notes: string };
  sources: SourceRef[];
  createdAt: string;
  reviewer?: string;
  reviewerNote?: string;
  versions: number;
}

export type NotificationKind = "review" | "validation" | "export" | "grounding" | "done";

export interface AppNotification {
  id: string;
  kind: NotificationKind;
  title: string;
  detail: string;
  time: string;
  unread: boolean;
  /** Which roles should see this notification. */
  roles: Array<"student" | "reviewer" | "admin">;
}

export interface RagStage {
  key: string;
  label: string;
  detail: string;
}

/* ── Analytics ────────────────────────────────────────────────────────── */

export interface DistributionBucket {
  name: string;
  value: number;
}

export interface ActivityPoint {
  week: string;
  questions: number;
  flashcards: number;
  quality: number;
}

export interface TopicCoverage {
  topic: string;
  covered: boolean;
  pct: number;
}
