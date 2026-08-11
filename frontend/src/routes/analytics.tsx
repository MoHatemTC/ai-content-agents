import { RoleGate } from "@/components/app/RoleGate";
import { createFileRoute } from "@tanstack/react-router";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { BookOpen, Gauge, Layers, ListChecks, ShieldCheck, Timer } from "lucide-react";
import { AppShell } from "@/components/app/AppShell";
import { StatCard } from "@/components/app/StatCard";
import { AsyncSection, NoActiveWorkspace } from "@/components/app/AsyncState";
import { useServiceQuery } from "@/hooks/useServiceQuery";
import { AnalyticsService } from "@/services";
import { useWorkspace } from "@/contexts/WorkspaceContext";

export const Route = createFileRoute("/analytics")({
  head: () => ({
    meta: [
      { title: "Analytics — Sensei" },
      {
        name: "description",
        content:
          "Track questions generated, grounding success, average quality, Bloom distribution, question types and topic coverage across your material.",
      },
      { property: "og:title", content: "Analytics — Sensei" },
      {
        property: "og:description",
        content: "Quality, grounding and coverage analytics for every AI generation.",
      },
    ],
  }),
  component: () => (
    <RoleGate allow={["admin"]} permission="analytics:read">
      <Analytics />
    </RoleGate>
  ),
});

const pieColors = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
  "var(--primary-glow)",
];

const tooltipStyle = {
  background: "var(--card)",
  border: "1px solid var(--border)",
  borderRadius: "12px",
  fontSize: "12px",
  color: "var(--card-foreground)",
};

function Analytics() {
  const { active } = useWorkspace();
  const workspaceId = active ? active.id : "";
  const { data, isPending, error, refetch } = useServiceQuery(
    ["analytics", workspaceId],
    () => AnalyticsService.get({ workspaceId, range: "30d" }),
    { enabled: active != null },
  );

  return (
    <AppShell
      title="Analytics"
      description="How much you generated, how well it scored, and where your material is still uncovered."
    >
      {!active ? (
        <NoActiveWorkspace />
      ) : (
        <>
          <AsyncSection
            isLoading={isPending}
            error={error}
            data={data}
            loadingLabel="Loading analytics…"
            errorTitle="Unable to load analytics"
            emptyTitle="No analytics yet"
            emptyMessage="Generate your first study assets to see quality and coverage metrics."
            isEmpty={(d) =>
              d.activitySeries.every((p) => p.questions === 0 && p.flashcards === 0) &&
              d.topicCoverage.length === 0
            }
            onRetry={() => void refetch()}
          >
            {({ activitySeries, bloomDistribution, topicCoverage, typeDistribution, summary }) => (
              <>
                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                  <StatCard
                    label="Questions generated"
                    value={String(summary.questions)}
                    delta="Across all workspaces"
                    icon={ListChecks}
                    index={0}
                  />
                  <StatCard
                    label="Flashcards created"
                    value={String(summary.flashcards)}
                    delta="Across all workspaces"
                    icon={Layers}
                    index={1}
                  />
                  <StatCard
                    label="Study plans"
                    value={String(summary.studyPlans)}
                    delta="Generated plans"
                    icon={BookOpen}
                    index={2}
                  />
                  <StatCard
                    label="Grounding success"
                    value={summary.grounding != null ? `${summary.grounding}%` : "—"}
                    delta="Mean citation coverage"
                    icon={ShieldCheck}
                    index={3}
                  />
                  <StatCard
                    label="Average quality"
                    value={summary.quality != null ? `${summary.quality} / 10` : "—"}
                    delta="Mean review score"
                    icon={Gauge}
                    index={4}
                  />
                  <StatCard
                    label="Review completion"
                    value={summary.reviewCompletion != null ? `${summary.reviewCompletion}%` : "—"}
                    delta="Of all reviewable runs"
                    icon={Timer}
                    index={5}
                  />
                </div>

                <div className="mt-6 grid gap-6 lg:grid-cols-3">
                  <div className="surface-card p-6 lg:col-span-2">
                    <h2 className="text-lg font-semibold">Generation volume & quality</h2>
                    <p className="text-muted-foreground text-sm">Last six weeks</p>
                    <div className="mt-5 h-72">
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={activitySeries}>
                          <defs>
                            <linearGradient id="gq" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.55} />
                              <stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0.02} />
                            </linearGradient>
                            <linearGradient id="gf" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="0%" stopColor="var(--chart-3)" stopOpacity={0.4} />
                              <stop offset="100%" stopColor="var(--chart-3)" stopOpacity={0.02} />
                            </linearGradient>
                          </defs>
                          <CartesianGrid
                            strokeDasharray="3 3"
                            stroke="var(--border)"
                            vertical={false}
                          />
                          <XAxis
                            dataKey="week"
                            stroke="var(--muted-foreground)"
                            fontSize={12}
                            tickLine={false}
                            axisLine={false}
                          />
                          <YAxis
                            stroke="var(--muted-foreground)"
                            fontSize={12}
                            tickLine={false}
                            axisLine={false}
                          />
                          <Tooltip contentStyle={tooltipStyle} />
                          <Area
                            type="monotone"
                            dataKey="questions"
                            stroke="var(--chart-1)"
                            fill="url(#gq)"
                            strokeWidth={2}
                          />
                          <Area
                            type="monotone"
                            dataKey="flashcards"
                            stroke="var(--chart-3)"
                            fill="url(#gf)"
                            strokeWidth={2}
                          />
                        </AreaChart>
                      </ResponsiveContainer>
                    </div>
                  </div>

                  <div className="surface-card p-6">
                    <h2 className="text-lg font-semibold">Question types</h2>
                    <p className="text-muted-foreground text-sm">Distribution across all runs</p>
                    <div className="mt-4 h-56">
                      <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                          <Pie
                            data={typeDistribution}
                            dataKey="value"
                            nameKey="name"
                            innerRadius={52}
                            outerRadius={82}
                            paddingAngle={3}
                            stroke="none"
                          >
                            {typeDistribution.map((_, i) => (
                              <Cell key={i} fill={pieColors[i]} />
                            ))}
                          </Pie>
                          <Tooltip contentStyle={tooltipStyle} />
                        </PieChart>
                      </ResponsiveContainer>
                    </div>
                    <ul className="mt-2 space-y-1.5">
                      {typeDistribution.map((t, i) => (
                        <li key={t.name} className="flex items-center gap-2 text-sm">
                          <span
                            className="size-2.5 rounded-full"
                            style={{ background: pieColors[i] }}
                          />
                          {t.name}
                          <span className="text-muted-foreground ml-auto">{t.value}%</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>

                <div className="mt-6 grid gap-6 lg:grid-cols-2">
                  <div className="surface-card p-6">
                    <h2 className="text-lg font-semibold">Bloom's taxonomy distribution</h2>
                    <p className="text-muted-foreground text-sm">
                      Every question is auto-classified
                    </p>
                    <div className="mt-5 h-64">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={bloomDistribution}>
                          <CartesianGrid
                            strokeDasharray="3 3"
                            stroke="var(--border)"
                            vertical={false}
                          />
                          <XAxis
                            dataKey="name"
                            stroke="var(--muted-foreground)"
                            fontSize={11}
                            tickLine={false}
                            axisLine={false}
                          />
                          <YAxis
                            stroke="var(--muted-foreground)"
                            fontSize={12}
                            tickLine={false}
                            axisLine={false}
                          />
                          <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "var(--muted)" }} />
                          <Bar dataKey="value" radius={[8, 8, 0, 0]}>
                            {bloomDistribution.map((_, i) => (
                              <Cell key={i} fill={pieColors[i % pieColors.length]} />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>

                  <div className="surface-card p-6">
                    <h2 className="text-lg font-semibold">Topic coverage</h2>
                    <p className="text-muted-foreground text-sm">Across uploaded documents</p>
                    {topicCoverage.length === 0 ? (
                      <div className="text-muted-foreground mt-8 flex h-40 items-center justify-center text-center text-sm">
                        No coverage data yet — upload documents to see syllabus coverage.
                      </div>
                    ) : (
                      <>
                        <div className="mt-5 h-64">
                          <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={topicCoverage} layout="vertical" margin={{ left: 16 }}>
                              <CartesianGrid
                                strokeDasharray="3 3"
                                stroke="var(--border)"
                                horizontal={false}
                              />
                              <XAxis
                                type="number"
                                domain={[0, 100]}
                                stroke="var(--muted-foreground)"
                                fontSize={12}
                                tickLine={false}
                                axisLine={false}
                              />
                              <YAxis
                                type="category"
                                dataKey="topic"
                                stroke="var(--muted-foreground)"
                                fontSize={12}
                                width={80}
                                tickLine={false}
                                axisLine={false}
                              />
                              <Tooltip
                                contentStyle={tooltipStyle}
                                cursor={{ fill: "var(--muted)" }}
                              />
                              <Bar dataKey="pct" radius={[0, 8, 8, 0]}>
                                {topicCoverage.map((t, i) => (
                                  <Cell
                                    key={i}
                                    fill={t.covered ? "var(--chart-1)" : "var(--chart-5)"}
                                  />
                                ))}
                              </Bar>
                            </BarChart>
                          </ResponsiveContainer>
                        </div>
                        <p className="text-muted-foreground mt-3 text-sm">
                          Overall coverage{" "}
                          <span className="text-foreground font-semibold">
                            {Math.round(
                              topicCoverage.reduce((n, t) => n + t.pct, 0) / topicCoverage.length,
                            )}
                            %
                          </span>{" "}
                          ·{" "}
                          {topicCoverage.filter((t) => !t.covered).length > 0
                            ? `${topicCoverage
                                .filter((t) => !t.covered)
                                .map((t) => t.topic)
                                .join(", ")} still need question sets.`
                            : "All topics covered."}
                        </p>
                      </>
                    )}
                  </div>
                </div>
              </>
            )}
          </AsyncSection>
        </>
      )}
    </AppShell>
  );
}
