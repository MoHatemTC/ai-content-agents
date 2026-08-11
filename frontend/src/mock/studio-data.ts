import type { AppNotification, AssetCard, RagStage, SourceRef, Workspace } from "@/types/domain";

export type {
  AppNotification,
  AssetCard,
  NotificationKind,
  OutputStatus,
  RagStage,
  SourceRef,
} from "@/types/domain";
// Frontend-only demo data for the redesigned Content Agents experience.
// No backend / AI calls — everything here is static design fixture data.

export const workspaces: Workspace[] = [
  {
    id: "python-course",
    name: "Python Course",
    subject: "CS1010 · Semester 2",
    docs: 3,
    assets: 148,
    pendingReview: 3,
    generations: 42,
    reviewStatus: "Pending",
    lastActive: "12 minutes ago",
    accent: "primary",
    owner: {
      id: "user-student",
      name: "Nour Atef",
      email: "student@sensei.ai",
    },
  },
  {
    id: "operating-systems",
    name: "Operating Systems",
    subject: "CS3050 · Scheduling & memory",
    docs: 2,
    assets: 86,
    pendingReview: 1,
    generations: 23,
    reviewStatus: "Pending",
    lastActive: "Yesterday",
    accent: "info",
    owner: {
      id: "user-reviewer",
      name: "Name 3",
      email: "reviewer@sensei.ai",
    },
  },
  {
    id: "networking",
    name: "Networking",
    subject: "CS2210 · Layered models",
    docs: 4,
    assets: 61,
    pendingReview: 0,
    generations: 17,
    reviewStatus: "Approved",
    lastActive: "3 days ago",
    accent: "success",
    owner: {
      id: "user-admin",
      name: "Yousef Alaa",
      email: "admin@sensei.ai",
    },
  },
  {
    id: "algorithms",
    name: "Algorithms",
    subject: "CS2400 · Complexity",
    docs: 2,
    assets: 34,
    pendingReview: 2,
    generations: 9,
    reviewStatus: "Needs Edit",
    lastActive: "Last week",
    accent: "warning",
    owner: {
      id: "user-student",
      name: "Nour Atef",
      email: "student@sensei.ai",
    },
  },
];

export interface ModelOption {
  id: string;
  name: string;
  vendor: string;
  note: string;
  latency: string;
  badge?: string;
}

export const models: ModelOption[] = [
  {
    id: "gemini-flash",
    name: "Gemini 2.5 Flash",
    vendor: "Google",
    note: "Fast, cheap, long context",
    latency: "1.2s",
    badge: "Default",
  },
  {
    id: "gemini-pro",
    name: "Gemini 2.5 Pro",
    vendor: "Google",
    note: "Best reasoning for hard items",
    latency: "4.1s",
  },
  {
    id: "claude-sonnet",
    name: "Claude Sonnet",
    vendor: "Anthropic",
    note: "Strongest explanations",
    latency: "3.4s",
  },
  {
    id: "gpt-mini",
    name: "GPT mini",
    vendor: "OpenAI",
    note: "Balanced generalist",
    latency: "2.0s",
  },
  {
    id: "kimi-k2",
    name: "Kimi K2",
    vendor: "Moonshot",
    note: "Very long documents",
    latency: "3.8s",
  },
  {
    id: "openrouter-auto",
    name: "OpenRouter Auto",
    vendor: "OpenRouter",
    note: "Routes to cheapest capable model",
    latency: "~2.5s",
  },
  {
    id: "local-llama",
    name: "Local Llama 3",
    vendor: "Self-hosted",
    note: "Runs on-prem, no data egress",
    latency: "6.2s",
    badge: "Offline",
  },
];

export type ControlKind = "segmented" | "slider" | "toggle" | "text" | "date" | "tags";

export interface AgentControl {
  key: string;
  label: string;
  kind: ControlKind;
  options?: string[];
  min?: number;
  max?: number;
  step?: number;
  value: string | number | boolean | string[];
  hint?: string;
  future?: boolean;
}

export interface StudioAgent {
  slug: string;
  name: string;
  short: string;
  blurb: string;
  placeholder: string;
  icon: string;
  controls: AgentControl[];
}

export const studioAgents: StudioAgent[] = [
  {
    slug: "question-bank",
    name: "Question Bank",
    short: "Questions",
    blurb: "Grounded MCQ, true/false and short-answer banks with rationale.",
    placeholder: "Generate a question bank covering iteration and comprehensions…",
    icon: "list-checks",
    controls: [
      {
        key: "type",
        label: "Question type",
        kind: "segmented",
        options: ["MCQ", "True/False", "Short Answer"],
        value: "MCQ",
      },
      {
        key: "difficulty",
        label: "Difficulty",
        kind: "segmented",
        options: ["Beginner", "Intermediate", "Advanced"],
        value: "Intermediate",
      },
      {
        key: "count",
        label: "Question count",
        kind: "slider",
        min: 4,
        max: 40,
        step: 2,
        value: 12,
      },
      {
        key: "bloom",
        label: "Bloom level",
        kind: "segmented",
        options: ["Auto", "Recall", "Apply", "Analyse"],
        value: "Auto",
        future: true,
        hint: "Coming soon",
      },
    ],
  },
  {
    slug: "mentor",
    name: "Mentor",
    short: "Mentor",
    blurb: "Conversational coaching that adapts to the learner's level.",
    placeholder: "I keep mixing up mutable and immutable types — help me…",
    icon: "compass",
    controls: [
      {
        key: "goal",
        label: "Learning goal",
        kind: "text",
        value: "Pass the mid-term on data structures",
      },
      {
        key: "level",
        label: "Student level",
        kind: "segmented",
        options: ["Beginner", "Intermediate", "Advanced"],
        value: "Beginner",
      },
    ],
  },
  {
    slug: "test-help",
    name: "Test Help",
    short: "Test Help",
    blurb: "Exam-style practice with hints and timed conditions.",
    placeholder: "Build a 30-minute mock exam on functions and scope…",
    icon: "target",
    controls: [
      {
        key: "difficulty",
        label: "Difficulty",
        kind: "segmented",
        options: ["Beginner", "Intermediate", "Advanced"],
        value: "Advanced",
      },
      {
        key: "style",
        label: "Exam style",
        kind: "segmented",
        options: ["Mixed", "MCQ only", "Written"],
        value: "Mixed",
      },
      { key: "hints", label: "Show hints", kind: "toggle", value: true },
      { key: "timed", label: "Timed mode", kind: "toggle", value: false },
    ],
  },
  {
    slug: "flashcards",
    name: "Flashcards",
    short: "Flashcards",
    blurb: "Spaced-repetition ready cards, front and back, with sources.",
    placeholder: "Make flashcards for every built-in sequence type…",
    icon: "layers",
    controls: [
      { key: "count", label: "Card count", kind: "slider", min: 10, max: 100, step: 5, value: 40 },
      {
        key: "difficulty",
        label: "Difficulty",
        kind: "segmented",
        options: ["Beginner", "Intermediate", "Advanced"],
        value: "Beginner",
      },
      { key: "cloze", label: "Cloze deletions", kind: "toggle", value: false },
    ],
  },
  {
    slug: "concept",
    name: "Concept Explanation",
    short: "Concepts",
    blurb: "Structured breakdowns: summary, key points, examples, analogies.",
    placeholder: "Explain the iteration protocol as if I've never seen it…",
    icon: "lightbulb",
    controls: [
      {
        key: "depth",
        label: "Explanation depth",
        kind: "segmented",
        options: ["Quick", "Standard", "Deep dive"],
        value: "Standard",
      },
      {
        key: "examples",
        label: "Worked examples",
        kind: "slider",
        min: 0,
        max: 6,
        step: 1,
        value: 2,
      },
      {
        key: "visual",
        label: "Visual explanation",
        kind: "toggle",
        value: true,
        hint: "Diagrams where the source supports it",
      },
    ],
  },
  {
    slug: "study-plan",
    name: "Study Plan",
    short: "Study Plan",
    blurb: "A schedule built from your goals, time budget and weak areas.",
    placeholder: "Plan my revision for the final in three weeks…",
    icon: "calendar",
    controls: [
      {
        key: "hours",
        label: "Study hours / week",
        kind: "slider",
        min: 2,
        max: 30,
        step: 1,
        value: 8,
      },
      { key: "date", label: "Target exam date", kind: "date", value: "2026-08-24" },
      {
        key: "intensity",
        label: "Pace",
        kind: "segmented",
        options: ["Relaxed", "Steady", "Intense"],
        value: "Steady",
      },
    ],
  },
  {
    slug: "revision",
    name: "Revision Assistant",
    short: "Revision",
    blurb: "Last-mile revision sheets targeting your weakest concepts.",
    placeholder: "Give me a one-page revision sheet for tomorrow…",
    icon: "sparkle",
    controls: [
      {
        key: "weak",
        label: "Weak topics",
        kind: "tags",
        value: ["Classes", "Files", "Decorators"],
      },
      {
        key: "intensity",
        label: "Revision intensity",
        kind: "segmented",
        options: ["Light", "Focused", "Cram"],
        value: "Focused",
      },
    ],
  },
];

export const assets: AssetCard[] = [
  {
    id: "out-9012",
    agent: "Question Bank",
    model: "Gemini 2.5 Flash",
    kind: "Question",
    title: "Which statement best describes a mutable default argument in a Python function?",
    body: "A. A fresh object is created on every call\nB. The same object persists across calls and accumulates state\nC. Python raises a SyntaxError at definition time\nD. The argument is silently converted to a tuple",
    meta: ["MCQ", "Advanced", "Analysis", "2 min"],
    answer: "B — the same object persists across calls and accumulates state.",
    rationale:
      "Default arguments are evaluated exactly once, when the def statement executes. A mutable default therefore becomes shared state across every invocation, which the source chapter demonstrates with an appending list example.",
    status: "Pending Review",
    confidence: 94,
    grounding: 100,
    validation: { schema: true, support: true, duplicates: true, notes: "All checks passed." },
    sources: [
      {
        doc: "Introduction to Python Programming",
        page: 74,
        chunk: "chunk_0182",
        snippet:
          "Default parameter values are evaluated exactly once, when the def statement is executed…",
        score: 0.94,
      },
      {
        doc: "Introduction to Python Programming",
        page: 75,
        chunk: "chunk_0183",
        snippet: "This is why appending to a default list argument produces surprising results.",
        score: 0.88,
      },
    ],
    createdAt: "Today · 09:12",
    versions: 2,
  },
  {
    id: "out-9011",
    agent: "Concept Explanation",
    model: "Claude Sonnet",
    kind: "Explanation",
    title: "The iteration protocol, end to end",
    body: "A for loop never touches your object directly. It calls iter() on it, which must return an iterator — an object with __next__. Each pass calls __next__ until StopIteration is raised, at which point the loop exits cleanly.",
    meta: ["Standard depth", "2 examples", "Diagram"],
    rationale:
      "Built from the chapter's protocol section plus the worked generator example on the following page; the analogy is generated, the mechanics are quoted.",
    status: "Approved",
    confidence: 97,
    grounding: 100,
    validation: { schema: true, support: true, duplicates: true, notes: "All checks passed." },
    sources: [
      {
        doc: "Introduction to Python Programming",
        page: 51,
        chunk: "chunk_0121",
        snippet: "An iterable is any object defining __iter__ which returns an iterator object.",
        score: 0.91,
      },
    ],
    createdAt: "Today · 08:41",
    reviewer: "Amira R.",
    reviewerNote: "Clear and accurate — approved for the revision pack.",
    versions: 1,
  },
  {
    id: "out-9010",
    agent: "Flashcards",
    model: "Gemini 2.5 Flash",
    kind: "Flashcard",
    title: "Front: What does len() call under the hood?",
    body: "Back: The object's __len__ method. Any object implementing it works with len().",
    meta: ["Beginner", "Deck: Python core"],
    rationale: "Direct restatement of the data-model table in the source chapter.",
    status: "Approved",
    confidence: 99,
    grounding: 100,
    validation: { schema: true, support: true, duplicates: true, notes: "All checks passed." },
    sources: [
      {
        doc: "Introduction to Python Programming",
        page: 118,
        chunk: "chunk_0301",
        snippet: "len(obj) is equivalent to obj.__len__() for any sized container.",
        score: 0.97,
      },
    ],
    createdAt: "Yesterday · 17:44",
    reviewer: "Amira R.",
    versions: 1,
  },
  {
    id: "out-9009",
    agent: "Question Bank",
    model: "GPT mini",
    kind: "Question",
    title: "Explain the difference between a class attribute and an instance attribute.",
    body: "Short answer · expected 2–3 sentences.",
    meta: ["Short Answer", "Intermediate", "Understanding"],
    answer:
      "A class attribute lives on the class and is shared by all instances; an instance attribute lives in the object's __dict__ and shadows the class attribute once assigned.",
    rationale:
      "The chapter contrasts both lookup paths and shows shadowing with a counter example.",
    status: "Needs Editing",
    confidence: 82,
    grounding: 96,
    validation: {
      schema: true,
      support: true,
      duplicates: false,
      notes: "Near-duplicate of out-8974 (similarity 0.91). Consider merging or rephrasing.",
    },
    sources: [
      {
        doc: "Introduction to Python Programming",
        page: 102,
        chunk: "chunk_0264",
        snippet: "Attribute lookup first checks the instance dictionary, then the class…",
        score: 0.9,
      },
    ],
    createdAt: "Yesterday · 15:20",
    reviewer: "Omar K.",
    reviewerNote: "Answer is right but overlaps an existing item — rephrase around shadowing only.",
    versions: 3,
  },
  {
    id: "out-9008",
    agent: "Study Plan",
    model: "Gemini 2.5 Pro",
    kind: "Plan",
    title: "Three-week plan · 8 hours per week · exam 24 Aug",
    body: "Week 1 — Variables, loops, functions (3 sessions + 20 recall questions).\nWeek 2 — Classes, files, exceptions (3 sessions, weakest area, double practice).\nWeek 3 — Mixed mock exams and revision sheets, tapering to light recall the final two days.",
    meta: ["8 h/week", "Steady", "24 Aug"],
    rationale:
      "Weighted by topic coverage: Classes (38%) and Files (24%) are under-covered, so week 2 allocates the extra sessions.",
    status: "Draft",
    confidence: 88,
    grounding: 91,
    validation: {
      schema: true,
      support: true,
      duplicates: true,
      notes: "Grounding below 95% target — plan text is partly generated.",
    },
    sources: [
      {
        doc: "Introduction to Python Programming",
        page: 3,
        chunk: "chunk_0004",
        snippet:
          "Course outline: five units across variables, control flow, functions, classes and file I/O.",
        score: 0.86,
      },
    ],
    createdAt: "Yesterday · 11:03",
    versions: 1,
  },
  {
    id: "out-9007",
    agent: "Mentor",
    model: "Claude Sonnet",
    kind: "Mentor note",
    title: "Why your loop keeps skipping the last element",
    body: "You're using range(len(items) - 1), which stops one short. range's stop value is exclusive, so range(len(items)) already ends at the final index.",
    meta: ["Beginner", "Goal: mid-term"],
    rationale:
      "Grounded in the range() semantics section; the diagnosis of the learner's error is inferred from their prompt.",
    status: "Rejected",
    confidence: 71,
    grounding: 64,
    validation: {
      schema: true,
      support: false,
      duplicates: true,
      notes:
        "Support check failed: the learner's code was not in the indexed content, so part of the answer is ungrounded.",
    },
    sources: [
      {
        doc: "Introduction to Python Programming",
        page: 44,
        chunk: "chunk_0098",
        snippet: "range(stop) yields values from 0 up to but not including stop.",
        score: 0.79,
      },
    ],
    createdAt: "2 days ago · 20:31",
    reviewer: "Omar K.",
    reviewerNote: "Rejected — advice extends beyond the indexed material.",
    versions: 1,
  },
];

export interface ChatTurn {
  id: string;
  role: "user" | "assistant";
  text: string;
  agent?: string;
  model?: string;
  assetIds?: string[];
  citations?: SourceRef[];
  time: string;
}

export const conversation: ChatTurn[] = [
  {
    id: "t1",
    role: "user",
    text: "Build me an intermediate question bank on iteration and comprehensions from the Python chapter.",
    time: "09:10",
  },
  {
    id: "t2",
    role: "assistant",
    agent: "Question Bank",
    model: "Gemini 2.5 Flash",
    text: "I retrieved 8 chunks covering the iteration protocol, for-loop desugaring and comprehension syntax, then drafted 12 items. Every item cites at least one chunk; two items were dropped by the duplicate check.",
    assetIds: ["out-9012", "out-9009"],
    citations: [
      {
        doc: "Introduction to Python Programming",
        page: 51,
        chunk: "chunk_0121",
        snippet: "An iterable is any object defining __iter__ which returns an iterator object.",
        score: 0.91,
      },
      {
        doc: "Introduction to Python Programming",
        page: 74,
        chunk: "chunk_0182",
        snippet: "Default parameter values are evaluated exactly once…",
        score: 0.94,
      },
    ],
    time: "09:12",
  },
  {
    id: "t3",
    role: "user",
    text: "The short-answer one feels like a repeat. Explain the concept instead.",
    time: "09:15",
  },
  {
    id: "t4",
    role: "assistant",
    agent: "Concept Explanation",
    model: "Claude Sonnet",
    text: "Switched to the Concept Explanation agent. Here's a structured breakdown of the iteration protocol with two worked examples — all mechanics quoted from page 51.",
    assetIds: ["out-9011"],
    citations: [
      {
        doc: "Introduction to Python Programming",
        page: 51,
        chunk: "chunk_0121",
        snippet: "An iterable is any object defining __iter__ which returns an iterator object.",
        score: 0.91,
      },
    ],
    time: "09:16",
  },
];

export interface OutlineNode {
  id: string;
  label: string;
  page: number;
  chunks: number;
  children?: OutlineNode[];
}

export const documentOutline: OutlineNode[] = [
  {
    id: "u1",
    label: "1 · Getting started",
    page: 8,
    chunks: 34,
    children: [
      { id: "u1a", label: "Installing Python", page: 9, chunks: 11 },
      { id: "u1b", label: "The REPL", page: 14, chunks: 9 },
    ],
  },
  {
    id: "u2",
    label: "2 · Variables & types",
    page: 22,
    chunks: 61,
    children: [
      { id: "u2a", label: "Mutability", page: 28, chunks: 22 },
      { id: "u2b", label: "Sequences", page: 33, chunks: 19 },
    ],
  },
  {
    id: "u3",
    label: "3 · Control flow & iteration",
    page: 44,
    chunks: 88,
    children: [
      { id: "u3a", label: "range() semantics", page: 44, chunks: 12 },
      { id: "u3b", label: "The iteration protocol", page: 51, chunks: 27 },
      { id: "u3c", label: "Comprehensions", page: 58, chunks: 21 },
    ],
  },
  { id: "u4", label: "4 · Functions & scope", page: 70, chunks: 74 },
  { id: "u5", label: "5 · Classes", page: 98, chunks: 92 },
  { id: "u6", label: "6 · Files & context managers", page: 128, chunks: 63 },
];

export interface ChunkRow {
  id: string;
  page: number;
  tokens: number;
  score: number;
  text: string;
  retrieved: boolean;
}

export const retrievedChunks: ChunkRow[] = [
  {
    id: "chunk_0121",
    page: 51,
    tokens: 486,
    score: 0.91,
    retrieved: true,
    text: "An iterable is any object defining __iter__ which returns an iterator object. The for statement calls iter() on the expression…",
  },
  {
    id: "chunk_0182",
    page: 74,
    tokens: 512,
    score: 0.94,
    retrieved: true,
    text: "Default parameter values are evaluated exactly once, when the def statement is executed, not on each call…",
  },
  {
    id: "chunk_0183",
    page: 75,
    tokens: 478,
    score: 0.88,
    retrieved: true,
    text: "This is why appending to a default list argument produces surprising results across calls…",
  },
  {
    id: "chunk_0264",
    page: 102,
    tokens: 501,
    score: 0.9,
    retrieved: true,
    text: "Attribute lookup first checks the instance dictionary, then the class, then each base class in MRO order…",
  },
  {
    id: "chunk_0301",
    page: 118,
    tokens: 462,
    score: 0.72,
    retrieved: false,
    text: "len(obj) is equivalent to obj.__len__() for any sized container…",
  },
  {
    id: "chunk_0341",
    page: 131,
    tokens: 495,
    score: 0.68,
    retrieved: false,
    text: "The with statement wraps execution in a context manager that closes the file deterministically…",
  },
];

export const notifications: AppNotification[] = [
  {
    id: "n1",
    kind: "review",
    title: "3 outputs need your review",
    detail: "Question Bank run gen-1042 · Python Course",
    time: "8m",
    unread: true,
    roles: ["reviewer", "admin"],
  },
  {
    id: "n2",
    kind: "validation",
    title: "Validation warning",
    detail: "out-9009 is a near-duplicate of out-8974 (0.91)",
    time: "1h",
    unread: true,
    roles: ["reviewer", "admin"],
  },
  {
    id: "n3",
    kind: "grounding",
    title: "Grounding failed",
    detail: "Mentor note out-9007 fell to 64% support",
    time: "2h",
    unread: true,
    roles: ["reviewer", "admin"],
  },
  {
    id: "n4",
    kind: "done",
    title: "Generation finished",
    detail: "Flashcards · 40 cards · Linear Algebra deck",
    time: "Yesterday",
    unread: false,
    roles: ["student", "reviewer", "admin"],
  },
  {
    id: "n5",
    kind: "export",
    title: "Export ready",
    detail: "python-core-questions.pdf · 24 approved items",
    time: "Yesterday",
    unread: false,
    roles: ["student", "reviewer", "admin"],
  },
  {
    id: "s1",
    kind: "done",
    title: "Your question was approved",
    detail: "out-8974 · reviewed by Name 3 · Python Course",
    time: "12m",
    unread: true,
    roles: ["student"],
  },
  {
    id: "s2",
    kind: "grounding",
    title: "One of your items was rejected",
    detail: "out-9007 · grounding fell to 64% · regenerate to fix",
    time: "3h",
    unread: true,
    roles: ["student"],
  },
  {
    id: "s3",
    kind: "review",
    title: "Your run is with a reviewer",
    detail: "gen-1042 · 6 items submitted for review",
    time: "5h",
    unread: false,
    roles: ["student"],
  },
  {
    id: "a1",
    kind: "validation",
    title: "Reviewer queue is growing",
    detail: "12 items pending across 3 workspaces",
    time: "30m",
    unread: true,
    roles: ["admin"],
  },
];

export interface ExportRecord {
  id: string;
  name: string;
  format: "PDF" | "JSON" | "CSV" | "Markdown";
  items: number;
  workspace: string;
  time: string;
}

export const exportsList: ExportRecord[] = [
  {
    id: "e1",
    name: "python-core-questions",
    format: "PDF",
    items: 24,
    workspace: "Python Course",
    time: "Yesterday 18:02",
  },
  {
    id: "e2",
    name: "linear-algebra-deck",
    format: "CSV",
    items: 40,
    workspace: "Python Course",
    time: "Yesterday 17:50",
  },
  {
    id: "e3",
    name: "os-scheduling-plan",
    format: "Markdown",
    items: 1,
    workspace: "Operating Systems",
    time: "2 days ago",
  },
  {
    id: "e4",
    name: "question-bank-export",
    format: "JSON",
    items: 118,
    workspace: "Python Course",
    time: "Last week",
  },
];

export const ragStages: RagStage[] = [
  { key: "upload", label: "Upload", detail: "5 files · 21.1 MB" },
  { key: "parsing", label: "Parsing", detail: "353 pages extracted, headers stripped" },
  { key: "chunking", label: "Chunking", detail: "990 chunks · 512 tokens · 64 overlap" },
  { key: "embedding", label: "Embedding", detail: "990 / 990 vectors written" },
  { key: "retrieval", label: "Retrieval", detail: "top-k 8 · hybrid BM25 + dense" },
  { key: "grounding", label: "Grounding", detail: "every claim mapped to a chunk" },
  { key: "generation", label: "Generation", detail: "Question Bank · Gemini 2.5 Flash" },
  { key: "validation", label: "Validation", detail: "schema · support · duplicates" },
  { key: "review", label: "Review", detail: "3 items awaiting a human" },
  { key: "export", label: "Export", detail: "JSON · CSV · Markdown · PDF" },
];

export const futureFeatures = [
  { label: "Voice interaction", note: "Talk to the mentor agent" },
  { label: "Image understanding", note: "Diagrams and figures as sources" },
  { label: "Handwritten notes", note: "OCR upload for scanned pages" },
  { label: "PDF annotation", note: "Highlight straight on the source" },
  { label: "Collaborative review", note: "Assign reviewers, threaded notes" },
  { label: "Team workspaces", note: "Shared libraries and roles" },
  { label: "Adaptive learning", note: "Difficulty tuned per learner" },
  { label: "Agent marketplace", note: "Install community agents" },
];

export const promptTemplates = [
  {
    label: "Mid-term question bank",
    agent: "Question Bank",
    text: "Generate 20 intermediate MCQs covering the whole chapter, balanced across Bloom levels.",
  },
  {
    label: "Explain like I'm new",
    agent: "Concept Explanation",
    text: "Explain this topic from first principles with one analogy and two worked examples.",
  },
  {
    label: "Two-week cram plan",
    agent: "Study Plan",
    text: "Build a two-week plan at 10 hours per week weighted toward my weakest topics.",
  },
  {
    label: "Timed mock exam",
    agent: "Test Help",
    text: "Create a 45-minute mock exam, mixed format, hints hidden until submission.",
  },
];
