import type {
  ActivityPoint,
  Agent,
  DistributionBucket,
  TopicCoverage,
  DocItem,
  GeneratedQuestion,
  HistoryItem,
  PipelineStep,
  WsFlashcard,
} from "@/types/domain";
import type { AnalyticsSummary } from "@/types/api/analytics.contracts";

export const documents: DocItem[] = [
  {
    id: "doc-1",
    title: "Introduction to Python Programming",
    kind: "PDF",
    size: "4.2 MB",
    pages: 148,
    chunks: 412,
    uploaded: "2026-07-21",
    status: "Indexed",
    topics: ["Variables", "Loops", "Functions", "Classes", "Files"],
    coverage: 83,
  },
  {
    id: "doc-2",
    title: "Linear Algebra — Lecture Deck 04",
    kind: "PPTX",
    size: "12.8 MB",
    pages: 62,
    chunks: 178,
    uploaded: "2026-07-19",
    status: "Indexed",
    topics: ["Vectors", "Matrices", "Eigenvalues", "Transformations"],
    coverage: 91,
  },
  {
    id: "doc-3",
    title: "Cell Biology — Chapter 7 Notes",
    kind: "DOCX",
    size: "1.1 MB",
    pages: 34,
    chunks: 96,
    uploaded: "2026-07-17",
    status: "Embedding",
    topics: ["Mitosis", "Organelles", "Membranes"],
    coverage: 44,
  },
  {
    id: "doc-4",
    title: "Operating Systems — Scheduling",
    kind: "PDF",
    size: "2.7 MB",
    pages: 88,
    chunks: 240,
    uploaded: "2026-07-12",
    status: "Indexed",
    topics: ["Processes", "Threads", "Scheduling", "Deadlocks"],
    coverage: 76,
  },
  {
    id: "doc-5",
    title: "Macroeconomics Seminar Transcript",
    kind: "TXT",
    size: "312 KB",
    pages: 21,
    chunks: 64,
    uploaded: "2026-07-08",
    status: "Indexed",
    topics: ["Inflation", "GDP", "Monetary Policy"],
    coverage: 58,
  },
];

export const questions: GeneratedQuestion[] = [
  {
    id: "q-1",
    prompt:
      "Which statement best describes what happens when a mutable default argument is used in a Python function definition?",
    type: "MCQ",
    difficulty: "Advanced",
    options: [
      "A fresh object is created on every call",
      "The same object persists across calls and accumulates state",
      "Python raises a SyntaxError at definition time",
      "The argument is silently converted to a tuple",
    ],
    answer: "The same object persists across calls and accumulates state",
    rationale:
      "Default arguments are evaluated once at function definition time, so a mutable default is shared between every invocation of the function.",
    bloom: "Analysis",
    quality: 9.6,
    grounded: 100,
    estMinutes: 2,
    review: "Pending",
    citations: [
      {
        doc: "Introduction to Python Programming",
        page: 74,
        chunk: "chunk_0182",
        snippet:
          "Default parameter values are evaluated exactly once, when the def statement is executed...",
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
  },
  {
    id: "q-2",
    prompt: "A `for` loop in Python can iterate over any object that implements `__iter__`.",
    type: "True/False",
    difficulty: "Intermediate",
    answer: "True",
    rationale:
      "The iteration protocol requires an object to return an iterator from __iter__; any such object is iterable by a for loop.",
    bloom: "Understanding",
    quality: 9.1,
    grounded: 100,
    estMinutes: 1,
    review: "Approved",
    citations: [
      {
        doc: "Introduction to Python Programming",
        page: 51,
        chunk: "chunk_0121",
        snippet: "An iterable is any object defining __iter__ which returns an iterator object.",
        score: 0.91,
      },
    ],
  },
  {
    id: "q-3",
    prompt:
      "Explain, in two or three sentences, the difference between a class attribute and an instance attribute.",
    type: "Short Answer",
    difficulty: "Intermediate",
    answer:
      "A class attribute is shared by every instance and stored on the class object, while an instance attribute is stored per object in its __dict__ and shadows the class attribute when set.",
    rationale:
      "The source chapter contrasts the two lookup paths and demonstrates shadowing with a counter example.",
    bloom: "Understanding",
    quality: 8.8,
    grounded: 96,
    estMinutes: 3,
    review: "Needs Edit",
    citations: [
      {
        doc: "Introduction to Python Programming",
        page: 102,
        chunk: "chunk_0264",
        snippet: "Attribute lookup first checks the instance dictionary, then the class...",
        score: 0.9,
      },
    ],
  },
  {
    id: "q-4",
    prompt: "Which construct guarantees a file handle is closed even if an exception is raised?",
    type: "MCQ",
    difficulty: "Beginner",
    options: ["try/except", "with open(...) as f", "del f", "f.flush()"],
    answer: "with open(...) as f",
    rationale:
      "The context manager protocol calls __exit__ on the file object during unwinding, closing the handle deterministically.",
    bloom: "Knowledge",
    quality: 9.4,
    grounded: 100,
    estMinutes: 1,
    review: "Approved",
    citations: [
      {
        doc: "Introduction to Python Programming",
        page: 131,
        chunk: "chunk_0341",
        snippet: "The with statement wraps execution in a context manager that closes the file.",
        score: 0.96,
      },
    ],
  },
];

export const bloomDistribution: DistributionBucket[] = [
  { name: "Knowledge", value: 22 },
  { name: "Understanding", value: 28 },
  { name: "Application", value: 21 },
  { name: "Analysis", value: 16 },
  { name: "Evaluation", value: 8 },
  { name: "Creation", value: 5 },
];

export const typeDistribution: DistributionBucket[] = [
  { name: "MCQ", value: 54 },
  { name: "True/False", value: 26 },
  { name: "Short Answer", value: 20 },
];

export const activitySeries: ActivityPoint[] = [
  { week: "W1", questions: 42, flashcards: 60, quality: 8.4 },
  { week: "W2", questions: 68, flashcards: 92, quality: 8.7 },
  { week: "W3", questions: 55, flashcards: 74, quality: 9.0 },
  { week: "W4", questions: 91, flashcards: 130, quality: 9.2 },
  { week: "W5", questions: 120, flashcards: 148, quality: 9.4 },
  { week: "W6", questions: 104, flashcards: 162, quality: 9.5 },
];

export const topicCoverage: TopicCoverage[] = [
  { topic: "Variables", covered: true, pct: 100 },
  { topic: "Loops", covered: true, pct: 96 },
  { topic: "Functions", covered: true, pct: 92 },
  { topic: "Classes", covered: false, pct: 38 },
  { topic: "Files", covered: false, pct: 24 },
];

/** Demo figures for the analytics stat cards (mock mode only). */
export const analyticsSummary: AnalyticsSummary = {
  questions: 480,
  flashcards: 666,
  studyPlans: 18,
  grounding: 98.4,
  quality: 9.3,
  reviewCompletion: 86,
};

export const history: HistoryItem[] = [
  {
    id: "gen-1042",
    date: "2026-07-29 09:12",
    agent: "Question Bank",
    doc: "Introduction to Python Programming",
    status: "Completed",
    quality: 9.6,
    review: "Pending",
    items: 24,
  },
  {
    id: "gen-1041",
    date: "2026-07-28 17:44",
    agent: "Flashcards",
    doc: "Linear Algebra — Lecture Deck 04",
    status: "Completed",
    quality: 9.2,
    review: "Approved",
    items: 40,
  },
  {
    id: "gen-1040",
    date: "2026-07-28 11:03",
    agent: "Study Plan",
    doc: "Operating Systems — Scheduling",
    status: "Completed",
    quality: 8.9,
    review: "Approved",
    items: 1,
  },
  {
    id: "gen-1039",
    date: "2026-07-27 20:31",
    agent: "Revision Assistant",
    doc: "Cell Biology — Chapter 7 Notes",
    status: "Completed",
    quality: 8.4,
    review: "Needs Edit",
    items: 6,
  },
  {
    id: "gen-1038",
    date: "2026-07-27 08:15",
    agent: "Mentor",
    doc: "Macroeconomics Seminar Transcript",
    status: "Completed",
    quality: 9.0,
    review: "Approved",
    items: 12,
  },
  {
    id: "gen-1037",
    date: "2026-07-26 14:50",
    agent: "Concept Explanation",
    doc: "Introduction to Python Programming",
    status: "Failed",
    quality: 0,
    review: "Rejected",
    items: 0,
  },
];

export const agents: Agent[] = [
  {
    slug: "mentor",
    name: "Mentor Agent",
    tagline: "Adaptive, cited explanations that meet the learner where they are.",
    bullets: [
      "Explains concepts conversationally",
      "Adapts to learner difficulty",
      "Grounded references on every claim",
      "Inline supporting citations",
    ],
    icon: "compass",
    runs: 218,
  },
  {
    slug: "concept",
    name: "Concept Explanation Agent",
    tagline: "Structured breakdowns: summary, key points, examples, analogies.",
    bullets: ["Structured explanations", "Summaries", "Worked examples", "Analogies & key points"],
    icon: "lightbulb",
    runs: 164,
  },
  {
    slug: "question-bank",
    name: "Question Bank Agent",
    tagline: "MCQ, True/False and Short Answer banks with rationale and citations.",
    bullets: [
      "Three question types",
      "Three difficulty tiers",
      "Answer key + rationale",
      "Human review required",
    ],
    icon: "list-checks",
    runs: 402,
  },
  {
    slug: "test-help",
    name: "Test Help Agent",
    tagline: "Practice quizzes and personalised assessments before the exam.",
    bullets: ["Practice quizzes", "Focused revision sets", "Personalised assessments"],
    icon: "target",
    runs: 131,
  },
  {
    slug: "flashcards",
    name: "Flashcards Agent",
    tagline: "Term → definition and question → answer cards, count configurable.",
    bullets: ["Front / back cards", "Term → definition", "Question → answer", "Configurable count"],
    icon: "layers",
    runs: 287,
  },
  {
    slug: "study-plan",
    name: "Study Plan Agent",
    tagline: "Schedules built around your goals, time budget and difficulty.",
    bullets: ["Goal-driven schedules", "Time-budget aware", "Difficulty balanced"],
    icon: "calendar",
    runs: 96,
  },
  {
    slug: "revision",
    name: "Revision Assistant",
    tagline: "Last-minute sheets covering key topics and weak concepts.",
    bullets: ["Revision sheets", "Key topic recall", "Weak concept targeting"],
    icon: "sparkle",
    runs: 143,
  },
] as const;

export const pipelineSteps: PipelineStep[] = [
  { key: "upload", label: "Upload", detail: "5 files · 21.1 MB" },
  { key: "parsing", label: "Parsing", detail: "353 pages extracted" },
  { key: "chunking", label: "Chunking", detail: "990 chunks · 512 tokens" },
  { key: "embedding", label: "Embedding", detail: "gemini-embedding-001" },
  { key: "retrieval", label: "Retrieval", detail: "top-k 8 · hybrid" },
  { key: "generation", label: "AI Generation", detail: "Question Bank Agent" },
  { key: "validation", label: "Validation", detail: "schema + support checks" },
  { key: "review", label: "Human Review", detail: "3 items awaiting" },
  { key: "export", label: "Export", detail: "PDF · MD · JSON · CSV" },
];

export const flashcards: WsFlashcard[] = [
  { front: "Immutable sequence type", back: "Tuple — fixed-length, hashable if elements are." },
  { front: "What does `len()` call under the hood?", back: "The object's `__len__` method." },
  { front: "List comprehension", back: "Concise syntax building a list from an iterable." },
  { front: "Duck typing", back: "Behaviour determined by methods present, not declared type." },
];
