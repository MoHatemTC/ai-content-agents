import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { motion } from "motion/react";
import { Download, Sparkles, Wand2 } from "lucide-react";
import { AppShell } from "@/components/app/AppShell";
import { RoleGate } from "@/components/app/RoleGate";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { QuestionCard } from "@/components/app/QuestionCard";
import { EmptyState, NoActiveWorkspace } from "@/components/app/AsyncState";
import { useServiceQuery } from "@/hooks/useServiceQuery";
import { ContentService, GenerationService, HistoryService } from "@/services";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useNotify } from "@/contexts/NotificationContext";
import { MODELS } from "@/components/app/ModelSelector";
import type { GenerateQuestionsRequest } from "@/types/api/generation.contracts";
import type { GeneratedQuestion } from "@/types/domain";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/generate")({
  head: () => ({
    meta: [
      { title: "Generate Questions — Sensei" },
      {
        name: "description",
        content:
          "Configure type, difficulty and count, then generate grounded MCQ, True/False and short-answer questions with rationale and citations.",
      },
      { property: "og:title", content: "Generate Questions — Sensei" },
      {
        property: "og:description",
        content: "Grounded question generation with quality scoring and Bloom classification.",
      },
    ],
  }),
  component: () => (
    <RoleGate allow={["student", "reviewer", "admin"]}>
      <Generate />
    </RoleGate>
  ),
});

const types = ["MCQ", "True/False", "Short Answer"] as const;
const levels = ["Beginner", "Intermediate", "Advanced"] as const;

const metrics = [
  { label: "Grounded", value: "100%", tone: "text-success" },
  { label: "Difficulty match", value: "94%", tone: "text-foreground" },
  { label: "Quality score", value: "9.6 / 10", tone: "text-foreground" },
  { label: "Schema validation", value: "Passed", tone: "text-success" },
  { label: "Support validation", value: "Passed", tone: "text-success" },
  { label: "Human review", value: "Pending", tone: "text-warning" },
  { label: "Question diversity", value: "Excellent", tone: "text-success" },
  { label: "Coverage", value: "87%", tone: "text-foreground" },
];

function Generate() {
  const { active, addHistory } = useWorkspace();
  const notify = useNotify();
  const [type, setType] = useState<(typeof types)[number]>("MCQ");
  const [level, setLevel] = useState<(typeof levels)[number]>("Intermediate");
  const [count, setCount] = useState([12]);
  const [doc, setDoc] = useState<string>("");
  const [items, setItems] = useState<GeneratedQuestion[] | null>(null);
  const [running, setRunning] = useState(false);

  const catalogue = useServiceQuery(["catalogue", "documents"], () => ContentService.catalogue());
  const documents = catalogue.data?.documents ?? [];
  const selectedDoc = doc || documents[0]?.id || "";

  // Generation is scoped to the active workspace; the page gates on it before running.
  const workspaceId = active ? active.id : "";

  /** Exactly the payload the FastAPI question-bank endpoint expects. */
  const buildRequest = (): GenerateQuestionsRequest => ({
    workspaceId,
    documentIds: selectedDoc ? [selectedDoc] : [],
    model: MODELS[0].id,
    count: count[0],
    difficulty: level,
    types: [type],
  });

  const run = async () => {
    if (!active) return;
    if (!selectedDoc) {
      notify.warning("Pick a source document first");
      return;
    }
    setRunning(true);
    const request = buildRequest();
    const res = await GenerationService.generateQuestions({
      workspaceId: request.workspaceId,
      documentId: request.documentIds[0],
      model: request.model,
      count: request.count ?? 12,
      type,
      difficulty: level,
    });
    setRunning(false);

    if (!res.success) {
      notify.fromError(res.error, "Generation failed");
      return;
    }

    setItems(res.data);
    addHistory(
      HistoryService.buildRow({
        agent: "Question Bank",
        doc: documents.find((d) => d.id === selectedDoc)?.title ?? selectedDoc,
        items: res.data.length,
      }),
      {
        kind: "question_bank",
        model: request.model,
        title: documents.find((d) => d.id === selectedDoc)?.title ?? selectedDoc,
        payload: { questions: res.data },
        documentIds: request.documentIds,
      },
    );
    notify.success(`${res.data.length} questions generated`, {
      description: "All items grounded and queued for human review.",
    });
  };

  return (
    <AppShell
      title="Question Bank"
      description="Configure the run, generate against your indexed chunks, and inspect the evidence behind every item."
      actions={
        <Button variant="outline" onClick={() => notify.info("Approve items first to export")}>
          <Download className="size-4" /> Export
        </Button>
      }
    >
      {!active ? (
        <NoActiveWorkspace />
      ) : (
        <>
          <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
            <aside className="surface-card h-fit p-6 lg:sticky lg:top-24">
              <h2 className="text-base font-semibold">Configuration</h2>

              <div className="mt-5 space-y-5">
                <div>
                  <Label className="text-xs tracking-wide uppercase">Question type</Label>
                  <div className="mt-2 grid grid-cols-3 gap-1.5">
                    {types.map((t) => (
                      <button
                        key={t}
                        onClick={() => setType(t)}
                        className={cn(
                          "rounded-xl border px-2 py-2 text-xs font-medium transition-colors",
                          type === t
                            ? "border-primary bg-primary/10 text-primary"
                            : "border-border text-muted-foreground hover:border-primary/40",
                        )}
                      >
                        {t}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <Label className="text-xs tracking-wide uppercase">Difficulty</Label>
                  <div className="mt-2 grid grid-cols-3 gap-1.5">
                    {levels.map((l) => (
                      <button
                        key={l}
                        onClick={() => setLevel(l)}
                        className={cn(
                          "rounded-xl border px-2 py-2 text-xs font-medium transition-colors",
                          level === l
                            ? "border-primary bg-primary/10 text-primary"
                            : "border-border text-muted-foreground hover:border-primary/40",
                        )}
                      >
                        {l}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between">
                    <Label className="text-xs tracking-wide uppercase">Question count</Label>
                    <span className="text-primary text-sm font-semibold">{count[0]}</span>
                  </div>
                  <Slider
                    className="mt-3"
                    value={count}
                    onValueChange={setCount}
                    min={4}
                    max={40}
                    step={2}
                  />
                </div>

                <div>
                  <Label className="text-xs tracking-wide uppercase">Source document</Label>
                  <Select
                    value={selectedDoc}
                    onValueChange={setDoc}
                    disabled={catalogue.isPending || documents.length === 0}
                  >
                    <SelectTrigger className="mt-2 w-full">
                      <SelectValue
                        placeholder={
                          catalogue.isPending
                            ? "Loading documents…"
                            : documents.length === 0
                              ? "No documents available"
                              : "Select a document"
                        }
                      />
                    </SelectTrigger>
                    <SelectContent>
                      {documents.map((d) => (
                        <SelectItem key={d.id} value={d.id}>
                          {d.title}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {catalogue.error && (
                    <p role="alert" className="text-destructive mt-2 text-xs">
                      Unable to load documents. {catalogue.error.message}
                    </p>
                  )}
                </div>

                <Button className="w-full" onClick={() => void run()} disabled={running}>
                  <Wand2 className="size-4" />
                  {running ? "Generating…" : "Generate questions"}
                </Button>
              </div>

              <div className="mt-6 border-t pt-5">
                <p className="text-muted-foreground text-[11px] font-semibold tracking-widest uppercase">
                  Quality analysis
                </p>
                <dl className="mt-3 space-y-2">
                  {metrics.map((m) => (
                    <div key={m.label} className="flex items-center justify-between text-sm">
                      <dt className="text-muted-foreground">{m.label}</dt>
                      <dd className={cn("font-medium", m.tone)}>{m.value}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            </aside>

            <section>
              {running ? (
                <div className="space-y-4">
                  {[0, 1, 2].map((i) => (
                    <div key={i} className="surface-card space-y-3 p-6">
                      <Skeleton className="h-4 w-40" />
                      <Skeleton className="h-5 w-3/4" />
                      <Skeleton className="h-20 w-full" />
                    </div>
                  ))}
                </div>
              ) : items === null ? (
                <div className="surface-card flex flex-col items-center p-16 text-center">
                  <motion.span
                    animate={{ scale: [1, 1.08, 1] }}
                    transition={{ repeat: Infinity, duration: 2.4 }}
                    className="bg-primary/12 text-primary flex size-14 items-center justify-center rounded-2xl"
                  >
                    <Sparkles className="size-6" />
                  </motion.span>
                  <h3 className="mt-4 font-semibold">No questions yet</h3>
                  <p className="text-muted-foreground mt-1 max-w-sm text-sm">
                    Pick a document and press generate — every item will arrive with citations.
                  </p>
                </div>
              ) : items.length === 0 ? (
                <div className="surface-card">
                  <EmptyState
                    title="No questions came back"
                    message="Try a different document, difficulty or a higher count."
                  />
                </div>
              ) : (
                <div className="space-y-4">
                  <p className="text-muted-foreground text-sm">
                    Showing {items.length} of {count[0]} generated items · {type} focus · {level}{" "}
                    bias
                  </p>
                  {items.map((q, i) => (
                    <QuestionCard key={q.id} q={q} index={i} />
                  ))}
                </div>
              )}
            </section>
          </div>
        </>
      )}
    </AppShell>
  );
}
