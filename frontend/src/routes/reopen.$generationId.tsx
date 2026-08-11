import { useEffect, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { motion } from "motion/react";
import { BookOpen, Brain, Sparkles } from "lucide-react";
import { AppShell } from "@/components/app/AppShell";
import { RoleGate } from "@/components/app/RoleGate";
import { LoadingState, ErrorState } from "@/components/app/AsyncState";
import { InteractiveQuiz } from "@/components/app/InteractiveQuiz";
import { FlashcardDeck, type Flashcard } from "@/components/app/FlashcardDeck";
import { ReviewBadge, NeutralBadge } from "@/components/app/badges";
import * as supabaseApi from "@/api/supabase.api";
import { KIND_TO_AGENT } from "@/services/HistoryService";
import { REVIEW_STATUS_TO_STATE } from "@/services/ReviewService";
import type { DbGeneration } from "@/types/database.types";
import type { GeneratedQuestion, WeakTopic } from "@/types/domain";

export const Route = createFileRoute("/reopen/$generationId")({
  head: () => ({
    meta: [
      { title: "Generation — Sensei" },
      {
        name: "description",
        content: "Reopened generation output: the exact payload produced by the run.",
      },
    ],
  }),
  component: () => (
    <RoleGate allow={["student", "reviewer", "admin"]}>
      <Reopen />
    </RoleGate>
  ),
});

function Reopen() {
  const { generationId } = Route.useParams();
  const [generation, setGeneration] = useState<DbGeneration | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    void supabaseApi
      .getGeneration(generationId)
      .then((g) => {
        if (!cancelled) {
          setGeneration(g);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load this generation");
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [generationId]);

  if (loading) {
    return (
      <div className="bg-background flex min-h-screen items-center justify-center">
        <LoadingState label="Opening generation…" />
      </div>
    );
  }

  if (error || !generation) {
    return (
      <div className="bg-background flex min-h-screen items-center justify-center px-6">
        <ErrorState
          title="Unable to open this generation"
          message={error ?? "The generation no longer exists in your review queue."}
        />
      </div>
    );
  }

  const payload = (generation.payload ?? {}) as Record<string, unknown>;
  const questions = (payload.questions ?? []) as GeneratedQuestion[];
  const cards = (payload.flashcards ?? []) as Flashcard[];
  const days = (payload.days ?? []) as { day: number; topics: string[]; hours: number }[];
  const weakTopics = (payload.weakTopics ?? []) as WeakTopic[];

  return (
    <AppShell
      title={generation.title || generation.kind}
      description={`${KIND_TO_AGENT[generation.kind] ?? generation.kind} · ${generation.model} · ${(
        generation.created_at ?? ""
      )
        .slice(0, 16)
        .replace("T", " ")}`}
    >
      <div className="mb-5 flex flex-wrap items-center gap-2">
        <NeutralBadge>{KIND_TO_AGENT[generation.kind] ?? generation.kind}</NeutralBadge>
        <ReviewBadge state={REVIEW_STATUS_TO_STATE[generation.review_status] ?? "Pending"} />
        <span className="text-muted-foreground text-xs">
          {generation.document_ids?.length ?? 0} grounded documents
        </span>
      </div>

      {questions.length > 0 && <InteractiveQuiz questions={questions} />}

      {cards.length > 0 && (
        <div className="surface-card p-6">
          <FlashcardDeck cards={cards} />
        </div>
      )}

      {days.length > 0 && (
        <div className="space-y-3">
          {days.map((d) => (
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
            </motion.div>
          ))}
        </div>
      )}

      {weakTopics.length > 0 && (
        <div className="space-y-3">
          {weakTopics.map((t, i) => (
            <motion.div
              key={t.topic}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
              className="surface-card p-4"
            >
              <div className="flex flex-wrap items-center gap-3">
                <Brain className="text-primary size-5 shrink-0" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold">{t.topic}</p>
                  {t.description && (
                    <p className="text-muted-foreground mt-1 text-xs leading-relaxed">
                      {t.description}
                    </p>
                  )}
                  <p className="text-muted-foreground mt-1 text-[11px]">{t.action}</p>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      )}

      {questions.length === 0 &&
        cards.length === 0 &&
        days.length === 0 &&
        weakTopics.length === 0 && (
          <div className="surface-card flex flex-col items-center gap-3 p-16 text-center">
            <Sparkles className="text-primary size-8" />
            <h3 className="font-semibold">This generation has no stored items</h3>
            <p className="text-muted-foreground text-sm">
              The payload was empty or is not a reviewable kind.
            </p>
          </div>
        )}
    </AppShell>
  );
}
