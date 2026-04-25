# Frontend Walkthrough — Vue 3 + Vue Flow

> The editor and dashboard live in `frontend/`. Standalone build, served as
> static assets in production. Vue 3 + Vite + Pinia + Vue Router + Vue Flow +
> TypeScript + Tailwind.

## Build & runtime

| Tool | Purpose | Defined in |
| ---- | ------- | ---------- |
| Vite 5 | Bundler + dev server. | `vite.config.ts` |
| Vue 3 (`<script setup>`) | Component framework. | every `*.vue` |
| Pinia | State management. | `src/stores/` |
| Vue Router 4 | SPA routing + auth guard. | `src/router/index.ts` |
| Vue Flow | Node-graph canvas. | `src/views/Editor.vue` |
| Tailwind CSS 4 | Utility-first styling. | `src/styles/tailwind.css` + `global.css` |
| Axios | API HTTP client. | `src/api/client.ts` |
| TypeScript 5 | Type safety. | `tsconfig.json` |
| Lucide | Icon set. | imported per-component |
| `class-variance-authority` + `tailwind-merge` | Utility-class composition. | `src/lib/utils.ts` |
| Vitest | Unit tests. | `vitest.config.ts` |
| Playwright | E2E tests. | `playwright.config.ts` |

`npm run dev` (Vite dev server, `:5173`), `npm run build` →
`frontend/dist/`. The backend serves `dist/` statically in production.

## Directory layout

```
frontend/src/
├── main.ts             # Entry — createApp + Pinia + Router.
├── App.vue             # Shell — TopBar + RouterView + Toasts + Tour.
├── router/
│   └── index.ts        # Routes + auth guard.
├── api/
│   ├── client.ts       # Axios instance + 401 redirect interceptor.
│   └── endpoints.ts    # One namespace per resource (workflows, executions, …).
├── stores/             # Pinia stores.
│   ├── auth.ts
│   ├── workflows.ts
│   ├── executions.ts
│   ├── credentials.ts
│   └── nodeTypes.ts
├── views/              # Route components.
│   ├── Login.vue
│   ├── Home.vue
│   ├── Editor.vue
│   ├── Executions.vue
│   ├── ExecutionDetail.vue
│   └── Credentials.vue
├── components/
│   ├── TopBar.vue
│   ├── NodePalette.vue
│   ├── NodeParameterForm.vue
│   ├── ExecutionPanel.vue
│   ├── CredentialEditor.vue
│   ├── TourOverlay.vue
│   ├── canvas/
│   │   └── WorkflowNodeCard.vue   # The card rendered for each node on canvas.
│   ├── forms/                     # (extension point for per-property-type renderers)
│   └── ui/                        # Design-system primitives.
│       ├── Button.vue Card.vue CardHeader.vue CardContent.vue
│       ├── Badge.vue Dialog.vue Input.vue Switch.vue
│       ├── Separator.vue Tooltip.vue Kbd.vue ToastContainer.vue
├── lib/
│   ├── utils.ts          # `cn(...)` (Tailwind class merger), debounce, formatters.
│   ├── toast.ts          # Toast emitter; consumed by ToastContainer.
│   ├── tour.ts           # Onboarding tour spec + driver.
│   ├── templates.ts      # Starter-workflow templates the editor offers.
│   ├── node-icons.ts     # Built-in node-type → Lucide icon mapping.
│   └── fieldExamples.ts  # Per-property-type example values for placeholders.
├── types/
│   └── api.ts            # Hand-written TS types mirroring server schemas.
└── styles/
    ├── tailwind.css      # @import "tailwindcss";
    └── global.css        # CSS variables, reset, scrollbar theming.
```

## Entry — `main.ts`

```ts
app.use(createPinia());
app.use(router);
app.mount("#app");
```

Three CSS imports: Tailwind, our globals, and Vue Flow's stylesheet (core +
default theme). Order matters — global comes after Tailwind so our overrides
win.

## Shell — `App.vue`

| Element | Purpose |
| ------- | ------- |
| `<TopBar v-if="auth.isAuthenticated" />` | Logo, project switcher, user menu. Hidden on `/login`. |
| `<RouterView />` | The current route. |
| `<ToastContainer />` | Bottom-right slide-in notifications. |
| `<TourOverlay />` | Driver-style guided onboarding overlay. |

Calls `auth.hydrate()` once at mount so a saved bearer token bootstraps the
session before any API call fires.

## Routing — `router/index.ts`

| Path | Name | View |
| ---- | ---- | ---- |
| `/login` | `login` | `Login.vue` (public) |
| `/` | `home` | `Home.vue` |
| `/workflows/:id` | `editor` | `Editor.vue` |
| `/executions` | `executions` | `Executions.vue` |
| `/executions/:id` | `execution-detail` | `ExecutionDetail.vue` |
| `/credentials` | `credentials` | `Credentials.vue` |
| `/:pathMatch(.*)*` | — | redirect to `/` |

Global `beforeEach` guard: any non-`public` route requires
`auth.isAuthenticated`; otherwise redirect to `/login?redirect=<original>`.

## API client — `api/client.ts`

Single axios instance per page load. Interceptors:

- **Request** — pulls `weftlyflow.access_token` from `localStorage`, sets
  `Authorization: Bearer …`. Adds `X-Weftlyflow-Project` from
  `weftlyflow.project_id` if set.
- **Response** — on `401`: clear stored token + project, redirect to
  `/login?redirect=…` (skipping when we're already on `/login` or the
  failing call *is* `/auth/login`, to avoid a redirect loop).

Helper `extractErrorMessage(err)` reads `error.response.data.detail` (FastAPI's
default) and falls back to the axios message.

## API endpoints — `api/endpoints.ts`

One TS namespace per server router:

```ts
export const workflows = {
  list:     () => http.get<Workflow[]>("/api/v1/workflows"),
  get:      (id: string) => http.get<Workflow>(`/api/v1/workflows/${id}`),
  create:   (body: WorkflowWrite) => http.post<Workflow>("/api/v1/workflows", body),
  update:   (id: string, body: WorkflowWrite) => http.put<Workflow>(`/api/v1/workflows/${id}`, body),
  remove:   (id: string) => http.delete(`/api/v1/workflows/${id}`),
  activate:   (id: string) => http.post(`/api/v1/workflows/${id}/activate`),
  deactivate: (id: string) => http.post(`/api/v1/workflows/${id}/deactivate`),
  run:        (id: string, body?: RunWorkflowRequest) => http.post(`/api/v1/workflows/${id}/run`, body),
};
```

Same shape for `executions`, `credentials`, `nodeTypes`, `auth`.

## Stores — `src/stores/`

| Store | State | Notable actions |
| ----- | ----- | --------------- |
| `auth` | `token`, `user`, `project_id` | `hydrate()`, `login(email, password, mfa?)`, `logout()`, `isAuthenticated` (getter). |
| `workflows` | `list[]`, `current`, `loading`, `dirty` | `fetchAll()`, `fetchOne(id)`, `save()`, `activate()`, `deactivate()`, `run()`. |
| `executions` | `list[]`, `current`, `streamSocket` | `fetchAll(workflowId?)`, `open(id)`, `subscribe(id)` (WebSocket), `cancel(id)`. |
| `credentials` | `list[]`, `types[]` | `fetchAll()`, `fetchTypes()`, `create()`, `update()`, `remove()`, `test(id)`. |
| `nodeTypes` | `list[]` keyed `(type, version)` | `fetchAll()`. Cached for the editor session. |

Each store is a `defineStore(...)` with `state`, `getters`, `actions`. State
mutations always go through actions to keep devtools traces meaningful.

## Views — route components

### `Login.vue`
Email + password form. Optional MFA prompt appears after the first POST when
the server replies `401 mfa_required`. On success: stores tokens via the
`auth` store and routes to `?redirect=` or `/`.

### `Home.vue`
Dashboard grid. Recent workflows, recent executions, quick-create cards
(blank workflow / pick a template from `lib/templates.ts`).

### `Editor.vue` — the heart of the UI
The most complex view. Holds the workflow in memory (`reactive` arrays for
nodes + connections), pushes the whole thing on Save. Components used:

- `<VueFlow>` — the canvas. `nodeTypes` is set to `{ default: WorkflowNodeCard }`
  so every node renders with the custom card.
- `<Background>` / `<Controls>` / `<MiniMap>` — Vue Flow extras.
- `<NodePalette>` — left rail. Drag-out source for adding nodes.
- `<NodeParameterForm>` — right rail. Renders the selected node's parameters
  using its `NodeSpec.properties`. Each property type maps to an `Input`,
  `Switch`, `Select`, code editor, etc.
- `<ExecutionPanel>` — bottom pane. Shows the live run as it streams in,
  per-node items with the lineage view.
- `<Dialog>` — Save shortcut help, keybinding cheatsheet, confirm-deactivate.

Keyboard shortcuts: ⌘S save, ⌘Enter execute, ⌘D duplicate node, Del remove,
⌘Z / ⌘⇧Z undo / redo (local history), `?` cheatsheet.

### `Executions.vue` + `ExecutionDetail.vue`
Filterable execution table; click a row → detail with a re-rendered Vue Flow
canvas showing per-node status, items, errors. Streams live updates via the
WebSocket subscribed in `executions.subscribe(id)`.

### `Credentials.vue`
Card grid of saved credentials grouped by type, with create/edit dialogs
that render the credential type's `fields` (loaded from `nodeTypes` /
`credentials.types`). The "Test credential" button POSTs to
`/api/v1/credentials/{id}/test`.

## Components

### Canvas

`WorkflowNodeCard.vue` — a Vue Flow custom node. Shows:

- The node's icon (resolved via `lib/node-icons.ts`).
- Title (the user-set `name`) + subtitle (resolved via `node.spec.subtitle_template`).
- Status badge — synced from the live execution stream.
- Input + output handles for each `Port`. Different visual treatment for
  `ai_*` ports.
- Selection ring + hover lift.

### Layout / chrome

| Component | Renders |
| --------- | ------- |
| `TopBar.vue` | Logo, primary nav, project switcher, user menu, Tour button. |
| `NodePalette.vue` | Left rail. Search + categorized list of node types. Drag to canvas. |
| `NodeParameterForm.vue` | Right rail. Property-type → input dispatch. Includes the credential picker. |
| `ExecutionPanel.vue` | Bottom drawer. Run-data viewer with item table, JSON tree, lineage. |
| `CredentialEditor.vue` | Modal form rendered from a credential type spec. |
| `TourOverlay.vue` | Spotlight overlay for `lib/tour.ts`-driven onboarding steps. |

### Design-system primitives — `components/ui/`

Tiny wrappers, each one `<script setup>` + minimal Tailwind. The pattern
mirrors shadcn/ui — primitives compose into views without bringing in a
heavy component library.

| File | Renders |
| ---- | ------- |
| `Button.vue` | `cva` variants: `default`, `secondary`, `destructive`, `ghost`, `outline`. Sizes `sm`/`md`/`lg`/`icon`. |
| `Card.vue`, `CardHeader.vue`, `CardContent.vue` | Composable surface. |
| `Badge.vue` | Status pill with semantic variants. |
| `Dialog.vue` | Modal shell with focus trap + ESC/click-outside dismiss. |
| `Input.vue` | Text input with label + error slot. |
| `Switch.vue` | Toggle. |
| `Separator.vue` | Hairline. |
| `Tooltip.vue` | Hover tooltip via `Floating UI`-style positioning. |
| `Kbd.vue` | Renders a keyboard shortcut chip. |
| `ToastContainer.vue` | Reads from `lib/toast.ts` queue, slides notifications in. |

## Lib utilities

| File | Exports |
| ---- | ------- |
| `utils.ts` | `cn(...classes)` — `clsx + tailwind-merge`. Plus `debounce`, `formatRelative`, `formatBytes`. |
| `toast.ts` | `toast.success/info/error/warning(message, opts?)`. Backed by a tiny reactive queue. |
| `tour.ts` | `EDITOR_TOUR` step list + `startTour(name)` driver. Persists "seen" state in `localStorage`. |
| `templates.ts` | Hard-coded starter workflows the Home view offers. |
| `node-icons.ts` | Map: node `type` → Lucide icon component. Falls back to a generic icon. |
| `fieldExamples.ts` | Per-property-type placeholder text and example dropdowns. |

## Types — `types/api.ts`

Hand-written TS interfaces for every server schema:

`Workflow`, `WorkflowNode`, `WorkflowConnection`, `Execution`,
`ExecutionDetail`, `NodeRun`, `Item`, `NodeType`, `Port`, `PropertySchema`,
`Credential`, `CredentialType`, `User`, `LoginResponse`.

Kept in sync with `src/weftlyflow/server/schemas/*` by hand. There is a
ticket to auto-generate from the OpenAPI spec; until then, server-side
schema changes require a manual mirror here.

## Styling

`global.css` defines the dark/light tokens and the editor-specific surfaces:

```css
:root { --wf-bg: #0b1020; --wf-surface: #0f172a; --wf-fg: #e2e8f0; }
@media (prefers-color-scheme: light) {
  :root { --wf-bg: #f8fafc; --wf-surface: #ffffff; --wf-fg: #0f172a; }
}
```

Tailwind 4 is the default. `cn(...)` (in `lib/utils.ts`) is the only helper
needed for conditional class composition.

## Frontend ↔ backend WebSocket

The execution stream uses a plain `WebSocket` (no socket.io, no SSE):

```ts
const ws = new WebSocket(`${wsScheme}://${host}/api/v1/executions/${id}/stream`);
ws.onmessage = (e) => updateRunData(JSON.parse(e.data));
```

The token is sent as a `?token=` query param (browsers can't set custom
WebSocket headers from the client). The router enforces a short window
between issue + first frame so the token doesn't sit in URLs longer than
needed.

## Cross-references

- The server side of the WebSocket and the events emitted to it:
  [Server & DB](backend/server-db.md).
- The end-to-end picture (UI → API → engine → UI):
  [Data flow](data-flow.md).
- "I see this symbol in `types/api.ts` — what's it called server-side?":
  [Source backtracking](source-backtrack.md).
