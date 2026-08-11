import { useEffect, useState } from "react";
import { createFileRoute, Link, useNavigate, useSearch } from "@tanstack/react-router";
import { motion } from "motion/react";
import { ArrowLeft, LogIn, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { DEMO_ACCOUNTS, homeForRole, useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";
import { BrandMark } from "@/components/app/BrandMark";

export const Route = createFileRoute("/login")({
  validateSearch: (s: Record<string, unknown>): { redirect?: string } =>
    typeof s.redirect === "string" ? { redirect: s.redirect } : {},
  head: () => ({
    meta: [
      { title: "Sign in — Sensei" },
      {
        name: "description",
        content: "Sign in to Sensei to access your grounded study workspace.",
      },
      { property: "og:title", content: "Sign in — Sensei" },
      { property: "og:description", content: "Access your grounded study workspace." },
    ],
  }),
  component: LoginPage,
});

function LoginPage() {
  const { signIn, user, ready } = useAuth();
  const navigate = useNavigate();
  const { redirect } = useSearch({ from: "/login" });
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (ready && user) navigate({ to: redirect ?? homeForRole(user.role) });
  }, [ready, user, redirect, navigate]);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    const res = await signIn(email, password, remember);
    setSubmitting(false);
    if (!res.ok) {
      toast.error(res.error);
      return;
    }
    toast.success(`Welcome, ${res.user.name}`);
    navigate({ to: redirect ?? homeForRole(res.user.role) });
  };

  return (
    <div className="bg-background mesh-bg min-h-screen">
      <div className="mx-auto flex min-h-screen max-w-6xl items-center gap-10 px-4 py-10 sm:px-6 lg:grid lg:grid-cols-2">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="hidden lg:block"
        >
          <Link to="/" className="flex items-center gap-2.5">
            <BrandMark className="size-10" />
            <span className="text-lg font-semibold">Sensei</span>
          </Link>
          <h1 className="mt-8 text-4xl leading-tight font-semibold tracking-tight">
            Grounded learning, one login away.
          </h1>
          <p className="text-muted-foreground mt-4 max-w-md">
            Pick a role to explore the workspace. Each role sees a different surface, matched to
            what they need to do.
          </p>
          <div className="mt-8 space-y-3">
            {DEMO_ACCOUNTS.map((a) => (
              <button
                key={a.email}
                type="button"
                onClick={() => {
                  setEmail(a.email);
                  setPassword(a.password);
                }}
                className="surface-card hover:border-primary/40 flex w-full items-center gap-3 p-4 text-left transition-colors"
              >
                <span className="bg-primary/12 text-primary flex size-10 items-center justify-center rounded-xl text-xs font-bold uppercase">
                  {a.role.slice(0, 2)}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold capitalize">
                    {a.role} · {a.name}
                  </p>
                  <p className="text-muted-foreground text-xs">
                    {a.email} · password: {a.password}
                  </p>
                </div>
                <ShieldCheck className="text-muted-foreground size-4" />
              </button>
            ))}
          </div>
        </motion.div>

        <motion.form
          onSubmit={onSubmit}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="surface-card mx-auto w-full max-w-md p-8"
        >
          <Link
            to="/"
            className="text-muted-foreground hover:text-foreground hover:border-primary/40 border-border inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors"
          >
            <ArrowLeft className="size-3.5" /> Back to home
          </Link>

          <h2 className="mt-2 text-2xl font-semibold tracking-tight">Sign in</h2>
          <p className="text-muted-foreground mt-1 text-sm">
            Use one of the demo accounts on the left, or type them in.
          </p>

          <div className="mt-6 space-y-4">
            <div>
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="student@sensei.ai"
                className="mt-1.5"
                required
              />
            </div>
            <div>
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="student"
                className="mt-1.5"
                required
              />
            </div>
          </div>

          <label className="mt-4 flex items-center gap-2.5 text-sm">
            <Checkbox
              checked={remember}
              onCheckedChange={(v) => setRemember(v === true)}
              aria-label="Remember me"
            />
            <span>
              Remember me
              <span className="text-muted-foreground block text-xs">
                Stay signed in after you refresh the page.
              </span>
            </span>
          </label>

          <Button type="submit" className="mt-6 w-full" disabled={submitting}>
            <LogIn className="size-4" /> Sign in
          </Button>

          <div className="mt-6 lg:hidden">
            <p className="text-muted-foreground mb-2 text-xs font-semibold tracking-widest uppercase">
              Demo accounts
            </p>
            <div className="space-y-2">
              {DEMO_ACCOUNTS.map((a) => (
                <button
                  key={a.email}
                  type="button"
                  onClick={() => {
                    setEmail(a.email);
                    setPassword(a.password);
                  }}
                  className="border-border hover:border-primary/40 w-full rounded-lg border px-3 py-2 text-left text-xs"
                >
                  <span className="font-semibold capitalize">{a.role}</span> · {a.email} /{" "}
                  {a.password}
                </button>
              ))}
            </div>
          </div>
        </motion.form>
      </div>
    </div>
  );
}
