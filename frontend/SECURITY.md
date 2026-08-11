# Security Policy

Sensei handles educational content and user accounts. We take security
seriously and appreciate responsible disclosure.

## Reporting a vulnerability

Please **do not open a public issue** for security problems. Instead, email the
maintainers directly, or report privately via GitHub's Security Advisories.

In your report, include:

1. The affected repository (frontend `sensei-ai` or backend `ai-content-agents`).
2. The affected endpoint, file, or dependency (with a version if known).
3. A minimal reproduction or description of the impact.

You can expect an acknowledgement within 3 business days, and a timeline for a
fix once the issue is triaged.

## Scope

- **Frontend** — this repository: client-side secrets handling, auth token
  storage, XSS/injection surfaces, dependency advisories.
- **Backend** — the [ai-content-agents](https://github.com/MoHatemTC/ai-content-agents)
  repository: JWT verification, RLS/authorization, file upload handling,
  model API key handling.

## Security posture

- Only **publishable** keys (e.g. the Supabase anon key) ever reach the
  browser. JWT secrets and model API keys live server-side only.
- Workspace access is enforced **server-side** (RLS + role checks); the client
  never grants access by itself.
- `src/api/http.ts` is the single network path and the single token holder.
- Supabase migrations enable Row Level Security on user-owned tables.
