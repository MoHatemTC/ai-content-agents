import { RoleGate } from "@/components/app/RoleGate";
import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/app/AppShell";
import { Pipeline } from "@/components/app/Pipeline";
import { motion } from "motion/react";
import { useServiceQuery } from "@/hooks/useServiceQuery";
import { AdminService } from "@/services";

export const Route = createFileRoute("/pipeline")({
  head: () => ({
    meta: [
      { title: "RAG Pipeline — Sensei" },
      {
        name: "description",
        content:
          "Watch upload, parsing, chunking, embedding, retrieval, generation, validation, review and export complete stage by stage.",
      },
      { property: "og:title", content: "RAG Pipeline — Sensei" },
      {
        property: "og:description",
        content: "A transparent nine-stage retrieval-augmented generation pipeline.",
      },
    ],
  }),
  component: () => (
    <RoleGate allow={["admin"]}>
      <PipelinePage />
    </RoleGate>
  ),
});

function PipelinePage() {
  const telemetry = useServiceQuery(["pipeline-telemetry"], () => AdminService.pipelineStats());
  const stats = telemetry.data;

  const cards = [
    { label: "Chunks indexed", value: stats ? String(stats.chunksIndexed) : "—" },
    {
      label: "Avg. retrieval latency",
      value: stats?.avgRetrievalMs != null ? `${stats.avgRetrievalMs} ms` : "—",
    },
    { label: "Top-k", value: stats?.topK != null ? `${stats.topK} (hybrid)` : "—" },
    { label: "Embedding model", value: stats?.embeddingModel ?? "—" },
    {
      label: "Validation pass rate",
      value: stats?.validationPassRate != null ? `${stats.validationPassRate}%` : "—",
    },
    {
      label: "Support checked",
      value: stats?.supportCheckedPct != null ? `${stats.supportCheckedPct}%` : "—",
    },
  ];

  return (
    <AppShell
      title="RAG Pipeline"
      description="Nothing is a black box. Follow a generation from raw upload to approved export."
    >
      <Pipeline />

      {telemetry.error && (
        <div className="border-warning/15 bg-warning/5 text-warning mt-6 rounded-xl border p-4 text-sm">
          Live telemetry is unavailable. Run migration{" "}
          <code className="text-foreground">019_pipeline_telemetry.sql</code> in the Supabase SQL
          editor to enable it. {telemetry.error.message}
        </div>
      )}

      <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {cards.map((t, i) => (
          <motion.div
            key={t.label}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
            className="surface-card p-5"
          >
            <p className="text-muted-foreground text-xs tracking-wide uppercase">{t.label}</p>
            <p className="mt-2 text-2xl font-semibold tracking-tight">{t.value}</p>
          </motion.div>
        ))}
      </div>

      <div className="surface-card mt-6 p-6">
        <h2 className="text-lg font-semibold">Why you can trust the output</h2>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          {[
            [
              "Grounded retrieval",
              "Every generated claim is anchored to retrieved chunks with a similarity score above threshold.",
            ],
            [
              "Schema validation",
              "Outputs must conform to a strict schema — malformed items never reach review.",
            ],
            [
              "Support checking",
              "A second pass verifies the answer key is entailed by the cited evidence.",
            ],
            [
              "Human in the loop",
              "Nothing exports until a reviewer approves it. Rejections feed back into prompts.",
            ],
          ].map(([title, body]) => (
            <div key={title} className="border-border bg-muted/40 rounded-xl border p-4">
              <p className="text-sm font-semibold">{title}</p>
              <p className="text-muted-foreground mt-1 text-sm">{body}</p>
            </div>
          ))}
        </div>
      </div>
    </AppShell>
  );
}
