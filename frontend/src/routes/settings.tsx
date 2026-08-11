import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/app/AppShell";
import { RoleGate } from "@/components/app/RoleGate";
import { ModelSelector, MODELS, type ModelId } from "@/components/app/ModelSelector";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useAuth } from "@/contexts/AuthContext";
import { useState } from "react";
import { toast } from "sonner";

export const Route = createFileRoute("/settings")({
  head: () => ({
    meta: [
      { title: "Settings — Sensei" },
      {
        name: "description",
        content: "Preferences, default AI model and account settings for your Sensei workspace.",
      },
      { property: "og:title", content: "Settings — Sensei" },
      {
        property: "og:description",
        content: "Manage preferences and the AI model powering your workspace.",
      },
    ],
  }),
  component: () => (
    <RoleGate allow={["student", "reviewer", "admin"]}>
      <SettingsPage />
    </RoleGate>
  ),
});

function SettingsPage() {
  const { user } = useAuth();
  const [model, setModel] = useState<ModelId>("gemini");
  const [citeHover, setCiteHover] = useState(true);
  const [autoReveal, setAutoReveal] = useState(false);
  const [confidence, setConfidence] = useState(true);

  return (
    <AppShell
      title="Settings"
      description="Preferences apply to every generator in your workspace."
    >
      <div className="grid gap-6 lg:grid-cols-3">
        <section className="surface-card p-6 lg:col-span-2">
          <h2 className="text-lg font-semibold">Default AI model</h2>
          <p className="text-muted-foreground mt-1 text-sm">
            Change the provider that powers every generator and chat.
          </p>
          <div className="mt-4">
            <ModelSelector value={model} onChange={setModel} />
          </div>
          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            {MODELS.map((m) => (
              <div
                key={m.id}
                className={`border-border rounded-xl border p-3 text-sm ${model === m.id ? "border-primary bg-primary/5" : ""} ${!m.available ? "opacity-70" : ""}`}
              >
                <p className="flex items-center gap-2 font-semibold">
                  {m.name} <span className="text-muted-foreground text-xs">· {m.vendor}</span>
                  {!m.available && (
                    <span className="bg-warning/15 text-warning rounded-full px-1.5 py-0.5 text-[10px] font-semibold">
                      Soon
                    </span>
                  )}
                </p>
                <p className="text-muted-foreground mt-1 text-xs">{m.desc}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="surface-card p-6">
          <h2 className="text-lg font-semibold">Account</h2>
          <div className="mt-4 space-y-3">
            <div>
              <Label>Name</Label>
              <Input className="mt-1.5" defaultValue={user?.name} />
            </div>
            <div>
              <Label>Email</Label>
              <Input className="mt-1.5" defaultValue={user?.email} disabled />
            </div>
            <div>
              <Label>Role</Label>
              <Input className="mt-1.5 capitalize" defaultValue={user?.role} disabled />
            </div>
          </div>
        </section>

        <section className="surface-card p-6 lg:col-span-3">
          <h2 className="text-lg font-semibold">Display</h2>
          <div className="mt-4 grid gap-4 sm:grid-cols-3">
            <ToggleRow
              label="Citation hover cards"
              desc="Show source snippet when hovering a citation chip."
              checked={citeHover}
              onChange={setCiteHover}
            />
            <ToggleRow
              label="Auto-reveal answers"
              desc="Skip the check step in the interactive quiz."
              checked={autoReveal}
              onChange={setAutoReveal}
            />
            <ToggleRow
              label="Confidence badges"
              desc="Show confidence % beside every answer."
              checked={confidence}
              onChange={setConfidence}
            />
          </div>
          <div className="mt-6 flex justify-end">
            <Button onClick={() => toast.success("Settings saved")}>Save changes</Button>
          </div>
        </section>
      </div>
    </AppShell>
  );
}

function ToggleRow({
  label,
  desc,
  checked,
  onChange,
}: {
  label: string;
  desc: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="border-border rounded-xl border p-4">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold">{label}</p>
        <Switch checked={checked} onCheckedChange={onChange} />
      </div>
      <p className="text-muted-foreground mt-1 text-xs">{desc}</p>
    </div>
  );
}
