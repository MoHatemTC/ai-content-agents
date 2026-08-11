import { useMemo, useRef, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { motion, AnimatePresence } from "motion/react";
import {
  FileText,
  Presentation,
  FileType,
  FileCode2,
  NotebookPen,
  Upload,
  Search,
  Pencil,
  Trash2,
  Plus,
  X,
} from "lucide-react";
import { AppShell } from "@/components/app/AppShell";
import { RoleGate } from "@/components/app/RoleGate";
import { NoActiveWorkspace } from "@/components/app/AsyncState";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { NeutralBadge } from "@/components/app/badges";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { UploadService } from "@/services";
import type { WsDoc } from "@/types/domain";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

const ACCEPTED = ".pdf,.docx,.pptx,.txt,.md";

export const Route = createFileRoute("/library")({
  head: () => ({
    meta: [
      { title: "Document Explorer — Sensei" },
      {
        name: "description",
        content:
          "Browse, upload, edit and organise every lecture file and written note inside the current workspace.",
      },
      { property: "og:title", content: "Document Explorer — Sensei" },
      {
        property: "og:description",
        content: "All the material for this workspace, in one explorer.",
      },
    ],
  }),
  component: () => (
    <RoleGate allow={["student", "reviewer", "admin"]}>
      <Library />
    </RoleGate>
  ),
});

const kindIcon = {
  PDF: FileText,
  DOCX: FileType,
  PPTX: Presentation,
  TXT: FileCode2,
  Note: NotebookPen,
} as const;

function newId() {
  return `doc-${Math.random().toString(36).slice(2, 8)}`;
}

interface DraftState {
  id?: string;
  title: string;
  tags: string;
  notes: string;
  kind: WsDoc["kind"];
}

const emptyDraft: DraftState = { title: "", tags: "", notes: "", kind: "Note" };

function Library() {
  const { active, data, addDoc, updateDoc, removeDoc } = useWorkspace();
  const [query, setQuery] = useState("");
  const [dragging, setDragging] = useState(false);
  const [draft, setDraft] = useState<DraftState | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Workspace name used by handlers that outlive the active-workspace guard.
  const activeName = active ? active.name : "";

  const filtered = useMemo(
    () =>
      data.docs.filter(
        (d) =>
          d.title.toLowerCase().includes(query.toLowerCase()) ||
          d.tags.some((t) => t.toLowerCase().includes(query.toLowerCase())),
      ),
    [data.docs, query],
  );

  async function handleFiles(files: FileList | File[]) {
    if (!active || files.length === 0) return;
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        const result = await UploadService.ingest(active.id, file);
        await addDoc(result.document);
        if (result.pipelineError) {
          toast.warning(
            `Uploaded “${file.name}” but text extraction was skipped: ${result.pipelineError}`,
          );
        } else {
          toast.success(`Uploaded “${file.name}” to ${activeName}`);
        }
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Upload failed. Please try again.");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function saveDraft() {
    if (!draft || !draft.title.trim()) {
      toast.error("Give the material a title first.");
      return;
    }
    const tags = draft.tags
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    if (draft.id) {
      updateDoc(draft.id, { title: draft.title, tags, notes: draft.notes });
      toast.success("Material updated");
      setDraft(null);
      return;
    }
    try {
      await addDoc({
        id: newId(),
        title: draft.title,
        kind: draft.kind,
        size: `${Math.max(1, Math.round(draft.notes.length / 1024))} KB`,
        pages: 1,
        uploaded: new Date().toISOString().slice(0, 10),
        status: "Ready",
        tags,
        notes: draft.notes,
        chunks: draft.notes.trim()
          ? [
              {
                id: `chunk_${Math.random().toString(36).slice(2, 7)}`,
                page: 1,
                tokens: Math.max(20, Math.round(draft.notes.length / 4)),
                text: draft.notes.slice(0, 400),
                tags: tags.slice(0, 2),
                section: "Written note",
              },
            ]
          : [],
      });
      toast.success(`Added to ${activeName}`);
      setDraft(null);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not save the material.");
    }
  }

  return (
    <AppShell
      title="Document Explorer"
      description={`Everything inside ${activeName}. Upload lecture files, write your own lecture notes, edit tags or remove material.`}
      actions={
        <Button variant="outline" onClick={() => setDraft({ ...emptyDraft })}>
          <Plus className="size-4" /> Add written material
        </Button>
      }
    >
      {!active ? (
        <NoActiveWorkspace />
      ) : (
        <>
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              if (e.dataTransfer.files?.length) void handleFiles(e.dataTransfer.files);
            }}
            className={cn(
              "surface-card flex flex-col items-center justify-center px-6 py-12 text-center transition-all",
              dragging && "border-primary shadow-glow scale-[1.005]",
            )}
          >
            <motion.span
              animate={{ y: [0, -6, 0] }}
              transition={{ repeat: Infinity, duration: 2.6, ease: "easeInOut" }}
              className="bg-primary/12 text-primary mb-4 flex size-14 items-center justify-center rounded-2xl"
            >
              <Upload className="size-6" />
            </motion.span>
            <h2 className="text-lg font-semibold">Drop lecture material into {activeName}</h2>
            <p className="text-muted-foreground mt-1 max-w-md text-sm">
              PDF, DOCX, PPTX and TXT up to 100 MB — or write your own lecture notes as material.
            </p>
            <div className="mt-5 flex flex-wrap justify-center gap-2">
              <input
                ref={fileInputRef}
                type="file"
                accept={ACCEPTED}
                multiple
                className="hidden"
                onChange={(e) => {
                  if (e.target.files?.length) void handleFiles(e.target.files);
                }}
              />
              <Button disabled={uploading} onClick={() => fileInputRef.current?.click()}>
                <Upload className="size-4" /> {uploading ? "Uploading…" : "Select files"}
              </Button>
              <Button variant="outline" onClick={() => setDraft({ ...emptyDraft })}>
                <NotebookPen className="size-4" /> Write lecture notes
              </Button>
            </div>
          </div>

          <AnimatePresence>
            {draft && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="overflow-hidden"
              >
                <div className="surface-card mt-6 p-6">
                  <div className="flex items-center justify-between">
                    <h3 className="font-semibold">
                      {draft.id ? "Edit material" : "New written lecture material"}
                    </h3>
                    <Button size="icon" variant="ghost" onClick={() => setDraft(null)}>
                      <X className="size-4" />
                    </Button>
                  </div>
                  <div className="mt-4 grid gap-3 sm:grid-cols-2">
                    <Input
                      value={draft.title}
                      onChange={(e) => setDraft({ ...draft, title: e.target.value })}
                      placeholder="Title, e.g. Lecture 4 — Recursion"
                    />
                    <Input
                      value={draft.tags}
                      onChange={(e) => setDraft({ ...draft, tags: e.target.value })}
                      placeholder="Tags, comma separated"
                    />
                  </div>
                  <Textarea
                    value={draft.notes}
                    onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
                    placeholder="Write or paste your lecture notes here…"
                    className="mt-3 min-h-32"
                  />
                  <div className="mt-4 flex gap-2">
                    <Button onClick={saveDraft}>Save to {activeName}</Button>
                    <Button variant="ghost" onClick={() => setDraft(null)}>
                      Cancel
                    </Button>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          <div className="mt-8 flex flex-wrap items-center gap-3">
            <div className="relative max-w-sm flex-1">
              <Search className="text-muted-foreground absolute top-1/2 left-3 size-4 -translate-y-1/2" />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Filter by title or tag…"
                className="pl-9"
              />
            </div>
            <p className="text-muted-foreground text-sm">
              {filtered.length} items in {activeName}
            </p>
          </div>

          {filtered.length === 0 ? (
            <div className="surface-card mt-6 p-12 text-center">
              <h3 className="font-semibold">Nothing here yet</h3>
              <p className="text-muted-foreground mt-1 text-sm">
                Upload a lecture file or write your own notes for this workspace.
              </p>
            </div>
          ) : (
            <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              <AnimatePresence mode="popLayout">
                {filtered.map((d, i) => {
                  const Icon = kindIcon[d.kind] ?? FileText;
                  return (
                    <motion.article
                      key={d.id}
                      layout
                      initial={{ opacity: 0, y: 16 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, scale: 0.96 }}
                      transition={{ delay: i * 0.04, duration: 0.3 }}
                      whileHover={{ y: -4 }}
                      className="surface-card hover:shadow-elevated flex flex-col p-5 transition-shadow"
                    >
                      <div className="flex flex-1 flex-col">
                        <div className="flex items-start gap-3">
                          <span className="bg-primary/10 text-primary flex size-10 shrink-0 items-center justify-center rounded-xl">
                            <Icon className="size-5" />
                          </span>
                          <div className="min-w-0 flex-1">
                            <h3 className="truncate text-sm font-semibold">{d.title}</h3>
                            <p className="text-muted-foreground mt-0.5 text-xs">
                              {d.kind} · {d.size} · {d.pages} pages · added {d.uploaded}
                            </p>
                          </div>
                        </div>

                        {d.notes && (
                          <p className="text-muted-foreground mt-3 line-clamp-3 text-xs leading-relaxed">
                            {d.notes}
                          </p>
                        )}

                        <div className="mt-4 flex flex-wrap gap-1.5">
                          {d.tags.map((t) => (
                            <NeutralBadge key={t}>{t}</NeutralBadge>
                          ))}
                        </div>
                      </div>

                      <div className="mt-auto flex items-center gap-2 border-t pt-3">
                        <span className="text-muted-foreground text-xs">
                          {d.status === "Ready" ? "Ready to study" : "Processing…"}
                        </span>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="ml-auto"
                          onClick={() =>
                            setDraft({
                              id: d.id,
                              title: d.title,
                              tags: d.tags.join(", "),
                              notes: d.notes ?? "",
                              kind: d.kind,
                            })
                          }
                        >
                          <Pencil className="size-4" /> Edit
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => {
                            removeDoc(d.id);
                            toast.success("Removed from this workspace");
                          }}
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      </div>
                    </motion.article>
                  );
                })}
              </AnimatePresence>
            </div>
          )}
        </>
      )}
    </AppShell>
  );
}
