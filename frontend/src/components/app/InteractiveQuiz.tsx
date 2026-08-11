import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Check, Copy, Eye, Heart, PenLine, RefreshCw, ShieldCheck, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import type { GeneratedQuestion } from "@/types/domain";
import { CitationChip } from "@/components/app/CitationChip";
import { DifficultyBadge, BloomBadge, NeutralBadge } from "@/components/app/badges";

export function InteractiveQuiz({ questions }: { questions: GeneratedQuestion[] }) {
  return (
    <div className="space-y-4">
      {questions.map((q, i) => (
        <QuizItem key={q.id} q={q} index={i} />
      ))}
    </div>
  );
}

function QuizItem({ q, index }: { q: GeneratedQuestion; index: number }) {
  const [picked, setPicked] = useState<string | null>(null);
  const [checked, setChecked] = useState(false);
  const [fav, setFav] = useState(false);
  const [boxOpen, setBoxOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [showAnswer, setShowAnswer] = useState(false);

  const isShortAnswer = q.type === "Short Answer";
  const options = q.options ?? [q.answer, "True", "False"].slice(0, 2);
  const correct = picked === q.answer;

  const copy = () => {
    void navigator.clipboard.writeText(
      `Q${index + 1}. ${q.prompt}\nAnswer: ${q.answer}\n${q.rationale}`,
    );
    toast.success("Question copied");
  };

  const reset = () => {
    setPicked(null);
    setChecked(false);
    setBoxOpen(false);
    setShowAnswer(false);
    setDraft("");
  };

  return (
    <motion.article
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05 }}
      className="surface-card p-5 sm:p-6"
    >
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="text-muted-foreground font-mono">Q{index + 1}</span>
        <DifficultyBadge level={q.difficulty} />
        <NeutralBadge>{q.type}</NeutralBadge>
        <BloomBadge level={q.bloom} />
        <span className="text-success ml-auto inline-flex items-center gap-1">
          <ShieldCheck className="size-3.5" /> {q.grounded}% grounded
        </span>
      </div>

      <h3 className="mt-3 text-[15px] leading-relaxed font-medium">{q.prompt}</h3>

      {isShortAnswer ? (
        <div className="mt-4 space-y-3">
          {!boxOpen ? (
            <button
              type="button"
              onClick={() => setBoxOpen(true)}
              className="border-border flex w-full items-center gap-2.5 rounded-xl border border-dashed px-3 py-2.5 text-left text-sm text-muted-foreground transition-colors hover:border-primary/40 hover:bg-muted/40"
            >
              <PenLine className="size-4 shrink-0" />
              <span>Write your answer</span>
              <span className="ml-auto text-[11px] font-medium">Tap to open</span>
            </button>
          ) : (
            <div>
              <textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="Think it through and type your answer here…"
                rows={3}
                className="border-border bg-muted/40 w-full resize-y rounded-xl border p-3 text-sm placeholder:text-muted-foreground/60 focus:border-primary focus:outline-none"
              />
              <div className="mt-3 flex flex-wrap items-center gap-2">
                {!showAnswer ? (
                  <Button size="sm" onClick={() => setShowAnswer(true)}>
                    <Eye className="size-3.5" /> Show answer
                  </Button>
                ) : (
                  <span className="border-success/30 bg-success/10 border border-success/30 rounded-xl px-3 py-2 text-sm">
                    <span className="text-success text-[11px] font-semibold tracking-widest uppercase">
                      Expected answer
                    </span>
                    <span className="text-foreground mt-0.5 block">{q.answer}</span>
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      ) : (
        <ul className="mt-4 grid gap-2 sm:grid-cols-2">
          {options.map((opt) => {
            const isPicked = picked === opt;
            const isCorrect = opt === q.answer;
            const state =
              checked && isCorrect
                ? "correct"
                : checked && isPicked && !isCorrect
                  ? "wrong"
                  : isPicked
                    ? "picked"
                    : "idle";
            return (
              <li key={opt}>
                <button
                  disabled={checked}
                  onClick={() => setPicked(opt)}
                  className={cn(
                    "flex w-full items-center gap-2.5 rounded-xl border px-3 py-2.5 text-left text-sm transition-all",
                    state === "idle" && "border-border hover:border-primary/40 hover:bg-muted/40",
                    state === "picked" && "border-primary bg-primary/10",
                    state === "correct" && "border-success bg-success/10 text-foreground",
                    state === "wrong" && "border-destructive bg-destructive/10 text-foreground",
                  )}
                >
                  <span
                    className={cn(
                      "flex size-5 shrink-0 items-center justify-center rounded-full border text-[11px] font-semibold",
                      state === "correct" && "border-success bg-success text-success-foreground",
                      state === "wrong" &&
                        "border-destructive bg-destructive text-destructive-foreground",
                      state === "picked" && "border-primary bg-primary text-primary-foreground",
                      state === "idle" && "border-border",
                    )}
                  >
                    {state === "correct" ? (
                      <Check className="size-3" />
                    ) : state === "wrong" ? (
                      <X className="size-3" />
                    ) : (
                      ""
                    )}
                  </span>
                  <span className="flex-1">{opt}</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        {!isShortAnswer &&
          (!checked ? (
            <Button size="sm" onClick={() => setChecked(true)} disabled={!picked}>
              Check answer
            </Button>
          ) : (
            <span
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold",
                correct ? "bg-success/15 text-success" : "bg-destructive/15 text-destructive",
              )}
            >
              {correct ? <Check className="size-3.5" /> : <X className="size-3.5" />}
              {correct ? "Correct" : `Answer: ${q.answer}`}
            </span>
          ))}
        <Button size="sm" variant="ghost" onClick={reset}>
          <RefreshCw className="size-3.5" /> Retry
        </Button>
        <Button size="sm" variant="ghost" onClick={() => toast.info("Regenerating this question…")}>
          Regenerate
        </Button>
        <Button size="sm" variant="ghost" onClick={copy}>
          <Copy className="size-3.5" /> Copy
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => {
            setFav((f) => !f);
            toast.success(fav ? "Removed from favorites" : "Added to favorites");
          }}
          className={cn(fav && "text-destructive")}
        >
          <Heart className={cn("size-3.5", fav && "fill-current")} />
        </Button>
      </div>

      <AnimatePresence>
        {(checked || (isShortAnswer && showAnswer)) && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="border-border mt-4 space-y-3 overflow-hidden border-t pt-4"
          >
            <div>
              <p className="text-muted-foreground text-[11px] font-semibold tracking-widest uppercase">
                Explanation
              </p>
              <p className="text-muted-foreground mt-1 text-sm leading-relaxed">{q.rationale}</p>
            </div>
            <div>
              <p className="text-muted-foreground text-[11px] font-semibold tracking-widest uppercase">
                Sources
              </p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {q.citations.map((c, i) => (
                  <CitationChip key={c.chunk} source={c} index={i} />
                ))}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.article>
  );
}
