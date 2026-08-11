## Description

<!-- What does this change do, and why? Link the issue if there is one. -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor (no behaviour change)
- [ ] Documentation
- [ ] Dependency update

## Checklist

- [ ] `npm run typecheck` passes (0 errors)
- [ ] `npm run lint` passes (0 errors)
- [ ] `npm run build` passes
- [ ] UI changes go through services — no direct `src/api` / `src/mock` imports
- [ ] Role checks use `useAuth().can()` / `<RoleGate>`, never inline `role === "x"`
- [ ] Workspace-owned data read from `useWorkspace().data`
- [ ] Endpoint added → `src/api/paths.ts` + contracts + api module + service + docs updated
- [ ] Docs updated (`README.md` / `docs/` as needed)

## Testing

<!-- How did you verify this change? Screenshots, curl output, manual test steps. -->
