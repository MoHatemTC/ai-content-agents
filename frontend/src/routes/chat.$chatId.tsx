import { createFileRoute } from "@tanstack/react-router";
import { motion } from "motion/react";
import { MessagesSquare } from "lucide-react";
import { RoleGate } from "@/components/app/RoleGate";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/chat/$chatId")({
  head: () => ({
    meta: [
      { title: "Conversation — Sensei" },
      {
        name: "description",
        content: "A saved study conversation from your workspace, reopened in full.",
      },
      { property: "og:title", content: "Conversation — Sensei" },
      { property: "og:description", content: "Read back a saved mentor or concept conversation." },
    ],
  }),
  component: () => (
    <RoleGate allow={["student", "reviewer", "admin"]}>
      <ChatPage />
    </RoleGate>
  ),
});

function ChatPage() {
  const { chatId } = Route.useParams();
  const { data } = useWorkspace();
  const chat = data.chats.find((c) => c.id === chatId);

  if (!chat) {
    return (
      <main className="bg-background text-foreground flex min-h-screen items-center justify-center px-6">
        <div className="text-center">
          <h1 className="text-xl font-semibold">Conversation not found</h1>
          <p className="text-muted-foreground mt-1 text-sm">
            It may have been removed from this workspace.
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="bg-background text-foreground min-h-screen">
      <header className="border-border bg-card/60 border-b backdrop-blur">
        <div className="mx-auto flex max-w-3xl items-center gap-3 px-4 py-4 sm:px-6">
          <span className="bg-primary/10 text-primary flex size-10 items-center justify-center rounded-xl">
            <MessagesSquare className="size-5" />
          </span>
          <div className="min-w-0">
            <h1 className="truncate text-base font-semibold">{chat.title}</h1>
            <p className="text-muted-foreground text-xs">
              {chat.agent} · {chat.model} · {chat.date}
            </p>
          </div>
        </div>
      </header>

      <div className="mesh-bg min-h-[calc(100vh-4.5rem)] px-4 py-8 sm:px-6">
        <div className="mx-auto max-w-3xl space-y-4">
          {chat.messages.map((m, i) => (
            <motion.div
              key={m.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.06 }}
              className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}
            >
              <div
                className={cn(
                  "max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed",
                  m.role === "user" ? "bg-primary text-primary-foreground" : "surface-card",
                )}
              >
                {m.text}
                <span className="mt-1 block text-[10px] opacity-60">{m.time}</span>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </main>
  );
}
