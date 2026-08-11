import { cn } from "@/lib/utils";
import type { BloomLevel, Difficulty, ReviewState } from "@/types/domain";

const base =
  "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium whitespace-nowrap";

const bloomTone: Record<BloomLevel, string> = {
  Knowledge: "border-info/30 bg-info/10 text-info",
  Understanding: "border-primary/30 bg-primary/10 text-primary",
  Application: "border-success/30 bg-success/10 text-success",
  Analysis: "border-warning/40 bg-warning/12 text-warning",
  Evaluation: "border-destructive/30 bg-destructive/10 text-destructive",
  Creation: "border-primary-glow/40 bg-primary-glow/12 text-primary-glow",
};

export function BloomBadge({ level }: { level: BloomLevel }) {
  return <span className={cn(base, bloomTone[level])}>{level}</span>;
}

const diffTone: Record<Difficulty, string> = {
  Beginner: "border-success/30 bg-success/10 text-success",
  Intermediate: "border-info/30 bg-info/10 text-info",
  Advanced: "border-warning/40 bg-warning/12 text-warning",
};

export function DifficultyBadge({ level }: { level: Difficulty }) {
  return <span className={cn(base, diffTone[level])}>{level}</span>;
}

const reviewTone: Record<ReviewState, string> = {
  Pending: "border-warning/40 bg-warning/12 text-warning",
  Approved: "border-success/30 bg-success/10 text-success",
  "Needs Edit": "border-info/30 bg-info/10 text-info",
  Rejected: "border-destructive/30 bg-destructive/10 text-destructive",
};

export function ReviewBadge({ state }: { state: ReviewState }) {
  return <span className={cn(base, reviewTone[state])}>{state}</span>;
}

export function NeutralBadge({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span className={cn(base, "border-border bg-muted text-muted-foreground", className)}>
      {children}
    </span>
  );
}
