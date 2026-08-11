import { useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { motion } from "motion/react";
import { Download, ExternalLink, MessagesSquare } from "lucide-react";
import { AppShell } from "@/components/app/AppShell";
import { RoleGate } from "@/components/app/RoleGate";
import { NoActiveWorkspace } from "@/components/app/AsyncState";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ReviewBadge, NeutralBadge } from "@/components/app/badges";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/history")({
  head: () => ({
    meta: [
      { title: "History — Sensei" },
      {
        name: "description",
        content:
          "Every generation and chat in this workspace, with date, agent, material and review state — reopen any conversation in a new tab.",
      },
      { property: "og:title", content: "History — Sensei" },
      { property: "og:description", content: "The full activity trail of this workspace." },
    ],
  }),
  component: () => (
    <RoleGate allow={["student", "reviewer", "admin"]}>
      <HistoryPage />
    </RoleGate>
  ),
});

const statusTone: Record<string, string> = {
  Completed: "text-success",
  Running: "text-info",
  Failed: "text-destructive",
};

function HistoryPage() {
  const { active, data } = useWorkspace();
  const [q, setQ] = useState("");
  const rows = data.history.filter((h) =>
    `${h.id} ${h.agent} ${h.doc}`.toLowerCase().includes(q.toLowerCase()),
  );
  const chats = data.chats.filter((c) =>
    `${c.title} ${c.agent}`.toLowerCase().includes(q.toLowerCase()),
  );

  return (
    <AppShell
      title={active ? `History · ${active.name}` : "History"}
      description="Only this workspace's activity. Open any conversation in a new tab to keep studying side by side."
      actions={
        <Button variant="outline" onClick={() => toast.success("History exported as CSV")}>
          <Download className="size-4" /> Export CSV
        </Button>
      }
    >
      {!active ? (
        <NoActiveWorkspace />
      ) : (
        <>
          <div className="mb-4 max-w-sm">
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Filter this workspace…"
            />
          </div>

          <h2 className="mb-3 text-sm font-semibold">Conversations</h2>
          {chats.length === 0 ? (
            <div className="surface-card p-8 text-center text-sm">
              No conversations in {active.name} yet.
            </div>
          ) : (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {chats.map((c, i) => (
                <motion.a
                  key={c.id}
                  href={`/chat/${c.id}`}
                  target="_blank"
                  rel="noreferrer"
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.05 }}
                  whileHover={{ y: -4 }}
                  className="surface-card hover:border-primary/40 hover:shadow-elevated block p-5 transition-all"
                >
                  <div className="flex items-start gap-3">
                    <span className="bg-primary/10 text-primary flex size-9 items-center justify-center rounded-xl">
                      <MessagesSquare className="size-4" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-semibold">{c.title}</p>
                      <p className="text-muted-foreground mt-0.5 text-xs">
                        {c.agent} · {c.messages.length} messages · {c.date}
                      </p>
                    </div>
                    <ExternalLink className="text-muted-foreground size-4" />
                  </div>
                </motion.a>
              ))}
            </div>
          )}

          <h2 className="mt-8 mb-3 text-sm font-semibold">Generation runs</h2>
          <div className="surface-card overflow-hidden p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-muted/50 text-muted-foreground">
                  <tr className="text-left text-xs tracking-wide uppercase">
                    <th className="px-5 py-3 font-medium">Run</th>
                    <th className="px-5 py-3 font-medium">Date</th>
                    <th className="px-5 py-3 font-medium">Agent</th>
                    <th className="px-5 py-3 font-medium">Material</th>
                    <th className="px-5 py-3 font-medium">Status</th>
                    <th className="px-5 py-3 font-medium">Items</th>
                    <th className="px-5 py-3 font-medium">Review</th>
                    <th className="px-5 py-3" />
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {rows.map((h, i) => (
                    <motion.tr
                      key={h.id}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: i * 0.04 }}
                      className="hover:bg-muted/40 transition-colors"
                    >
                      <td className="px-5 py-3 font-mono text-xs">{h.id}</td>
                      <td className="text-muted-foreground px-5 py-3 whitespace-nowrap">
                        {h.date}
                      </td>
                      <td className="px-5 py-3">
                        <NeutralBadge>{h.agent}</NeutralBadge>
                      </td>
                      <td className="max-w-[220px] truncate px-5 py-3">{h.doc}</td>
                      <td className={cn("px-5 py-3 font-medium", statusTone[h.status])}>
                        {h.status}
                      </td>
                      <td className="px-5 py-3">{h.items}</td>
                      <td className="px-5 py-3">
                        <ReviewBadge state={h.review} />
                      </td>
                      <td className="px-5 py-3 text-right">
                        {h.chatId ? (
                          <a href={`/chat/${h.chatId}`} target="_blank" rel="noreferrer">
                            <Button size="sm" variant="ghost">
                              <ExternalLink className="size-4" /> Open chat
                            </Button>
                          </a>
                        ) : h.generationId ? (
                          <Button asChild size="sm" variant="ghost">
                            <Link
                              to="/reopen/$generationId"
                              params={{ generationId: h.generationId }}
                            >
                              Reopen
                            </Link>
                          </Button>
                        ) : (
                          <Button asChild size="sm" variant="ghost">
                            <Link to="/studio">Reopen</Link>
                          </Button>
                        )}
                      </td>
                    </motion.tr>
                  ))}
                </tbody>
              </table>
            </div>

            {rows.length === 0 && (
              <div className="p-12 text-center">
                <h3 className="font-semibold">No runs in {active.name}</h3>
                <p className="text-muted-foreground mt-1 text-sm">
                  Generate something in AI Studio.
                </p>
              </div>
            )}
          </div>
        </>
      )}
    </AppShell>
  );
}
