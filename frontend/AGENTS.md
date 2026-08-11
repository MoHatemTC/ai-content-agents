# Agent Guidance

Instructions for AI coding agents working in this repository. Human developers
should read [CONTRIBUTING.md](CONTRIBUTING.md).

## Repository conventions

- **Branches**: keep the working branch in a green, buildable state at all
  times. Do not rewrite or force-push published git history.
- **Commits**: small, focused commits with descriptive messages. The working
  branch is expected to build and type-check after every commit.

## Engineering principles

1. UI never imports `src/api` or `src/mock` — always go through the service
   layer (`src/services`).
2. Services are the only place backend behaviour changes. When FastAPI or
   Supabase lands, only `src/api/*` and the relevant service internals change.
3. Role checks go through `useAuth().can()` /
   `<RoleGate>` — never inline `role === "admin"` in a component.
4. Workspace-owned data is read from `useWorkspace().data`, already scoped to
   the active workspace. Pages never filter by workspace themselves.
5. All network access flows through `src/api/http.ts`. There is exactly one
   access-token holder and one error-shaping path.

## Getting started

```bash
npm install
npm run dev        # http://localhost:8080 (mock mode on by default)
```

## Verification

```bash
npm run typecheck  # tsc --noEmit
npm run lint       # ESLint + Prettier
npm run build      # production build (client + server/bundle)
```
