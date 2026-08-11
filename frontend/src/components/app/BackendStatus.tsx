import { useEffect, useState } from "react";
import {
  Check,
  CircleCheck,
  CircleDot,
  CircleX,
  Folder,
  Plug,
  Server,
  ShieldCheck,
  WifiOff,
  Wrench,
} from "lucide-react";
import { http } from "@/api/http";
import { paths } from "@/api/paths";
import { isMockMode, env } from "@/config/env";
import { useAuth } from "@/contexts/AuthContext";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { cn } from "@/lib/utils";

type Probe = "checking" | "ok" | "error";

interface ProbeResult {
  health: Probe;
  authed: Probe;
  healthDetail: string;
}

/**
 * Real, visible proof that the frontend reaches the FastAPI backend.
 *
 * In mock mode this states that explicitly. Otherwise it genuinely calls
 * `GET /health` (no auth) and `GET /workspaces` (with the Supabase Auth token)
 * and reflects the actual outcomes — never fabricated.
 */
export function BackendStatus() {
  const { active } = useWorkspace();
  const { user } = useAuth();
  const [state, setState] = useState<ProbeResult>({
    health: "checking",
    authed: "checking",
    healthDetail: "",
  });

  useEffect(() => {
    if (isMockMode()) {
      setState({ health: "ok", authed: "ok", healthDetail: "mock mode enabled" });
      return;
    }
    const controller = new AbortController();
    (async () => {
      let health: Probe = "error";
      let healthDetail = "";
      let authed: Probe = "error";
      try {
        const res = await fetch(`${env.API_BASE_URL}${paths.health}`, {
          signal: controller.signal,
        });
        if (res.ok) {
          health = "ok";
          const body = (await res.json().catch(() => null)) as { status?: string } | null;
          healthDetail = body?.status ?? "";
        } else {
          healthDetail = `HTTP ${res.status}`;
        }
      } catch {
        health = "error";
        healthDetail = "unreachable";
      }
      if (health === "ok") {
        try {
          await http.get<{ workspaces: unknown[] }>(paths.workspaces.list);
          authed = "ok";
        } catch {
          authed = "error";
        }
      }
      setState({ health, authed, healthDetail });
    })();
    return () => controller.abort();
  }, [isMockMode, env.API_BASE_URL]);

  if (isMockMode()) {
    return (
      <div className="surface-card border-warning/15 flex max-w-sm items-start gap-3 rounded-2xl border p-4 text-sm">
        <Wrench className="text-warning mt-0.5 size-5 shrink-0" />
        <div>
          <p className="font-semibold">Mock mode</p>
          <p className="text-muted-foreground mt-1 text-xs">
            VITE_ENABLE_MOCK is on — the API layer resolves mock fixtures, not the backend. Set{" "}
            <code className="text-foreground">VITE_ENABLE_MOCK=false</code> to talk to FastAPI.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="surface-card max-w-sm rounded-2xl border p-4 text-sm">
      <p className="flex items-center gap-2 font-semibold">
        <Plug className="size-4" /> Backend connection
      </p>
      <ul className="mt-3 space-y-2 text-xs">
        <StatusRow
          icon={Server}
          label="Backend API"
          state={state.health}
          note={state.healthDetail ? `FastAPI · ${state.healthDetail}` : env.API_BASE_URL}
        />
        <StatusRow
          icon={ShieldCheck}
          label="Authenticated (Supabase JWT)"
          state={state.authed}
          note={user ? `as ${user.name}` : "not signed in"}
        />
        <StatusRow
          icon={Folder}
          label="Active workspace"
          state={state.health === "ok" && active ? "ok" : "error"}
          note={active?.name ?? "—"}
        />
      </ul>
    </div>
  );
}

function StatusRow({
  icon: Icon,
  label,
  state,
  note,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  state: Probe;
  note?: string;
}) {
  const icon =
    state === "checking" ? (
      <CircleDot className="text-muted-foreground size-4" />
    ) : state === "ok" ? (
      <CircleCheck className="text-success size-4" />
    ) : (
      <CircleX className="text-destructive size-4" />
    );
  return (
    <li className="flex items-center gap-2">
      <Icon className="text-muted-foreground size-4 shrink-0" />
      {icon}
      <span className="font-medium">{label}</span>
      {state === "ok" ? <Check className="ml-auto size-4 text-success" /> : null}
      {state === "ok" && note ? (
        <span className="text-muted-foreground ml-1 truncate">{note}</span>
      ) : null}
    </li>
  );
}
