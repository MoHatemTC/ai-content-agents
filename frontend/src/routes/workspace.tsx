import { useEffect, useRef, useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { motion, AnimatePresence } from "motion/react";
import {
  ArrowLeft,
  Check,
  ChevronRight,
  Copy,
  FileText,
  Pencil,
  Save,
  Search,
  Sparkles,
  Tag,
} from "lucide-react";
import { AppShell } from "@/components/app/AppShell";
import { RoleGate } from "@/components/app/RoleGate";
import { NoActiveWorkspace } from "@/components/app/AsyncState";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { NeutralBadge } from "@/components/app/badges";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { DocumentService } from "@/services";
import type { WsChunk, WsDoc } from "@/types/domain";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

export const Route = createFileRoute("/workspace")({
  head: () => ({
    meta: [
      { title: "Workspace — Sensei" },
      {
        name: "description",
        content:
          "Browse the material in this workspace, open a lecture, read its sections and inspect any passage in detail.",
      },
      { property: "og:title", content: "Workspace — Sensei" },
      {
        property: "og:description",
        content: "Your lectures, their sections and the passages behind every answer.",
      },
    ],
  }),
  component: () => (
    <RoleGate allow={["student", "reviewer", "admin"]}>
      <WorkspacePage />
    </RoleGate>
  ),
});

function WorkspacePage() {
  const { active, data, updateDoc } = useWorkspace();
  const [docId, setDocId] = useState<string | null>(null);
  const [chunkId, setChunkId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [chunksLoading, setChunksLoading] = useState(false);
  const fetchedChunksFor = useRef<string | null>(null);

  // Switching workspace resets the drill-down.
  const activeId = active ? active.id : null;
  useEffect(() => {
    setDocId(null);
    setChunkId(null);
    setQuery("");
  }, [activeId]);

  // Backend document lists carry `chunks: []`, so the parsed sections are
  // fetched the first time a document is opened (fresh uploads already carry
  // them, reloaded documents get them from GET /documents/{id}/chunks).
  useEffect(() => {
    if (!activeId || !docId) return;
    const found = data.docs.find((d) => d.id === docId);
    if ((found && found.chunks.length > 0) || fetchedChunksFor.current === docId) return;
    fetchedChunksFor.current = docId;
    setChunksLoading(true);
    let cancelled = false;
    DocumentService.listChunks(activeId, docId)
      .then((chunks) => {
        if (cancelled) return;
        if (chunks.length > 0) updateDoc(docId, { chunks });
        setChunksLoading(false);
      })
      .catch(() => {
        if (!cancelled) {
          fetchedChunksFor.current = null;
          setChunksLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [activeId, docId, data.docs, updateDoc]);

  const doc: WsDoc | undefined = data.docs.find((d) => d.id === docId);
  const chunk: WsChunk | undefined = doc?.chunks.find((c) => c.id === chunkId);

  const docs = data.docs.filter(
    (d) =>
      d.title.toLowerCase().includes(query.toLowerCase()) ||
      d.tags.some((t) => t.toLowerCase().includes(query.toLowerCase())),
  );

  return (
    <AppShell
      title={active ? active.name : "Workspace"}
      description={`${data.docs.length} lecture materials · ${data.docs.reduce((n, d) => n + d.chunks.length, 0)} sections you can open`}
      actions={
        <Button asChild>
          <Link to="/studio">
            <Sparkles className="size-4" /> Ask AI about this workspace
          </Link>
        </Button>
      }
    >
      {!active ? (
        <NoActiveWorkspace />
      ) : (
        <>
          {/* Breadcrumb */}
          <div className="text-muted-foreground mb-4 flex flex-wrap items-center gap-1.5 text-sm">
            <button
              className="hover:text-foreground font-medium transition-colors"
              onClick={() => {
                setDocId(null);
                setChunkId(null);
              }}
            >
              {active.name}
            </button>
            {doc && (
              <>
                <ChevronRight className="size-3.5" />
                <button
                  className="hover:text-foreground transition-colors"
                  onClick={() => setChunkId(null)}
                >
                  {doc.title}
                </button>
              </>
            )}
            {chunk && (
              <>
                <ChevronRight className="size-3.5" />
                <span className="text-foreground font-mono text-xs">{chunk.id}</span>
              </>
            )}
          </div>

          <AnimatePresence mode="wait">
            {/* Level 1 — documents in this workspace */}
            {!doc && (
              <motion.div
                key="docs"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.25 }}
              >
                <div className="relative mb-5 max-w-sm">
                  <Search className="text-muted-foreground absolute top-1/2 left-3 size-4 -translate-y-1/2" />
                  <Input
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Find a lecture…"
                    className="pl-9"
                  />
                </div>

                {docs.length === 0 ? (
                  <div className="surface-card p-12 text-center">
                    <h3 className="font-semibold">No material in {active.name} yet</h3>
                    <p className="text-muted-foreground mt-1 text-sm">
                      Add lectures from the Document Explorer.
                    </p>
                    <Button asChild className="mt-4" variant="outline">
                      <Link to="/library">Open Document Explorer</Link>
                    </Button>
                  </div>
                ) : (
                  <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                    {docs.map((d, i) => (
                      <motion.button
                        key={d.id}
                        initial={{ opacity: 0, y: 14 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: i * 0.05, duration: 0.3 }}
                        whileHover={{ y: -4 }}
                        onClick={() => setDocId(d.id)}
                        className="surface-card hover:border-primary/40 hover:shadow-elevated p-5 text-left transition-all"
                      >
                        <div className="flex items-start gap-3">
                          <span className="bg-primary/10 text-primary flex size-10 items-center justify-center rounded-xl">
                            <FileText className="size-5" />
                          </span>
                          <div className="min-w-0">
                            <h3 className="truncate text-sm font-semibold">{d.title}</h3>
                            <p className="text-muted-foreground mt-0.5 text-xs">
                              {d.pages} pages · {d.chunks.length} sections
                            </p>
                          </div>
                        </div>
                        <div className="mt-4 flex flex-wrap gap-1.5">
                          {d.tags.map((t) => (
                            <NeutralBadge key={t}>{t}</NeutralBadge>
                          ))}
                        </div>
                      </motion.button>
                    ))}
                  </div>
                )}
              </motion.div>
            )}

            {/* Level 2 — sections of one document */}
            {doc && !chunk && (
              <motion.div
                key="chunks"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.25 }}
              >
                <Button variant="ghost" size="sm" onClick={() => setDocId(null)}>
                  <ArrowLeft className="size-4" /> All material
                </Button>

                <div className="surface-card mt-3 flex flex-wrap items-center gap-3 p-5">
                  <span className="bg-primary/12 text-primary flex size-10 items-center justify-center rounded-xl">
                    <FileText className="size-5" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <h2 className="truncate text-lg font-semibold">{doc.title}</h2>
                    <p className="text-muted-foreground text-xs">
                      {doc.kind} · {doc.pages} pages · added {doc.uploaded}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {doc.tags.map((t) => (
                      <NeutralBadge key={t}>{t}</NeutralBadge>
                    ))}
                  </div>
                </div>

                <LectureNotesEditor doc={doc} />

                <h3 className="mt-6 mb-3 text-sm font-semibold">Sections in this lecture</h3>
                {doc.chunks.length === 0 ? (
                  <div className="surface-card p-8 text-center text-sm">
                    {chunksLoading
                      ? "Loading sections…"
                      : "This material is still being prepared — sections will appear here shortly."}
                  </div>
                ) : (
                  <ul className="space-y-2">
                    {doc.chunks.map((c, i) => (
                      <motion.li
                        key={c.id}
                        initial={{ opacity: 0, x: -8 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: i * 0.04 }}
                      >
                        <button
                          onClick={() => setChunkId(c.id)}
                          className="surface-card hover:border-primary/40 w-full p-4 text-left transition-colors"
                        >
                          <div className="flex flex-wrap items-center gap-2 text-xs">
                            <span className="font-semibold">{c.section}</span>
                            <span className="text-muted-foreground">page {c.page}</span>
                            <span className="ml-auto flex flex-wrap gap-1.5">
                              {c.tags.map((t) => (
                                <span
                                  key={t}
                                  className="border-primary/25 bg-primary/8 text-primary inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium"
                                >
                                  <Tag className="size-3" />
                                  {t}
                                </span>
                              ))}
                            </span>
                          </div>
                          <p className="text-muted-foreground mt-2 line-clamp-2 text-sm leading-relaxed">
                            {c.text}
                          </p>
                        </button>
                      </motion.li>
                    ))}
                  </ul>
                )}
              </motion.div>
            )}

            {/* Level 3 — one section in full */}
            {doc && chunk && (
              <motion.div
                key="chunk"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.25 }}
              >
                <Button variant="ghost" size="sm" onClick={() => setChunkId(null)}>
                  <ArrowLeft className="size-4" /> Back to {doc.title}
                </Button>

                <div className="mt-3 grid gap-4 lg:grid-cols-[1fr_280px]">
                  <div className="surface-card p-6">
                    <h2 className="text-lg font-semibold">{chunk.section}</h2>
                    <p className="text-muted-foreground mt-1 text-xs">
                      {doc.title} · page {chunk.page}
                    </p>
                    <p className="mt-5 text-[15px] leading-relaxed">{chunk.text}</p>
                    <div className="mt-6 flex flex-wrap gap-2">
                      <Button asChild size="sm">
                        <Link to="/studio">
                          <Sparkles className="size-4" /> Generate questions from this
                        </Link>
                      </Button>
                    </div>
                  </div>

                  <aside className="surface-card h-fit p-5">
                    <p className="text-muted-foreground text-[11px] font-semibold tracking-widest uppercase">
                      About this passage
                    </p>
                    <dl className="mt-3 space-y-2.5 text-sm">
                      {[
                        ["Reference", chunk.id],
                        ["Lecture", doc.title],
                        ["Page", String(chunk.page)],
                        ["Reading time", `${Math.max(1, Math.round(chunk.tokens / 200))} min`],
                      ].map(([k, v]) => (
                        <div key={k} className="flex gap-3">
                          <dt className="text-muted-foreground w-24 shrink-0 text-xs">{k}</dt>
                          <dd className={cn("min-w-0 flex-1 truncate text-xs font-medium")}>{v}</dd>
                        </div>
                      ))}
                    </dl>
                    <p className="text-muted-foreground mt-4 mb-2 text-[11px] font-semibold tracking-widest uppercase">
                      Tags
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {chunk.tags.map((t) => (
                        <NeutralBadge key={t}>{t}</NeutralBadge>
                      ))}
                    </div>
                  </aside>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </>
      )}
    </AppShell>
  );
}

/* ---------------- Lecture notes editor ---------------- */

function LectureNotesEditor({ doc }: { doc: WsDoc }) {
  const { updateDoc } = useWorkspace();
  const [draft, setDraft] = useState(doc.notes ?? "");
  const [editing, setEditing] = useState(!doc.notes);
  const [savedAt, setSavedAt] = useState<string | null>(null);

  // Reset the draft whenever a different lecture is opened.
  useEffect(() => {
    setDraft(doc.notes ?? "");
    setEditing(!doc.notes);
    setSavedAt(null);
  }, [doc.id, doc.notes]);

  const dirty = draft !== (doc.notes ?? "");

  const save = () => {
    updateDoc(doc.id, { notes: draft.trim() });
    setSavedAt(new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
    setEditing(false);
    toast.success("Notes saved to this workspace — reusable in the AI Studio");
  };

  return (
    <div className="surface-card mt-4 p-5">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-muted-foreground text-[11px] font-semibold tracking-widest uppercase">
          Lecture notes
        </p>
        {savedAt && (
          <span className="text-success inline-flex items-center gap-1 text-[11px]">
            <Check className="size-3" /> saved {savedAt}
          </span>
        )}
        <div className="ml-auto flex gap-1.5">
          {!editing && (
            <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>
              <Pencil className="size-3.5" /> Edit
            </Button>
          )}
          {doc.notes && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                void navigator.clipboard?.writeText(doc.notes ?? "");
                toast.success("Notes copied — reuse them anywhere in this workspace");
              }}
            >
              <Copy className="size-3.5" /> Reuse
            </Button>
          )}
        </div>
      </div>

      {editing ? (
        <>
          <Textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Write your own notes for this lecture — summaries, exam hints, questions to ask the mentor…"
            className="mt-3 min-h-32 text-sm leading-relaxed"
          />
          <div className="mt-3 flex flex-wrap justify-end gap-2">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setDraft(doc.notes ?? "");
                setEditing(Boolean(!doc.notes));
              }}
            >
              Cancel
            </Button>
            <Button size="sm" onClick={save} disabled={!dirty}>
              <Save className="size-3.5" /> Save notes
            </Button>
          </div>
        </>
      ) : (
        <p className="mt-2 text-sm leading-relaxed whitespace-pre-wrap">{doc.notes}</p>
      )}
    </div>
  );
}
