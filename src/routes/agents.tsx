import { RoleGate } from "@/components/app/RoleGate";
import { createFileRoute, Link } from "@tanstack/react-router";
import { motion } from "motion/react";
import {
  Calendar,
  Compass,
  Layers,
  Lightbulb,
  ListChecks,
  Sparkle,
  Target,
  ArrowRight,
} from "lucide-react";
import { AppShell } from "@/components/app/AppShell";
import { Button } from "@/components/ui/button";
import { AsyncSection } from "@/components/app/AsyncState";
import { useServiceQuery } from "@/hooks/useServiceQuery";
import { AgentService, ContentService } from "@/services";

export const Route = createFileRoute("/agents")({
  head: () => ({
    meta: [
      { title: "AI Agents — Sensei" },
      {
        name: "description",
        content:
          "Seven specialised study agents: mentor, concept explanation, question bank, test help, flashcards, study plan and revision assistant.",
      },
      { property: "og:title", content: "AI Agents — Sensei" },
      {
        property: "og:description",
        content: "Seven specialised, grounded agents that turn your material into study resources.",
      },
    ],
  }),
  component: () => (
    <RoleGate allow={["admin"]}>
      <Agents />
    </RoleGate>
  ),
});

const icons = {
  compass: Compass,
  lightbulb: Lightbulb,
  "list-checks": ListChecks,
  target: Target,
  layers: Layers,
  calendar: Calendar,
  sparkle: Sparkle,
} as const;

function Agents() {
  const agentsQuery = useServiceQuery(["agents"], () => AgentService.list());
  const cardsQuery = useServiceQuery(["catalogue", "flashcards"], () => ContentService.catalogue());
  const flashcards = cardsQuery.data?.flashcards ?? [];

  return (
    <AppShell
      title="AI Agents"
      description="Each agent is scoped to one job, retrieves from your indexed chunks, and hands its output to validation and review."
    >
      <AsyncSection
        isLoading={agentsQuery.isPending}
        error={agentsQuery.error}
        data={agentsQuery.data}
        isEmpty={(list) => list.length === 0}
        loadingLabel="Loading agents…"
        errorTitle="Unable to load agents"
        emptyTitle="No agents available"
        emptyMessage="Agents will appear once your workspace is configured."
        onRetry={() => void agentsQuery.refetch()}
      >
        {(agents) => (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {agents.map((a, i) => {
              const Icon = icons[a.icon];
              return (
                <motion.article
                  key={a.slug}
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.05, duration: 0.32 }}
                  whileHover={{ y: -4 }}
                  className="surface-card hover:shadow-elevated group flex flex-col p-6 transition-shadow"
                >
                  <span className="bg-primary/10 text-primary flex size-11 items-center justify-center rounded-2xl">
                    <Icon className="size-5" />
                  </span>
                  <h2 className="mt-4 text-base font-semibold">{a.name}</h2>
                  <p className="text-muted-foreground mt-1 text-sm">{a.tagline}</p>
                  <ul className="mt-4 space-y-1.5">
                    {a.bullets.map((b) => (
                      <li key={b} className="text-muted-foreground flex items-start gap-2 text-sm">
                        <span className="bg-primary mt-1.5 size-1.5 shrink-0 rounded-full" />
                        {b}
                      </li>
                    ))}
                  </ul>
                  <div className="mt-5 flex items-center justify-between border-t pt-4">
                    <span className="text-muted-foreground text-xs">{a.runs} runs</span>
                    <Button asChild variant="ghost" size="sm">
                      <Link to="/generate">
                        Run agent
                        <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
                      </Link>
                    </Button>
                  </div>
                </motion.article>
              );
            })}
          </div>
        )}
      </AsyncSection>

      <div className="surface-card mt-8 p-6">
        <h2 className="text-lg font-semibold">Latest flashcard set</h2>
        <p className="text-muted-foreground text-sm">
          Hover a card to flip it — generated from Introduction to Python Programming.
        </p>
        {cardsQuery.isPending && (
          <p className="text-muted-foreground mt-4 text-sm">Loading cards…</p>
        )}
        {cardsQuery.error && (
          <p role="alert" className="text-destructive mt-4 text-sm">
            Unable to load flashcards. {cardsQuery.error.message}
          </p>
        )}
        {!cardsQuery.isPending && !cardsQuery.error && flashcards.length === 0 && (
          <p className="text-muted-foreground mt-4 text-sm">No flashcards generated yet.</p>
        )}
        <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {flashcards.map((f) => (
            <div key={f.front} className="group [perspective:1200px]">
              <div className="relative h-40 transition-transform duration-500 [transform-style:preserve-3d] group-hover:[transform:rotateY(180deg)]">
                <div className="border-border bg-muted/40 absolute inset-0 flex items-center justify-center rounded-2xl border p-4 text-center text-sm font-medium [backface-visibility:hidden]">
                  {f.front}
                </div>
                <div className="border-primary/30 bg-primary/10 text-foreground absolute inset-0 flex items-center justify-center rounded-2xl border p-4 text-center text-sm [backface-visibility:hidden] [transform:rotateY(180deg)]">
                  {f.back}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </AppShell>
  );
}
