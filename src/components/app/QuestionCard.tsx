import { useState } from "react";
import { motion } from "motion/react";
import { BookOpen, ChevronDown, Clock, Gauge, Quote, ShieldCheck } from "lucide-react";
import type { GeneratedQuestion } from "@/types/domain";
import { BloomBadge, DifficultyBadge, NeutralBadge, ReviewBadge } from "@/components/app/badges";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function QuestionCard({ q, index = 0 }: { q: GeneratedQuestion; index?: number }) {
  const [open, setOpen] = useState(false);

  return (
    <motion.article
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06, duration: 0.35, ease: "easeOut" }}
      className="surface-card hover:shadow-elevated p-5 transition-shadow sm:p-6"
    >
      <div className="flex flex-wrap items-center gap-2">
        <DifficultyBadge level={q.difficulty} />
        <NeutralBadge>{q.type}</NeutralBadge>
        <BloomBadge level={q.bloom} />
        <span className="ml-auto flex items-center gap-3 text-xs">
          <span className="text-success inline-flex items-center gap-1">
            <ShieldCheck className="size-3.5" /> {q.grounded}% grounded
          </span>
          <span className="text-muted-foreground inline-flex items-center gap-1">
            <Gauge className="size-3.5" /> {q.quality.toFixed(1)}/10
          </span>
          <span className="text-muted-foreground inline-flex items-center gap-1">
            <Clock className="size-3.5" /> {q.estMinutes} min
          </span>
        </span>
      </div>

      <h3 className="mt-4 text-[15px] leading-relaxed font-medium">{q.prompt}</h3>

      {q.options && (
        <ul className="mt-3 grid gap-2 sm:grid-cols-2">
          {q.options.map((opt) => (
            <li
              key={opt}
              className={cn(
                "rounded-xl border px-3 py-2 text-sm",
                opt === q.answer
                  ? "border-success/35 bg-success/8 text-foreground font-medium"
                  : "border-border bg-muted/40 text-muted-foreground",
              )}
            >
              {opt}
            </li>
          ))}
        </ul>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <ReviewBadge state={q.review} />
        <Button variant="ghost" size="sm" className="ml-auto" onClick={() => setOpen((o) => !o)}>
          {open ? "Hide" : "Answer key, rationale & sources"}
          <ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} />
        </Button>
      </div>

      {open && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          className="mt-4 space-y-4 overflow-hidden border-t pt-4"
        >
          <div>
            <p className="text-muted-foreground text-[11px] font-semibold tracking-widest uppercase">
              Answer key
            </p>
            <p className="mt-1 text-sm font-medium">{q.answer}</p>
          </div>
          <div>
            <p className="text-muted-foreground text-[11px] font-semibold tracking-widest uppercase">
              Rationale
            </p>
            <p className="text-muted-foreground mt-1 text-sm leading-relaxed">{q.rationale}</p>
          </div>
          <div>
            <p className="text-muted-foreground text-[11px] font-semibold tracking-widest uppercase">
              Source references
            </p>
            <div className="mt-2 space-y-2">
              {q.citations.map((c) => (
                <div key={c.chunk} className="border-border bg-muted/40 rounded-xl border p-3">
                  <p className="flex flex-wrap items-center gap-2 text-xs font-medium">
                    <BookOpen className="text-primary size-3.5" />
                    {c.doc} · p.{c.page}
                    <span className="text-muted-foreground font-mono text-[11px]">{c.chunk}</span>
                    <span className="text-primary ml-auto">match {c.score.toFixed(2)}</span>
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
    </motion.article>
  );
}
