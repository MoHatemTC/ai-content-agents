import { useCallback, useEffect, useMemo, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { motion, AnimatePresence } from "motion/react";
import {
  AlertTriangle,
  BookOpen,
  Check,
  ChevronDown,
  Download,
  Flag,
  History,
  MessageSquare,
  Pencil,
  Quote,
  ShieldCheck,
  UserRound,
  X,
} from "lucide-react";
import { AppShell } from "@/components/app/AppShell";
import { RoleGate } from "@/components/app/RoleGate";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ReviewBadge, NeutralBadge, DifficultyBadge } from "@/components/app/badges";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useAuth } from "@/contexts/AuthContext";
import { ExportService, ReviewService } from "@/services";
import { REVIEW_STATUS_TO_STATE } from "@/services/ReviewService";
import { KIND_TO_AGENT } from "@/services/HistoryService";
import { getReviewItems } from "@/api/review.api";
import { isMockMode } from "@/config/env";
import type { GeneratedQuestion, ReviewState } from "@/types/domain";
import type { WsAuditEntry } from "@/types/domain";
import type { Citation } from "@/types/domain";
import type { ReviewItem } from "@/types/api/review.contracts";
import type {
  DbGenerationWithCreator,
  DbReview,
  GenerationKind,
  ReviewStatus,
} from "@/types/database.types";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

export const Route = createFileRoute("/review")({
  head: () => ({
    meta: [
      { title: "Human Review — Sensei" },
      {
        name: "description",
        content:
          "Approve, reject or flag every AI output with grounding evidence, supporting chunks and a full audit trail. Nothing exports unreviewed.",
      },
      { property: "og:title", content: "Human Review — Sensei" },
      {
        property: "og:description",
        content:
          "A reviewer gate between AI generation and export, with citations and audit history.",
      },
    ],
  }),
  component: () => (
    <RoleGate allow={["reviewer", "admin"]} permission="review:approve">
      <Review />
    </RoleGate>
  ),
});

type FilterId = "all" | "flagged" | "pending" | "approved" | "rejected";

const GROUNDING_TARGET = 98;
const QUALITY_TARGET = 8.5;

/** A single reviewable output item, normalised across generator payloads. */
interface ReviewableItem {
  key: string;
  itemId: string;
  generationId: string;
  workspaceId: string;
  kind: GenerationKind;
  agent: string;
  doc: string;
  created: string;
  creatorName: string | null;
  workspaceName: string | null;
  review: ReviewState;
  flags: string[];
  prompt: string;
  type: string;
  difficulty: string;
  options: string[];
  answer: string;
  rationale: string;
  quality: number;
  grounded: number;
  citations: Citation[];
}

function flagsForItem(q: ReviewableItem): string[] {
  const f: string[] = [];
  if (q.grounded > 0 && q.grounded < GROUNDING_TARGET)
    f.push(`Grounding ${q.grounded}% below ${GROUNDING_TARGET}% target`);
  if (q.quality > 0 && q.quality < QUALITY_TARGET)
    f.push(`Quality ${q.quality.toFixed(1)}/10 below ${QUALITY_TARGET} target`);
  if (!q.citations?.length) f.push("No supporting chunk attached");
  if (q.citations?.some((c) => c.score < 0.75)) f.push("Weak retrieval match on a cited chunk");
  if (q.options && new Set(q.options).size !== q.options.length)
    f.push("Duplicate distractor detected");
  return f;
}

function stateToStatus(state: ReviewState): ReviewStatus {
  switch (state) {
    case "Approved":
      return "approved";
    case "Rejected":
      return "rejected";
    case "Needs Edit":
      return "needs_edit";
    default:
      return "pending";
  }
}

function reviewStateFromStatus(status: ReviewStatus): ReviewState {
  return REVIEW_STATUS_TO_STATE[status] ?? "Pending";
}

/** Map a FastAPI review item (mock mode) onto the shared queue shape. */
function reviewItemToQueueItem(item: ReviewItem, workspaceName: string): ReviewableItem[] {
  const questions = (item.payload?.questions ?? []) as Partial<GeneratedQuestion>[];
  const kind = item.kind as GenerationKind;
  return questions
    .filter((q) => q?.id)
    .map((q) => ({
      key: `${item.id}:${q.id}`,
      itemId: String(q.id),
      generationId: item.id,
      workspaceId: "",
      kind,
      agent: KIND_TO_AGENT[kind] ?? item.kind,
      doc: item.id,
      created: (item.created_at ?? "").slice(0, 16).replace("T", " "),
      creatorName: null,
      workspaceName,
      review: reviewStateFromItem(item),
      flags: [],
      prompt: String(q.prompt ?? item.id),
      type: String(q.type ?? "MCQ"),
      difficulty: String(q.difficulty ?? "Beginner"),
      options: q.options ?? [],
      answer: String(q.answer ?? ""),
      rationale: String(q.rationale ?? ""),
      quality: Number(q.quality ?? 0),
      grounded: Number(q.grounded ?? 0),
      citations: (q.citations as Citation[]) ?? [],
    }));
}

/** Backend output status → UI review state. */
function reviewStateFromItem(item: ReviewItem): ReviewState {
  switch (item.status) {
    case "approved":
      return "Approved";
    case "rejected":
      return "Rejected";
    case "needs_edit":
    case "edited":
      return "Needs Edit";
    default:
      return "Pending";
  }
}

/** Flatten a Supabase generation payload into queue items (per generator kind). */
function generationToItems(g: DbGenerationWithCreator): ReviewableItem[] {
  const payload = (g.payload ?? {}) as Record<string, unknown>;
  const base = {
    generationId: g.id,
    workspaceId: g.workspace_id,
    kind: g.kind,
    agent: KIND_TO_AGENT[g.kind] ?? g.kind,
    doc: g.title ?? g.kind,
    created: (g.created_at ?? "").slice(0, 16).replace("T", " "),
    creatorName: g.creator_name,
    workspaceName: g.workspace_name,
    review: reviewStateFromStatus(g.review_status),
  };

  const items: Omit<ReviewableItem, "key" | "itemId" | "flags" | "review">[] = [];

  for (const q of (payload.questions as Partial<GeneratedQuestion>[] | undefined) ?? []) {
    if (!q?.id) continue;
    items.push({
      ...base,
      prompt: String(q.prompt ?? ""),
      type: String(q.type ?? "MCQ"),
      difficulty: String(q.difficulty ?? "Beginner"),
      options: q.options ?? [],
      answer: String(q.answer ?? ""),
      rationale: String(q.rationale ?? ""),
      quality: Number(q.quality ?? 0),
      grounded: Number(q.grounded ?? 0),
      citations: (q.citations as Citation[]) ?? [],
    });
  }

  for (const card of (payload.flashcards as Record<string, unknown>[] | undefined) ?? []) {
    if (!card?.id) continue;
    items.push({
      ...base,
      prompt: String(card.front ?? ""),
      type: "Flashcard",
      difficulty: String(card.topic ?? ""),
      options: [],
      answer: String(card.back ?? ""),
      rationale: String(card.topic ?? ""),
      quality: 0,
      grounded: 0,
      citations: (card.citations as Citation[]) ?? [],
    });
  }

  for (const day of (payload.days as Record<string, unknown>[] | undefined) ?? []) {
    items.push({
      ...base,
      prompt: `Day ${String(day.day ?? "")}`,
      type: "Study Plan",
      difficulty: "",
      options: [],
      answer: Array.isArray(day.topics)
        ? (day.topics as string[]).join(" · ")
        : String(day.topics ?? ""),
      rationale: `${String(day.hours ?? "")}h planned for this day`,
      quality: 0,
      grounded: 0,
      citations: [],
    });
  }

  for (const topic of (payload.weakTopics as Record<string, unknown>[] | undefined) ?? []) {
    items.push({
      ...base,
      prompt: String(topic.topic ?? ""),
      type: "Revision",
      difficulty: String(topic.difficulty ?? ""),
      options: [],
      answer: String(topic.action ?? ""),
      rationale: String(topic.description ?? ""),
      quality: Number(topic.strength ?? 0),
      grounded: 0,
      citations: [],
    });
  }

  return items.map((partial, i) => {
    const itemId = partial.prompt || `${g.id}-item-${i}`;
    return {
      ...partial,
      itemId,
      key: `${g.id}:${itemId}`,
      review: base.review,
      flags: [],
    } as ReviewableItem;
  });
}

function reviewsToAudit(reviews: DbReview[]): WsAuditEntry[] {
  return reviews.map((r) => ({
    id: r.id,
    itemId: r.item_id,
    itemLabel: r.item_id,
    action: (r.status === "needs_edit"
      ? "Needs Edit"
      : r.status.charAt(0).toUpperCase() + r.status.slice(1)) as WsAuditEntry["action"],
    actor: r.reviewer_id ? `Reviewer ${r.reviewer_id.slice(0, 6)}` : "System",
    at: (r.created_at ?? "").slice(0, 16).replace("T", " "),
    comment: r.comment ?? undefined,
  }));
}

function Review() {
  const { active, data, setReview, addAudit } = useWorkspace();
  const { user } = useAuth();
  // Staff (reviewer/admin) review every workspace's queue; the workspace
  // switcher must not scope the queue down to the staff member's own
  // workspace. Owners (non-staff) see their own workspace.
  const isStaff = user?.role === "reviewer" || user?.role === "admin";
  const [filter, setFilter] = useState<FilterId>("all");
  const [comments, setComments] = useState<Record<string, string>>({});
  const [items, setItems] = useState<ReviewableItem[]>([]);
  const [audit, setAudit] = useState<WsAuditEntry[]>([]);

  const activeId = active?.id;

  const hydrate = useCallback(() => {
    if (isMockMode()) {
      // Mock queue is scoped to an active workspace; staff without one get an
      // empty state rather than a crash.
      if (!activeId) {
        setItems([]);
        setAudit([]);
        return;
      }
      void Promise.all([getReviewItems(activeId), ReviewService.auditHistory(activeId)])
        .then(([res, history]) => {
          setItems(
            res.items.flatMap((item) => reviewItemToQueueItem(item, active?.name ?? "Workspace")),
          );
          setAudit(history);
        })
        .catch(() => {
          setItems([]);
          setAudit([]);
        });
      return;
    }
    // Real mode: staff read EVERY workspace (staff-wide queue); owners read
    // their own. Omitting the workspace id resolves to the staff-wide path.
    void ReviewService.hydrateQueue(isStaff ? undefined : activeId)
      .then(({ generations, reviews }) => {
        const reviewByItem = new Map(reviews.map((r) => [r.item_id, r]));
        setItems(
          generations.flatMap((g) =>
            generationToItems(g).map((item) => {
              const decided = reviewByItem.get(item.itemId);
              return {
                ...item,
                review: decided ? reviewStateFromStatus(decided.status) : item.review,
              };
            }),
          ),
        );
        setAudit(reviewsToAudit(reviews));
      })
      .catch(() => {
        setItems([]);
        setAudit([]);
      });
  }, [activeId, active, isStaff]);

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  const flagged = useMemo(() => items.filter((q) => q.flags.length > 0), [items]);

  const counts = {
    all: items.length,
    flagged: flagged.length,
    pending: items.filter((q) => q.review === "Pending").length,
    approved: items.filter((q) => q.review === "Approved").length,
    rejected: items.filter((q) => q.review === "Rejected").length,
  };

  const visible = items.filter((q) => {
    if (filter === "all") return true;
    if (filter === "flagged") return q.flags.length > 0;
    if (filter === "pending") return q.review === "Pending";
    if (filter === "approved") return q.review === "Approved";
    return q.review === "Rejected";
  });

  const decide = async (q: ReviewableItem, state: ReviewState) => {
    const comment = comments[q.key]?.trim();
    setItems((prev) => prev.map((i) => (i.key === q.key ? { ...i, review: state } : i)));
    setComments((c) => ({ ...c, [q.key]: "" }));

    if (isMockMode() || !q.workspaceId) {
      setReview(q.itemId, state, { comment: comment || undefined, label: q.prompt });
      addAudit({
        itemId: q.itemId,
        itemLabel: q.prompt,
        action: state as WsAuditEntry["action"],
        actor: "You",
        comment,
      });
      toast.success(`${state} · recorded`);
      return;
    }

    try {
      const next = await ReviewService.decideItem({
        generationId: q.generationId,
        workspaceId: q.workspaceId,
        itemId: q.itemId,
        status: stateToStatus(state),
        comment: comment || null,
      });
      setItems((prev) =>
        prev.map((i) =>
          i.generationId === q.generationId && i.review === "Pending"
            ? { ...i, review: reviewStateFromStatus(next) }
            : i,
        ),
      );
      setAudit((prev) => [
        {
          id: `${q.itemId}-${Date.now().toString(36)}`,
          itemId: q.itemId,
          itemLabel: q.prompt,
          action: state as WsAuditEntry["action"],
          actor: "You",
          at: new Date().toISOString().slice(0, 16).replace("T", " "),
          comment,
        },
        ...prev,
      ]);
      toast.success(`${state} · saved to the review queue`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not persist the decision");
    }
  };

  const onFlag = async (q: ReviewableItem) => {
    const comment = comments[q.key]?.trim() || "Manually flagged for a second opinion";
    setComments((c) => ({ ...c, [q.key]: "" }));
    toast.info("Flagged for a second reviewer");
    if (isMockMode() || !q.workspaceId) {
      addAudit({ itemId: q.itemId, itemLabel: q.prompt, action: "Flagged", actor: "You", comment });
      return;
    }
    try {
      await ReviewService.decideItem({
        generationId: q.generationId,
        workspaceId: q.workspaceId,
        itemId: q.itemId,
        status: "pending",
        comment,
      });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not flag the item");
    }
  };

  /** Real export through the backend (approved outputs only — the API enforces the gate). */
  const handleExport = async () => {
    if (!active || counts.approved === 0) return;
    try {
      await ExportService.exportApproved({
        workspaceId: active.id,
        format: "json",
        title: `${active.name} — approved study content`,
      });
      toast.success(`Downloading ${counts.approved} approved items`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Export failed");
    }
  };

  return (
    <AppShell
      title={active ? `Human Review · ${active.name}` : "Human Review"}
      description="Every AI output is flagged, evidenced and decided here. Exports unlock only for approved items."
      actions={
        <Button
          variant="outline"
          onClick={() => void handleExport()}
          disabled={!active || counts.approved === 0}
        >
          <Download className="size-4" /> Export approved ({counts.approved})
        </Button>
      }
    >
      {items.length === 0 ? (
        <div className="surface-card p-12 text-center">
          <h3 className="font-semibold">Nothing to review yet</h3>
          <p className="text-muted-foreground mt-1 text-sm">
            Generate outputs in the AI Studio and they will queue up here.
          </p>
        </div>
      ) : (
        <>
          {counts.flagged > 0 && (
            <div className="border-warning/35 bg-warning/10 mb-6 flex items-start gap-3 rounded-2xl border p-4">
              <AlertTriangle className="text-warning mt-0.5 size-5 shrink-0" />
              <div>
                <p className="text-sm font-medium">
                  {counts.flagged} output{counts.flagged > 1 ? "s" : ""} flagged by automatic
                  validation
                </p>
                <p className="text-muted-foreground mt-0.5 text-sm">
                  Flags fire when grounding drops below {GROUNDING_TARGET}%, quality below{" "}
                  {QUALITY_TARGET}
                  /10, retrieval match is weak, or distractors overlap.
                </p>
              </div>
            </div>
          )}

          <div className="mb-5 flex flex-wrap gap-1.5">
            {(
              [
                ["all", "All"],
                ["flagged", "Flagged"],
                ["pending", "Pending"],
                ["approved", "Approved"],
                ["rejected", "Rejected"],
              ] as [FilterId, string][]
            ).map(([id, label]) => (
              <button
                key={id}
                onClick={() => setFilter(id)}
                className={cn(
                  "rounded-xl border px-3 py-1.5 text-xs font-medium transition-colors",
                  filter === id
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border text-muted-foreground hover:border-primary/40",
                )}
              >
                {label} · {counts[id]}
              </button>
            ))}
          </div>

          <div className="grid gap-6 xl:grid-cols-[1fr_340px]">
            <div className="min-w-0 space-y-5">
              {visible.length === 0 && (
                <div className="surface-card p-10 text-center text-sm">
                  No items match this filter.
                </div>
              )}
              {visible.map((q, i) => (
                <ReviewItem
                  key={q.key}
                  q={q}
                  index={i}
                  comment={comments[q.key] ?? ""}
                  onComment={(v) => setComments((c) => ({ ...c, [q.key]: v }))}
                  onDecide={(s) => void decide(q, s)}
                  onFlag={() => void onFlag(q)}
                />
              ))}
            </div>

            <AuditPanel entries={audit} />
          </div>
        </>
      )}
    </AppShell>
  );
}

function ReviewItem({
  q,
  index,
  comment,
  onComment,
  onDecide,
  onFlag,
}: {
  q: ReviewableItem;
  index: number;
  comment: string;
  onComment: (v: string) => void;
  onDecide: (s: ReviewState) => void;
  onFlag: () => void;
}) {
  const [open, setOpen] = useState(index === 0);
  const flags = q.flags.length > 0 ? q.flags : flagsForItem(q);

  return (
    <motion.article
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05, duration: 0.3 }}
      className={cn(
        "surface-card p-5 transition-shadow sm:p-6",
        flags.length > 0 && "border-warning/45",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        {q.difficulty ? (
          <DifficultyBadge level={q.difficulty as GeneratedQuestion["difficulty"]} />
        ) : null}
        <NeutralBadge>{q.type}</NeutralBadge>
        <ReviewBadge state={q.review} />
        {flags.length > 0 && (
          <span className="border-warning/40 bg-warning/10 text-warning inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold">
            <Flag className="size-3" /> {flags.length} flag{flags.length > 1 ? "s" : ""}
          </span>
        )}
        <span className="ml-auto flex items-center gap-3 text-xs">
          <span className="text-muted-foreground">
            {q.agent} · {q.doc} · {q.created}
          </span>
          {q.workspaceName && (
            <span className="text-muted-foreground inline-flex items-center gap-1">
              <BookOpen className="size-3.5" />
              {q.workspaceName}
            </span>
          )}
          {q.creatorName && (
            <span className="text-muted-foreground inline-flex items-center gap-1">
              <UserRound className="size-3.5" />
              {q.creatorName}
            </span>
          )}
          {q.grounded > 0 && (
            <span
              className={cn(
                "inline-flex items-center gap-1",
                q.grounded >= GROUNDING_TARGET ? "text-success" : "text-warning",
              )}
            >
              <ShieldCheck className="size-3.5" /> {q.grounded}% grounded
            </span>
          )}
          {q.quality > 0 && (
            <span className="text-muted-foreground">{q.quality.toFixed(1)}/10</span>
          )}
        </span>
      </div>

      <h3 className="mt-4 text-[15px] leading-relaxed font-medium">{q.prompt}</h3>

      {q.options.length > 0 && (
        <ul className="mt-3 grid gap-2 sm:grid-cols-2">
          {q.options.map((opt) => (
            <li
              key={opt}
              className={cn(
                "rounded-xl border px-3 py-2 text-sm",
                opt === q.answer
                  ? "border-success/35 bg-success/8 font-medium"
                  : "border-border bg-muted/40 text-muted-foreground",
              )}
            >
              {opt}
            </li>
          ))}
        </ul>
      )}

      {flags.length > 0 && (
        <ul className="border-warning/30 bg-warning/8 mt-4 space-y-1 rounded-xl border p-3 text-xs">
          {flags.map((f) => (
            <li key={f} className="text-warning flex items-start gap-2">
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
              <span className="text-foreground/80">{f}</span>
            </li>
          ))}
        </ul>
      )}

      <Button variant="ghost" size="sm" className="mt-3" onClick={() => setOpen((o) => !o)}>
        {open ? "Hide evidence" : `Supporting chunks (${q.citations?.length ?? 0})`}
        <ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} />
      </Button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            <div className="mt-3 space-y-3">
              {q.answer && (
                <div>
                  <p className="text-muted-foreground text-[11px] font-semibold tracking-widest uppercase">
                    Answer key & rationale
                  </p>
                  <p className="mt-1 text-sm font-medium">{q.answer}</p>
                  {q.rationale && (
                    <p className="text-muted-foreground mt-1 text-sm leading-relaxed">
                      {q.rationale}
                    </p>
                  )}
                </div>
              )}
              <div className="space-y-2">
                {q.citations?.map((c) => (
                  <div key={c.chunk} className="border-border bg-muted/40 rounded-xl border p-3">
                    <p className="flex flex-wrap items-center gap-2 text-xs font-medium">
                      <BookOpen className="text-primary size-3.5" />
                      {c.doc} · p.{c.page}
                      <span className="text-muted-foreground font-mono text-[11px]">{c.chunk}</span>
                      <span
                        className={cn("ml-auto", c.score < 0.75 ? "text-warning" : "text-primary")}
                      >
                        match {c.score.toFixed(2)}
                      </span>
                    </p>
                    <p className="text-muted-foreground mt-2 flex gap-2 text-xs italic">
                      <Quote className="size-3 shrink-0" />
                      {c.snippet}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="border-border mt-4 border-t pt-4">
        <Textarea
          value={comment}
          onChange={(e) => onComment(e.target.value)}
          placeholder="Reviewer note — saved with your decision in the audit history…"
          className="min-h-16 text-sm"
        />
        <div className="mt-3 flex flex-wrap gap-2">
          <Button size="sm" onClick={() => onDecide("Approved")}>
            <Check className="size-4" /> Approve
          </Button>
          <Button size="sm" variant="outline" onClick={() => onDecide("Needs Edit")}>
            <Pencil className="size-4" /> Needs edit
          </Button>
          <Button size="sm" variant="ghost" onClick={() => onDecide("Rejected")}>
            <X className="size-4" /> Reject
          </Button>
          <Button size="sm" variant="ghost" className="ml-auto" onClick={onFlag}>
            <Flag className="size-4" /> Flag
          </Button>
        </div>
      </div>
    </motion.article>
  );
}

const actionTone: Record<WsAuditEntry["action"], string> = {
  Approved: "text-success border-success/35 bg-success/10",
  Rejected: "text-destructive border-destructive/35 bg-destructive/10",
  "Needs Edit": "text-warning border-warning/35 bg-warning/10",
  Flagged: "text-warning border-warning/35 bg-warning/10",
  Comment: "text-muted-foreground border-border bg-muted/50",
};

function AuditPanel({ entries }: { entries: WsAuditEntry[] }) {
  return (
    <aside className="surface-card h-max p-5 xl:sticky xl:top-24">
      <p className="flex items-center gap-2 text-sm font-semibold">
        <History className="text-primary size-4" /> Audit history
      </p>
      <p className="text-muted-foreground mt-1 text-xs">
        Who decided what, when — scoped to this workspace and kept across reloads.
      </p>

      {entries.length === 0 ? (
        <p className="text-muted-foreground mt-6 text-sm">
          No decisions recorded yet. Approving, rejecting or flagging an output writes an entry
          here.
        </p>
      ) : (
        <ol className="mt-4 max-h-[60vh] space-y-3 overflow-y-auto pr-1">
          {entries.map((e) => (
            <motion.li
              key={e.id}
              initial={{ opacity: 0, x: 8 }}
              animate={{ opacity: 1, x: 0 }}
              className="border-border border-l-2 pl-3"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={cn(
                    "rounded-full border px-2 py-0.5 text-[11px] font-semibold",
                    actionTone[e.action] ?? actionTone.Comment,
                  )}
                >
                  {e.action}
                </span>
                <span className="text-muted-foreground text-[11px]">
                  {e.actor} · {e.at}
                </span>
              </div>
              <p className="mt-1 line-clamp-2 text-xs font-medium">{e.itemLabel}</p>
              {e.comment && (
                <p className="text-muted-foreground mt-1 flex gap-1.5 text-[11px] italic">
                  <MessageSquare className="mt-0.5 size-3 shrink-0" />
                  {e.comment}
                </p>
              )}
            </motion.li>
          ))}
        </ol>
      )}
    </aside>
  );
}
