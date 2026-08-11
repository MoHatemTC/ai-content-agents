import { createFileRoute, Link } from "@tanstack/react-router";
import { motion } from "motion/react";
import { useState } from "react";
import {
  ArrowRight,
  BookOpen,
  ClipboardList,
  Clock,
  Heart,
  Layers,
  Lightbulb,
  MessagesSquare,
  PlayCircle,
  Sparkles,
} from "lucide-react";
import { AppShell } from "@/components/app/AppShell";
import { RoleGate } from "@/components/app/RoleGate";
import { NoActiveWorkspace } from "@/components/app/AsyncState";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { useAuth } from "@/contexts/AuthContext";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useServiceQuery } from "@/hooks/useServiceQuery";
import { FavoriteService } from "@/services";
import { TeamSection } from "@/components/app/TeamSection";
import type { WsDoc } from "@/types/domain";
import type { FlashcardFavorite } from "@/types/database.types";

export const Route = createFileRoute("/home")({
  head: () => ({
    meta: [
      { title: "Home — Sensei" },
      {
        name: "description",
        content: "Continue studying, jump back into your workspace or generate a new asset.",
      },
      { property: "og:title", content: "Home — Sensei" },
      { property: "og:description", content: "Your grounded study workspace." },
    ],
  }),
  component: () => (
    // Student home only — reviewers land on /review and admins on /admin
    // (RoleGate redirects via ROLE_HOME when the role isn't in the allow-list).
    <RoleGate allow={["student"]}>
      <StudentHome />
    </RoleGate>
  ),
});

const QUICK = [
  {
    to: "/studio",
    tab: "questions",
    label: "Question Bank",
    icon: ClipboardList,
    hint: "MCQs, short answer",
  },
  { to: "/studio", tab: "flashcards", label: "Flashcards", icon: Layers, hint: "Animated deck" },
  { to: "/studio", tab: "mentor", label: "Mentor", icon: MessagesSquare, hint: "Grounded tutor" },
  { to: "/studio", tab: "concept", label: "Concept", icon: Lightbulb, hint: "Explain any idea" },
];

function kindLabel(kind: WsDoc["kind"]): string {
  switch (kind) {
    case "PDF":
      return "PDF Document";
    case "DOCX":
      return "Word Document";
    case "PPTX":
      return "Slides Document";
    case "Note":
    case "TXT":
      return "Text Document";
  }
}

function createdLabel(uploaded: string): string {
  const day = new Date(uploaded);
  if (Number.isNaN(day.getTime())) return "Created recently";
  const today = new Date();
  const sameDay =
    day.getFullYear() === today.getFullYear() &&
    day.getMonth() === today.getMonth() &&
    day.getDate() === today.getDate();
  if (sameDay) return "Created today";
  return `Created ${day.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  })}`;
}

function StudentHome() {
  const { user } = useAuth();
  const { active, data } = useWorkspace();
  const favorites = useServiceQuery(["favorites", active?.id ?? "none"], () =>
    FavoriteService.list(active?.id),
  );
  const [openFavorite, setOpenFavorite] = useState<FlashcardFavorite | null>(null);
  const name = user?.name.split(" ")[0] ?? "there";
  const latest = [...data.docs].sort((a, b) => b.uploaded.localeCompare(a.uploaded))[0];
  const favoriteCards = favorites.data ?? [];

  return (
    <AppShell
      title={`Welcome back, ${name}`}
      description={
        active
          ? `You're in the ${active.name} workspace · ${data.docs.length} materials · ${data.history.length} saved runs.`
          : "You don't have a workspace yet — create one from the sidebar to get started."
      }
      actions={
        <Button asChild>
          <Link to="/studio">
            <Sparkles className="size-4" /> Quick generate
          </Link>
        </Button>
      }
    >
      {!active ? (
        <NoActiveWorkspace />
      ) : (
        <>
          {/* Continue studying */}
          <section className="surface-card overflow-hidden">
            <div className="mesh-bg grid gap-4 p-6 md:grid-cols-[1fr_auto] md:items-center">
              <div>
                <span className="text-primary text-[11px] font-semibold tracking-widest uppercase">
                  Continue studying
                </span>
                {latest ? (
                  <>
                    <h2 className="mt-2 text-xl font-semibold">{latest.title}</h2>
                    <p className="text-muted-foreground mt-1 text-sm">
                      {latest.tags.length > 0 ? latest.tags.join(" · ") : kindLabel(latest.kind)}
                    </p>
                    <div className="text-muted-foreground mt-3 flex flex-wrap items-center gap-3 text-xs">
                      <span className="inline-flex items-center gap-1">
                        <BookOpen className="size-3.5" /> {kindLabel(latest.kind)}
                      </span>
                      <span className="inline-flex items-center gap-1">
                        <Clock className="size-3.5" /> {createdLabel(latest.uploaded)}
                      </span>
                      <span className="inline-flex items-center gap-1">
                        <Layers className="size-3.5" /> {latest.pages} page
                        {latest.pages === 1 ? "" : "s"}
                      </span>
                      <span
                        className={cn(
                          "inline-flex items-center rounded-full px-2 py-0.5 font-medium",
                          latest.status === "Ready"
                            ? "bg-emerald-500/10 text-emerald-600"
                            : "bg-amber-500/10 text-amber-600",
                        )}
                      >
                        {latest.status}
                      </span>
                    </div>
                  </>
                ) : (
                  <>
                    <h2 className="mt-2 text-xl font-semibold">No study material yet.</h2>
                    <p className="text-muted-foreground mt-1 text-sm">
                      Upload or create your first document.
                    </p>
                  </>
                )}
              </div>
              <Button asChild>
                <Link to="/library">
                  <PlayCircle className="size-4" /> {latest ? "View material" : "Browse library"}
                </Link>
              </Button>
            </div>
          </section>

          {/* Quick Generate */}
          <section className="mt-6">
            <h3 className="mb-3 text-sm font-semibold tracking-tight">Quick generate</h3>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {QUICK.map((q, i) => (
                <motion.div
                  key={q.label}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.05 }}
                >
                  <Link
                    to={q.to}
                    className="surface-card hover:border-primary/40 flex h-full items-center gap-3 p-4 transition-colors"
                  >
                    <span className="bg-primary/10 text-primary flex size-10 items-center justify-center rounded-xl">
                      <q.icon className="size-5" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold">{q.label}</p>
                      <p className="text-muted-foreground text-xs">{q.hint}</p>
                    </div>
                    <ArrowRight className="text-muted-foreground size-4" />
                  </Link>
                </motion.div>
              ))}
            </div>
          </section>

          <div className="mt-6 grid gap-6 lg:grid-cols-3">
            {/* Recent docs */}
            <div className="surface-card p-6 lg:col-span-2">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold tracking-tight">Recent documents</h3>
                <Button asChild variant="ghost" size="sm">
                  <Link to="/library">
                    View library <ArrowRight className="size-4" />
                  </Link>
                </Button>
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                {data.docs.slice(0, 4).map((d) => (
                  <Link
                    key={d.id}
                    to="/library"
                    className="border-border hover:border-primary/40 block rounded-xl border p-3 transition-colors"
                  >
                    <p className="truncate text-sm font-medium">{d.title}</p>
                    <p className="text-muted-foreground mt-0.5 text-xs">
                      {d.kind} · {d.pages}p · {d.chunks.length} sections
                    </p>
                  </Link>
                ))}
              </div>
            </div>

            {/* Recent generations */}
            <div className="surface-card p-6">
              <h3 className="text-sm font-semibold tracking-tight">Recent generations</h3>
              <div className="mt-4 divide-y">
                {data.history.slice(0, 4).map((h) => (
                  <div key={h.id} className="py-2.5">
                    <p className="truncate text-sm font-medium">
                      {h.agent} · {h.items} items
                    </p>
                    <p className="text-muted-foreground truncate text-xs">
                      {h.doc} · {h.date}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Continue Mentor / Favorites */}
          <div className="mt-6 grid gap-6 lg:grid-cols-2">
            <Link
              to="/workspace"
              className="surface-card hover:border-primary/40 group p-6 transition-colors"
            >
              <div className="flex items-center gap-3">
                <span className="bg-primary/10 text-primary flex size-10 items-center justify-center rounded-xl">
                  <MessagesSquare className="size-5" />
                </span>
                <div className="flex-1">
                  <p className="font-semibold">Continue your mentor conversation</p>
                  <p className="text-muted-foreground text-xs">
                    Last message: "Explain closures in one paragraph…"
                  </p>
                </div>
                <ArrowRight className="text-muted-foreground group-hover:text-primary size-4 transition-colors" />
              </div>
            </Link>

            <div className="surface-card p-6">
              <div className="flex items-center gap-2">
                <Heart className="text-destructive size-4" />
                <p className="text-sm font-semibold">Favorite flashcards</p>
              </div>
              <div className="mt-3 space-y-2">
                {favoriteCards.length === 0 ? (
                  <p className="text-muted-foreground text-sm">
                    No favorites yet — star a flashcard from the AI Studio.
                  </p>
                ) : (
                  favoriteCards.slice(0, 4).map((f) => (
                    <button
                      key={f.id}
                      type="button"
                      onClick={() => setOpenFavorite(f)}
                      className="border-border bg-muted/40 hover:border-primary/40 flex w-full items-center gap-2 rounded-lg border px-3 py-2 text-left text-sm transition-colors"
                    >
                      <span className="min-w-0 flex-1 truncate">{f.front}</span>
                      <span className="text-muted-foreground shrink-0 text-xs">
                        {f.topic ?? "flashcard"}
                      </span>
                    </button>
                  ))
                )}
              </div>

              <Dialog
                open={openFavorite !== null}
                onOpenChange={(open) => {
                  if (!open) setOpenFavorite(null);
                }}
              >
                <DialogContent className="sm:max-w-md">
                  <DialogHeader>
                    <DialogTitle className="pr-6">{openFavorite?.front}</DialogTitle>
                    {openFavorite?.topic ? (
                      <DialogDescription>{openFavorite.topic}</DialogDescription>
                    ) : null}
                  </DialogHeader>
                  <p className="text-muted-foreground text-sm">
                    {openFavorite?.back ?? "No answer saved for this flashcard."}
                  </p>
                </DialogContent>
              </Dialog>
            </div>
          </div>
          <div className="-mx-4 mt-10 sm:-mx-6 lg:-mx-10">
            <TeamSection />
          </div>
        </>
      )}
    </AppShell>
  );
}
