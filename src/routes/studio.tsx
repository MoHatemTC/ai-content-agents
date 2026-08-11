import { useEffect, useMemo, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { motion } from "motion/react";
import {
  BookOpen,
  Brain,
  Calendar,
  CheckCircle2,
  ClipboardList,
  FileText,
  GraduationCap,
  Layers,
  Lightbulb,
  Loader2,
  MessagesSquare,
  Send,
  Sparkles,
  Target,
  Timer,
} from "lucide-react";
import { AppShell } from "@/components/app/AppShell";
import { RoleGate } from "@/components/app/RoleGate";
import { NoActiveWorkspace } from "@/components/app/AsyncState";
import { InteractiveQuiz } from "@/components/app/InteractiveQuiz";
import { FlashcardDeck, type Flashcard } from "@/components/app/FlashcardDeck";
import { ModelSelector, type ModelId } from "@/components/app/ModelSelector";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { useNotify } from "@/contexts/NotificationContext";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { GenerationService } from "@/services/GenerationService";
import { ChatService } from "@/services/ChatService";
import { HistoryService, type PersistGenerationMeta } from "@/services/HistoryService";
import { FavoriteService } from "@/services/FavoriteService";
import type { WsDoc } from "@/types/domain";
import type { ChatCitation } from "@/types/domain";
import type { GeneratedQuestion } from "@/types/domain";
import type { WeakTopic } from "@/types/domain";

export const Route = createFileRoute("/studio")({
  head: () => ({
    meta: [
      { title: "AI Studio — Sensei" },
      {
        name: "description",
        content:
          "Generate grounded question banks, flashcards, study plans, exams and mentor conversations.",
      },
      { property: "og:title", content: "AI Studio — Sensei" },
      {
        property: "og:description",
        content: "Seven purpose-built agents, one grounded workspace.",
      },
    ],
  }),
  component: () => (
    <RoleGate allow={["student", "reviewer", "admin"]}>
      <StudioPage />
    </RoleGate>
  ),
});

type TabId = "questions" | "flashcards" | "test" | "plan" | "revision" | "mentor" | "concept";

const TABS: {
  id: TabId;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  kind: "gen" | "chat";
}[] = [
  { id: "questions", label: "Question Bank", icon: ClipboardList, kind: "gen" },
  { id: "test", label: "Test Help", icon: GraduationCap, kind: "gen" },
  { id: "flashcards", label: "Flashcards", icon: Layers, kind: "gen" },
  { id: "plan", label: "Study Plan", icon: Calendar, kind: "gen" },
  { id: "revision", label: "Revision", icon: Target, kind: "gen" },
  { id: "mentor", label: "Mentor", icon: MessagesSquare, kind: "chat" },
  { id: "concept", label: "Concept Explanation", icon: Lightbulb, kind: "chat" },
];

function StudioPage() {
  const { active: workspace, data } = useWorkspace();
  const [tab, setTab] = useState<TabId>("questions");
  const [model, setModel] = useState<ModelId>("gemini");
  const docs = data.docs;
  const [doc, setDoc] = useState<string>(docs[0]?.id ?? "");

  // The picker always follows the active workspace — never another workspace's material.
  const workspaceId = workspace ? workspace.id : null;
  useEffect(() => {
    setDoc(docs[0]?.id ?? "");
  }, [workspaceId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (doc && !docs.some((d) => d.id === doc)) setDoc(docs[0]?.id ?? "");
  }, [docs, doc]);

  const active = TABS.find((t) => t.id === tab)!;

  return (
    <AppShell
      title={workspace ? `AI Studio · ${workspace.name}` : "AI Studio"}
      description="Grounded to this workspace only — its documents, its chunks, its history."
      actions={
        <div className="hidden items-center gap-2 md:flex">
          <ModelSelector value={model} onChange={setModel} />
          <Select value={doc} onValueChange={setDoc} disabled={docs.length === 0}>
            <SelectTrigger className="h-9 min-w-52 gap-2">
              <FileText className="text-muted-foreground size-3.5" />
              <SelectValue placeholder="No documents in this workspace" />
            </SelectTrigger>
            <SelectContent>
              {docs.map((d) => (
                <SelectItem key={d.id} value={d.id}>
                  {d.title} · {d.chunks.length} chunks
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      }
    >
      {!workspace ? (
        <NoActiveWorkspace />
      ) : (
        <>
          {/* Tab bar */}
          <div className="mb-6 flex gap-1.5 overflow-x-auto">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={cn(
                  "relative flex shrink-0 items-center gap-2 rounded-xl px-3.5 py-2 text-sm font-medium transition-colors",
                  tab === t.id ? "text-primary" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {tab === t.id && (
                  <motion.span
                    layoutId="studio-tab"
                    className="bg-primary/12 ring-primary/25 absolute inset-0 rounded-xl ring-1"
                  />
                )}
                <t.icon className="relative size-4" />
                <span className="relative">{t.label}</span>
                <span
                  className={cn(
                    "relative rounded px-1.5 py-0.5 text-[10px] font-semibold",
                    t.kind === "gen"
                      ? "bg-primary/10 text-primary"
                      : "bg-muted text-muted-foreground",
                  )}
                >
                  {t.kind === "gen" ? "Generator" : "Chat"}
                </span>
              </button>
            ))}
          </div>

          {tab === "questions" && <QuestionBankPanel model={model} doc={doc} />}
          {tab === "test" && <TestHelpPanel model={model} doc={doc} />}
          {tab === "flashcards" && <FlashcardsPanel model={model} doc={doc} />}
          {tab === "plan" && <StudyPlanPanel model={model} doc={doc} />}
          {tab === "revision" && <RevisionPanel model={model} doc={doc} />}
          {tab === "mentor" && (
            <ChatPanel
              agent={active}
              model={model}
              doc={doc}
              greeting="I'm your grounded mentor. Ask me anything about the selected document — I'll only speak from what's cited."
            />
          )}
          {tab === "concept" && (
            <ChatPanel
              agent={active}
              model={model}
              doc={doc}
              greeting="Ask me to explain any concept from your material. I'll break it down with citations."
            />
          )}
        </>
      )}
    </AppShell>
  );
}

/* ---------------- Workspace helpers ---------------- */

function useDocTitle(doc: string) {
  const { data } = useWorkspace();
  return data.docs.find((d) => d.id === doc)?.title ?? "this workspace";
}

function useGenerationLog() {
  const { addHistory } = useWorkspace();
  return (
    agent: string,
    docTitle: string,
    items: number,
    meta?: PersistGenerationMeta & { quality?: number },
  ) => {
    const generationId = meta?.kind ? crypto.randomUUID() : undefined;
    const row = HistoryService.buildRow({
      agent,
      doc: docTitle,
      items,
      quality: meta?.quality,
      generationId,
    });
    addHistory(row, meta ? { ...meta, generationId } : undefined);
    return row;
  };
}

/* ---------------- Question Bank ---------------- */

function QuestionBankPanel({ model, doc }: { model: ModelId; doc: string }) {
  const { active: workspace } = useWorkspace();
  const docTitle = useDocTitle(doc);
  const notify = useNotify();
  const log = useGenerationLog();
  const [type, setType] = useState("MCQ");
  const [difficulty, setDifficulty] = useState("Intermediate");
  const [count, setCount] = useState(5);
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<GeneratedQuestion[] | null>(null);

  if (!workspace) return null;

  const generate = async () => {
    setBusy(true);
    setResults(null);
    const res = await GenerationService.generateQuestions({
      workspaceId: workspace.id,
      documentId: doc,
      model,
      count,
      type,
      difficulty,
    });
    if (!res.success) {
      setBusy(false);
      notify.fromError(res.error, "Generation failed");
      return;
    }
    const out = res.data;
    setResults(out);
    setBusy(false);
    log("Question Bank", docTitle, out.length, {
      kind: "question_bank",
      model,
      title: docTitle,
      payload: { questions: out },
      documentIds: [doc].filter(Boolean),
    });
    notify.success(`Generated ${out.length} grounded questions from ${docTitle} with ${model}.`);
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
      <ControlsCard title="Question Bank controls" onGenerate={generate} busy={busy}>
        <SegmentedField
          label="Question type"
          value={type}
          onChange={setType}
          options={["MCQ", "True/False", "Short Answer"]}
        />
        <SegmentedField
          label="Difficulty"
          value={difficulty}
          onChange={setDifficulty}
          options={["Beginner", "Intermediate", "Advanced"]}
        />
        <SliderField
          label="Question count"
          value={count}
          onChange={setCount}
          min={3}
          max={12}
          step={1}
        />
        <DocLine doc={doc} />
      </ControlsCard>

      <div className="min-w-0">
        {busy && <SkeletonList />}
        {!busy && !results && (
          <EmptyState
            icon={ClipboardList}
            title="Ready to generate"
            body="Set your controls on the left, then click Generate to build an interactive quiz."
          />
        )}
        {!busy && results && <InteractiveQuiz questions={results} />}
      </div>
    </div>
  );
}

/* ---------------- Test Help ---------------- */

function TestHelpPanel({ model, doc }: { model: ModelId; doc: string }) {
  const { active: workspace } = useWorkspace();
  const docTitle = useDocTitle(doc);
  const notify = useNotify();
  const log = useGenerationLog();
  const [duration, setDuration] = useState(15);
  const [count, setCount] = useState(6);
  const [started, setStarted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [set, setSet] = useState<GeneratedQuestion[] | null>(null);

  if (!workspace) return null;

  const generate = async () => {
    setBusy(true);
    const res = await GenerationService.generateExam({
      workspaceId: workspace.id,
      documentId: doc,
      model,
      count,
      durationMinutes: duration,
    });
    if (!res.success) {
      setBusy(false);
      notify.fromError(res.error, "Generation failed");
      return;
    }
    const out = res.data;
    setSet(out);
    setBusy(false);
    setStarted(true);
    log("Test Help", docTitle, out.length, {
      kind: "test_help",
      model,
      title: docTitle,
      payload: { questions: out },
      documentIds: [doc].filter(Boolean),
    });
    notify.success(`Exam ready · ${duration} min · ${model}`);
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
      <ControlsCard title="Exam simulation controls" onGenerate={generate} busy={busy}>
        <SliderField
          label="Duration (min)"
          value={duration}
          onChange={setDuration}
          min={5}
          max={60}
          step={5}
        />
        <SliderField
          label="Question count"
          value={count}
          onChange={setCount}
          min={3}
          max={12}
          step={1}
        />
        <DocLine doc={doc} />
      </ControlsCard>

      <div className="min-w-0">
        {!started && !busy && (
          <EmptyState
            icon={GraduationCap}
            title="Exam simulation"
            body="Timed, cite-checked exam. Answer everything, then reveal explanations and sources."
          />
        )}
        {busy && <SkeletonList />}
        {started && set && (
          <>
            <div className="surface-card mb-4 flex items-center gap-3 p-4">
              <Timer className="text-primary size-5" />
              <p className="text-sm font-semibold">
                Exam mode · {duration} min · {set.length} questions
              </p>
              <span className="text-muted-foreground ml-auto text-xs">
                Answers reveal after each check
              </span>
            </div>
            <InteractiveQuiz questions={set} />
          </>
        )}
      </div>
    </div>
  );
}

/* ---------------- Flashcards ---------------- */

function FlashcardsPanel({ model, doc }: { model: ModelId; doc: string }) {
  const { active: workspace } = useWorkspace();
  const docTitle = useDocTitle(doc);
  const notify = useNotify();
  const log = useGenerationLog();
  const [topic, setTopic] = useState("All chapters");
  const [topics, setTopics] = useState<string[]>([]);
  const [format, setFormat] = useState<"term-definition" | "qa">("term-definition");
  const [count, setCount] = useState(6);
  const [busy, setBusy] = useState(false);
  const [deck, setDeck] = useState<Flashcard[] | null>(null);
  const [favs, setFavs] = useState<Set<string>>(new Set());

  // Hydrate favorites for the current deck from Supabase (front-keyed),
  // scoped to the active workspace so favorites don't leak across workspaces.
  useEffect(() => {
    if (!deck) return;
    void FavoriteService.favoritedSet(
      deck.map((c) => c.front),
      workspace?.id,
    ).then((res) => {
      if (res.success) setFavs(res.data);
    });
  }, [deck, workspace?.id]);

  const toggleFavorite = async (card: Flashcard) => {
    const wasFav = favs.has(card.front);
    setFavs((s) => {
      const n = new Set(s);
      if (wasFav) n.delete(card.front);
      else n.add(card.front);
      return n;
    });
    const res = await FavoriteService.toggleFavorite({
      front: card.front,
      back: card.back,
      topic: card.topic ?? null,
      format: card.format ?? null,
      sourceChunkId: card.citations?.[0]?.chunk ?? null,
      workspaceId: workspace?.id ?? null,
    });
    if (!res.success) {
      setFavs((s) => {
        const n = new Set(s);
        if (wasFav) n.add(card.front);
        else n.delete(card.front);
        return n;
      });
      notify.fromError(res.error, "Could not update favorite");
    }
  };

  // Keep the topic selector in sync with the PDF: topics are extracted from
  // the indexed document chunks, exactly like the Streamlit UI does. If the
  // extraction returns nothing we fall back to "All chapters".
  useEffect(() => {
    let cancelled = false;
    if (!workspace || !doc) {
      setTopics([]);
      setTopic("All chapters");
      return;
    }
    setTopics([]);
    setTopic("All chapters");
    GenerationService.flashcardTopics({
      workspaceId: workspace.id,
      documentId: doc,
      model,
    }).then((res) => {
      if (cancelled) return;
      if (res.success) setTopics(res.data);
    });
    return () => {
      cancelled = true;
    };
  }, [workspace?.id, doc, model]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!workspace) return null;

  const topicOptions = ["All chapters", ...topics];

  const generate = async () => {
    setBusy(true);
    setDeck(null);
    const res = await GenerationService.generateFlashcards({
      workspaceId: workspace.id,
      documentId: doc,
      model,
      count,
      topic,
      format,
    });
    if (!res.success) {
      setBusy(false);
      notify.fromError(res.error, "Generation failed");
      return;
    }
    const cards = res.data;
    setDeck(cards);
    setBusy(false);
    log("Flashcards", docTitle, cards.length, {
      kind: "flashcards",
      model,
      title: docTitle,
      payload: { flashcards: cards },
      documentIds: [doc].filter(Boolean),
    });
    notify.success(`${cards.length} flashcards generated from ${docTitle} with ${model}.`);
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
      <ControlsCard title="Flashcards controls" onGenerate={generate} busy={busy}>
        <SegmentedField
          label="Card format"
          value={format}
          onChange={(v) => setFormat(v as "term-definition" | "qa")}
          options={["term-definition", "qa"]}
          labels={{ "term-definition": "Term · Definition", qa: "Question and Answer" }}
        />
        <SegmentedField label="Topic" value={topic} onChange={setTopic} options={topicOptions} />
        <SliderField
          label="Card count"
          value={count}
          onChange={setCount}
          min={4}
          max={12}
          step={1}
        />
        <DocLine doc={doc} />
      </ControlsCard>

      <div className="min-w-0">
        {busy && <SkeletonList />}
        {!busy && !deck && (
          <EmptyState
            icon={Layers}
            title="Animated flashcard deck"
            body="Flip, shuffle, favorite, mark difficult. Study or quiz mode."
          />
        )}
        {!busy && deck && (
          <div className="surface-card p-6">
            <FlashcardDeck cards={deck} favorites={favs} onToggleFavorite={toggleFavorite} />
          </div>
        )}
      </div>
    </div>
  );
}

/* ---------------- Study Plan ---------------- */

function StudyPlanPanel({ model, doc }: { model: ModelId; doc: string }) {
  const { active: workspace } = useWorkspace();
  const docTitle = useDocTitle(doc);
  const notify = useNotify();
  const log = useGenerationLog();
  const [days, setDays] = useState(7);
  const [hoursPerDay, setHoursPerDay] = useState(2);
  const [busy, setBusy] = useState(false);
  const [plan, setPlan] = useState<{ day: number; topics: string[]; hours: number }[] | null>(null);

  if (!workspace) return null;

  const generate = async () => {
    setBusy(true);
    const res = await GenerationService.generateStudyPlan({
      workspaceId: workspace.id,
      documentId: doc,
      model,
      days,
      hoursPerDay,
    });
    if (!res.success) {
      setBusy(false);
      notify.fromError(res.error, "Generation failed");
      return;
    }
    const out = res.data;
    setPlan(out);
    setBusy(false);
    log("Study Plan", docTitle, days, {
      kind: "study_plan",
      model,
      title: docTitle,
      payload: { days: out },
      documentIds: [doc].filter(Boolean),
    });
    notify.success(`${days}-day study plan generated with ${model}.`);
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
      <ControlsCard title="Study plan controls" onGenerate={generate} busy={busy}>
        <SliderField label="Days" value={days} onChange={setDays} min={1} max={14} step={1} />
        <SliderField
          label="Hours per day"
          value={hoursPerDay}
          onChange={setHoursPerDay}
          min={1}
          max={6}
          step={1}
        />
        <DocLine doc={doc} />
      </ControlsCard>

      <div className="min-w-0">
        {busy && <SkeletonList />}
        {!busy && !plan && (
          <EmptyState
            icon={Calendar}
            title="Personalised study plan"
            body="Timeline, calendar and checklist tailored to your available time."
          />
        )}
        {!busy && plan && (
          <div className="space-y-3">
            {plan.map((d) => (
              <motion.div
                key={d.day}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: d.day * 0.03 }}
                className="surface-card flex flex-wrap items-center gap-4 p-4"
              >
                <span className="bg-primary text-primary-foreground flex size-10 shrink-0 items-center justify-center rounded-xl font-bold">
                  {d.day}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold">Day {d.day}</p>
                  <p className="text-muted-foreground text-xs">{d.topics.join(" · ")}</p>
                </div>
                <span className="text-muted-foreground inline-flex items-center gap-1 text-xs">
                  <BookOpen className="size-3.5" /> {d.hours}h
                </span>
                <input type="checkbox" className="size-4 accent-current" />
              </motion.div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* ---------------- Revision ---------------- */

function RevisionPanel({ model, doc }: { model: ModelId; doc: string }) {
  const { active: workspace } = useWorkspace();
  const docTitle = useDocTitle(doc);
  const notify = useNotify();
  const log = useGenerationLog();
  const [busy, setBusy] = useState(false);
  const [items, setItems] = useState<WeakTopic[] | null>(null);

  if (!workspace) return null;

  const generate = async () => {
    setBusy(true);
    const res = await GenerationService.generateRevisionSheet({
      workspaceId: workspace.id,
      documentId: doc,
      model,
    });
    if (!res.success) {
      setBusy(false);
      notify.fromError(res.error, "Generation failed");
      return;
    }
    const out = res.data;
    setItems(out);
    setBusy(false);
    log("Revision", docTitle, out.length, {
      kind: "revision_sheet",
      model,
      title: docTitle,
      payload: { weakTopics: out },
      documentIds: [doc].filter(Boolean),
    });
    notify.success(`Weak topics analysed with ${model}.`);
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
      <ControlsCard
        title="Revision"
        onGenerate={generate}
        busy={busy}
        generateLabel="Analyse weak topics"
      >
        <p className="text-muted-foreground text-xs">
          Based on your recent quiz results and grounded feedback, we highlight what to revisit
          before your exam.
        </p>
        <DocLine doc={doc} />
      </ControlsCard>

      <div className="min-w-0">
        {busy && <SkeletonList />}
        {!busy && !items && (
          <EmptyState
            icon={Target}
            title="Weak topic detection"
            body="Turn your recent history into a targeted revision checklist."
          />
        )}
        {!busy && items && (
          <div className="space-y-3">
            {items.map((it, i) => (
              <motion.div
                key={it.topic}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.05 }}
                className="surface-card p-4"
              >
                <div className="flex flex-wrap items-center gap-4">
                  <Brain className="text-primary size-5 shrink-0" />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-semibold">{it.topic}</p>
                      {it.difficulty && (
                        <span className="border-border bg-muted/40 text-muted-foreground rounded-full border px-2 py-0.5 text-[10px] font-semibold capitalize">
                          {it.difficulty}
                        </span>
                      )}
                      {it.nextRevisionDate && (
                        <span className="text-muted-foreground text-[11px]">
                          Review by {it.nextRevisionDate}
                        </span>
                      )}
                    </div>
                    {it.description && (
                      <p className="text-muted-foreground mt-1 text-xs leading-relaxed">
                        {it.description}
                      </p>
                    )}
                    {it.confidencePrompt && (
                      <p className="border-primary/30 bg-primary/5 mt-2 rounded-lg border-l-2 pl-2 text-xs italic">
                        Self-check: {it.confidencePrompt}
                      </p>
                    )}
                  </div>
                  <div className="w-28">
                    <div className="bg-muted h-1.5 overflow-hidden rounded-full">
                      <div
                        className={cn(
                          "h-full",
                          it.strength < 50
                            ? "bg-destructive"
                            : it.strength < 70
                              ? "bg-warning"
                              : "bg-success",
                        )}
                        style={{ width: `${it.strength}%` }}
                      />
                    </div>
                    <p className="text-muted-foreground mt-1 text-right text-[11px]">
                      {it.strength}% retained
                    </p>
                  </div>
                  <CheckCircle2 className="text-muted-foreground hidden size-4 sm:block" />
                </div>
              </motion.div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* ---------------- Chat (Mentor / Concept) ---------------- */

function ChatPanel({
  agent,
  greeting,
  doc,
  model,
}: {
  agent: { id?: string; label: string; icon: React.ComponentType<{ className?: string }> };
  greeting: string;
  doc: string;
  model: ModelId;
}) {
  const { active: workspace, data, addChat, appendChatMessage } = useWorkspace();
  const docTitle = useDocTitle(doc);
  const notify = useNotify();
  const [chatId, setChatId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);

  // A new session always inherits the current workspace: switching workspace starts a fresh thread.
  const workspaceId = workspace ? workspace.id : null;
  useEffect(() => {
    setChatId(null);
  }, [workspaceId, agent.label]);

  if (!workspace) return null;

  const stored = data.chats.find((c) => c.id === chatId);
  const messages = stored?.messages ?? [
    { id: "greeting", role: "assistant" as const, text: greeting, time: "" },
  ];

  const now = () => new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  const send = async () => {
    if (!input.trim() || busy) return;
    const q = input.trim();
    const userMsg = {
      id: `m-${Date.now().toString(36)}`,
      role: "user" as const,
      text: q,
      time: now(),
    };
    let id = chatId;

    if (!id) {
      const created = await ChatService.createChat({
        workspaceId: workspace.id,
        kind: agent.id === "concept" ? "concept" : "mentor",
        title: q.slice(0, 48),
        model,
      });
      if (!created.success) {
        setBusy(false);
        notify.fromError(created.error, "Could not start chat");
        return;
      }
      id = created.data.chatId;
      addChat({
        id,
        title: q.slice(0, 48),
        agent: agent.label,
        model,
        date: new Date().toISOString().slice(0, 16).replace("T", " "),
        messages: [{ id: "greeting", role: "assistant", text: greeting, time: now() }, userMsg],
      });
      setChatId(id);
    } else {
      appendChatMessage(id, userMsg);
    }

    setInput("");
    setBusy(true);
    const target = id;
    const res = await ChatService.send({
      kind: agent.id === "concept" ? "concept" : "mentor",
      workspaceId: workspace.id,
      chatId: target,
      message: q,
      model,
      documentIds: [doc].filter(Boolean),
      context: { docTitle, workspaceName: workspace.name },
    });
    if (!res.success) {
      setBusy(false);
      notify.fromError(res.error, "The agent could not reply");
      return;
    }
    const reply = res.data;
    appendChatMessage(target, reply);
    setBusy(false);
  };

  return (
    <div className="surface-card flex h-[calc(100vh-16rem)] flex-col overflow-hidden">
      <div className="border-border flex items-center gap-2 border-b px-4 py-3">
        <span className="bg-primary/12 text-primary flex size-8 items-center justify-center rounded-lg">
          <agent.icon className="size-4" />
        </span>
        <div>
          <p className="text-sm font-semibold">{agent.label}</p>
          <p className="text-muted-foreground text-[11px]">
            {workspace.name} · grounded to {docTitle}
          </p>
        </div>
      </div>
      <div className="mesh-bg flex-1 space-y-3 overflow-y-auto p-4">
        {messages.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="flex justify-end">
              <div className="bg-primary text-primary-foreground max-w-[85%] rounded-2xl rounded-br-md px-4 py-2.5 text-sm">
                {m.text}
              </div>
            </div>
          ) : (
            <div key={i} className="surface-card max-w-[85%] p-3 text-sm">
              <div className="whitespace-pre-wrap">{m.text}</div>
              {m.citations && m.citations.length > 0 && (
                <MessageReferences citations={m.citations} />
              )}
            </div>
          ),
        )}
        {busy && (
          <div className="text-muted-foreground inline-flex items-center gap-2 text-xs">
            <Loader2 className="size-3.5 animate-spin" /> Thinking with citations…
          </div>
        )}
      </div>
      <div className="border-border border-t p-3">
        <div className="border-border focus-within:border-primary/50 flex items-center gap-1 rounded-xl border p-1.5 transition-colors">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            placeholder={`Ask ${agent.label.toLowerCase()}…`}
            className="flex-1 bg-transparent px-2 py-1.5 text-sm outline-none"
          />
          <Button size="icon" onClick={send} disabled={busy || !input.trim()}>
            {busy ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
          </Button>
        </div>
      </div>
    </div>
  );
}

/* ---------------- Shared UI ---------------- */

function MessageReferences({ citations }: { citations: ChatCitation[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2.5">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "border-border text-muted-foreground inline-flex items-center gap-1.5 rounded-lg border px-2 py-1 text-[11px] font-medium transition-colors hover:border-primary/40 hover:text-primary",
          open && "border-primary/40 text-primary",
        )}
      >
        <BookOpen className="size-3.5" />
        {open ? "Hide references" : `Show references (${citations.length})`}
      </button>
      {open && (
        <div className="border-border mt-2 space-y-2 border-l-2 pl-3">
          {citations.map((c, i) => (
            <div key={`${c.docId}-${i}`} className="text-xs leading-relaxed">
              <p className="text-primary font-semibold">
                {c.docTitle}
                {c.page ? ` · p.${c.page}` : ""}
              </p>
              <p className="text-muted-foreground line-clamp-3">{c.snippet}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ControlsCard({
  title,
  children,
  onGenerate,
  busy,
  generateLabel = "Generate",
}: {
  title: string;
  children: React.ReactNode;
  onGenerate: () => void;
  busy: boolean;
  generateLabel?: string;
}) {
  return (
    <aside className="surface-card sticky top-24 h-max p-5">
      <p className="text-muted-foreground text-[11px] font-semibold tracking-widest uppercase">
        {title}
      </p>
      <div className="mt-4 space-y-5">{children}</div>
      <Button className="mt-6 w-full" onClick={onGenerate} disabled={busy}>
        {busy ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
        {busy ? "Generating…" : generateLabel}
      </Button>
    </aside>
  );
}

function SegmentedField({
  label,
  value,
  onChange,
  options,
  labels,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: string[];
  labels?: Record<string, string>;
}) {
  return (
    <div>
      <Label className="text-xs tracking-wide uppercase">{label}</Label>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {options.map((o) => (
          <button
            key={o}
            type="button"
            onClick={() => onChange(o)}
            className={cn(
              "rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors",
              value === o
                ? "border-primary bg-primary/10 text-primary"
                : "border-border text-muted-foreground hover:border-primary/40",
            )}
          >
            {labels?.[o] ?? o}
          </button>
        ))}
      </div>
    </div>
  );
}

function SliderField({
  label,
  value,
  onChange,
  min,
  max,
  step,
}: {
  label: string;
  value: number;
  onChange: (n: number) => void;
  min: number;
  max: number;
  step: number;
}) {
  return (
    <div>
      <div className="flex items-center justify-between">
        <Label className="text-xs tracking-wide uppercase">{label}</Label>
        <span className="text-primary text-sm font-semibold">{value}</span>
      </div>
      <Slider
        className="mt-3"
        value={[value]}
        onValueChange={(v) => onChange(v[0])}
        min={min}
        max={max}
        step={step}
      />
    </div>
  );
}

function DocLine({ doc }: { doc: string }) {
  const { active, data } = useWorkspace();
  if (!active) return null;
  const d: WsDoc | undefined = data.docs.find((x) => x.id === doc);
  return (
    <div className="border-border bg-muted/40 rounded-lg border p-2.5 text-xs">
      <p className="text-muted-foreground text-[10px] font-semibold tracking-widest uppercase">
        Grounded to · {active.name}
      </p>
      <p className="mt-0.5 truncate font-medium">{d?.title ?? "No document selected"}</p>
      {d && <p className="text-muted-foreground mt-0.5">{d.chunks.length} chunks indexed</p>}
      {d?.notes && (
        <p className="border-primary/30 text-muted-foreground mt-2 line-clamp-3 border-l-2 pl-2 italic">
          Your notes: {d.notes}
        </p>
      )}
    </div>
  );
}

function EmptyState({
  icon: Icon,
  title,
  body,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  body: string;
}) {
  return (
    <div className="surface-card flex flex-col items-center justify-center gap-3 p-12 text-center">
      <span className="bg-primary/10 text-primary flex size-14 items-center justify-center rounded-2xl">
        <Icon className="size-7" />
      </span>
      <p className="text-lg font-semibold">{title}</p>
      <p className="text-muted-foreground max-w-md text-sm">{body}</p>
    </div>
  );
}

function SkeletonList() {
  return (
    <div className="space-y-3">
      {[0, 1, 2].map((i) => (
        <div key={i} className="surface-card p-5">
          <div className="bg-muted mb-3 h-3 w-24 animate-pulse rounded" />
          <div className="bg-muted mb-2 h-4 w-3/4 animate-pulse rounded" />
          <div className="bg-muted h-4 w-1/2 animate-pulse rounded" />
        </div>
      ))}
    </div>
  );
}
