import { motion } from "motion/react";
import { Check, Loader2, Circle, ArrowRight } from "lucide-react";
import { ContentService } from "@/services";
import { useServiceQuery } from "@/hooks/useServiceQuery";
import { ErrorState, LoadingState } from "./AsyncState";
import { cn } from "@/lib/utils";

export function Pipeline({
  activeIndex,
  workspaceId,
}: {
  activeIndex?: number;
  workspaceId?: string;
}) {
  const { data, isPending, error, refetch } = useServiceQuery(["pipeline-steps", workspaceId], () =>
    ContentService.pipelineSteps(workspaceId),
  );

  if (isPending) {
    return (
      <div className="surface-card p-6">
        <LoadingState label="Loading pipeline…" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="surface-card p-6">
        <ErrorState
          title="Unable to load the pipeline"
          message={error?.message}
          onRetry={() => void refetch()}
        />
      </div>
    );
  }

  const pipelineSteps = data.steps;
  const current = activeIndex ?? data.completed;

  return (
    <div className="surface-card p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">RAG pipeline</h2>
          <p className="text-muted-foreground text-sm">
            Every output is traceable through these nine stages.
          </p>
        </div>
        <span className="border-success/30 bg-success/10 text-success rounded-full border px-3 py-1 text-xs font-medium">
          {current} of {pipelineSteps.length} complete
        </span>
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {pipelineSteps.map((step, i) => {
          const done = i < current;
          const running = i === current;
          return (
            <motion.div
              key={step.key}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.07, duration: 0.3 }}
              className={cn(
                "flex items-center gap-3 rounded-xl border p-3.5 transition-colors",
                done && "border-success/25 bg-success/8",
                running && "border-primary/40 bg-primary/8 shadow-glow",
                !done && !running && "border-border bg-muted/40",
              )}
            >
              <span
                className={cn(
                  "flex size-8 shrink-0 items-center justify-center rounded-lg",
                  done && "bg-success/15 text-success",
                  running && "bg-primary/15 text-primary",
                  !done && !running && "bg-muted text-muted-foreground",
                )}
              >
                {done ? (
                  <Check className="size-4" />
                ) : running ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Circle className="size-3.5" />
                )}
              </span>
              <div className="min-w-0">
                <p className="flex items-center gap-1.5 text-sm font-medium">
                  {step.label}
                  {running && <ArrowRight className="text-primary size-3.5" />}
                </p>
                <p className="text-muted-foreground truncate text-xs">{step.detail}</p>
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
