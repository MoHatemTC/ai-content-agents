# Routes

TanStack Start uses **file-based routing**. Every `.tsx` file in this directory
defines a route. Do **not** create `src/pages/`, `src/routes/_app/index.tsx`, or
`app/layout.tsx` — those are Next.js / Remix conventions. The only root layout
is `src/routes/__root.tsx`.

## Conventions

| File                     | URL                                                     |
| ------------------------ | ------------------------------------------------------- |
| `index.tsx`              | `/`                                                     |
| `about.tsx`              | `/about`                                                |
| `users/index.tsx`        | `/users`                                                |
| `users/$id.tsx`          | `/users/:id` (dynamic — bare `$`, no curly braces)      |
| `posts/{-$category}.tsx` | `/posts/:category?` (optional segment)                  |
| `files/$.tsx`            | `/files/*` (splat — read via `_splat` param, never `*`) |
| `_layout.tsx`            | layout route (renders children via `<Outlet />`)        |
| `__root.tsx`             | app shell — wraps every page; preserve `<Outlet />`     |

`routeTree.gen.ts` is auto-generated. Don't edit it by hand.

## Routes in this app

| File                     | URL                                   | Purpose                                   |
| ------------------------ | ------------------------------------- | ----------------------------------------- |
| `index.tsx`              | `/`                                   | Redirect shell (to `/home`)               |
| `__root.tsx`             | (root)                                | App shell — mounts all providers          |
| `login.tsx`              | `/login`                              | Sign in                                   |
| `home.tsx`               | `/home`                               | Dashboard                                 |
| `studio.tsx`             | `/studio`                             | Upload + generate console                 |
| `workspace.tsx`          | `/workspace`                          | Workspace CRUD / switch                   |
| `library.tsx`            | `/library`                            | Uploaded documents                        |
| `generate.tsx`           | `/generate`                           | Question / flashcard generation           |
| `chat.$chatId.tsx`       | `/chat/:chatId`                       | Agent chat thread                         |
| `review.tsx`             | `/review`                             | Review workflow + export                  |
| `pipeline.tsx`           | `/pipeline`                           | RAG pipeline visualisation                |
| `agents.tsx`             | `/agents`                             | Agent catalogue                           |
| `history.tsx`            | `/history`                            | Generation history                        |
| `analytics.tsx`          | `/analytics`                          | Analytics dashboards                      |
| `settings.tsx`           | `/settings`                           | Profile + preferences                     |
| `admin.tsx`              | `/admin`                              | Admin (role-gated)                        |
| `reopen.$generationId.tsx`| `/reopen/:generationId`              | Re-open a past generation                 |
| `sitemap[.]xml.ts`       | `/sitemap.xml`                        | SEO sitemap                               |
