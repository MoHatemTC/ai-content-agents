import { useEffect } from "react";
import { useNavigate } from "@tanstack/react-router";
import { Loader2 } from "lucide-react";
import { homeForRole, useAuth, type Role } from "@/contexts/AuthContext";
import type { Permission } from "@/constants";

interface RoleGateProps {
  /** Roles allowed through this page — checked via useAuth().hasRole(). */
  allow?: Role[];
  /** Optional permission that must also pass — checked via useAuth().can(). */
  permission?: Permission;
  children: React.ReactNode;
}

/**
 * Route guard. Access is decided by the AuthContext helpers only:
 * `hasRole()` for the allow-list and `can()` for the permission — never an
 * inline `role === ...` check, so permission logic stays in one place.
 */
export function RoleGate({ allow, permission, children }: RoleGateProps) {
  const { user, ready, hasRole, can } = useAuth();
  const navigate = useNavigate();

  const allowed =
    ready && user !== null && hasRole(allow ?? []) && (permission === undefined || can(permission));

  useEffect(() => {
    if (!ready) return;
    if (!user) {
      navigate({ to: "/login", search: { redirect: window.location.pathname } });
      return;
    }
    if (!hasRole(allow ?? []) || (permission !== undefined && !can(permission))) {
      navigate({ to: homeForRole(user.role) });
    }
  }, [ready, user, allow, permission, hasRole, can, navigate]);

  if (!allowed) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 className="text-muted-foreground size-5 animate-spin" />
      </div>
    );
  }
  return <>{children}</>;
}
