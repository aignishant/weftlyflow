# UI walkthrough — the complete user guide

A page-by-page tour of the Weftlyflow web app. This is the right place to
start if you just signed in for the first time and want to know *what each
screen does*, *what every button means*, and *how to get from zero to a
running automation*.

!!! tip "Looking for something specific?"
    - Building your first workflow? Jump to **[The editor](#the-editor-workflowsid)**.
    - Need to add a Slack token or API key? See **[Credentials](#credentials-credentials)**.
    - Want to see what ships out of the box? **[Template gallery](#the-template-gallery)** lists all 22.
    - Keyboard-driven? There's a **[shortcut cheat sheet](#keyboard-shortcut-reference)**.

---

## Table of contents

1. [The big picture](#the-big-picture)
2. [Signing in](#signing-in-login)
3. [Global chrome — the top bar](#global-chrome-the-top-bar)
4. [Dashboard — the Home screen](#dashboard-the-home-screen)
5. [The editor (`/workflows/:id`)](#the-editor-workflowsid)
6. [Executions — run history](#executions-run-history)
7. [Execution detail](#execution-detail-executionsid)
8. [Credentials](#credentials-credentials)
9. [The template gallery](#the-template-gallery)
10. [Nodes — the building blocks](#nodes-the-building-blocks)
11. [Credential types](#credential-types)
12. [Tours and help](#tours-and-help)
13. [Keyboard shortcut reference](#keyboard-shortcut-reference)
14. [Data model cheat sheet](#data-model-cheat-sheet)
15. [Troubleshooting](#troubleshooting)

---

## The big picture

Weftlyflow is a **node-based workflow automation platform**. You draw a
graph of steps (pull from an API, transform data, send to Slack, …),
press **Run**, and the engine executes it. Triggers (schedule, webhook,
chat, manual) decide *when* a workflow runs. **Credentials** hold the
secrets your nodes need. **Executions** record every run with per-node
inputs, outputs, and errors.

The UI has six pages:

| Page | Route | What it's for |
|---|---|---|
| Login | `/login` | Authentication |
| Dashboard | `/` | Home screen — stats, templates, integrations, workflow list |
| Editor | `/workflows/:id` | Build and run a single workflow |
| Executions | `/executions` | Every run, newest first |
| Execution detail | `/executions/:id` | Per-node output of one run |
| Credentials | `/credentials` | Encrypted secret vault |

Everything else is chrome: the top navigation bar, the Help menu with
tours, and toast notifications.

---

## Signing in (`/login`)

![login]

**Fields:**

- **Email** (`data-testid="login-email"`) — the email you registered with.
- **Password** (`data-testid="login-password"`) — argon2-hashed server-side.
- **Sign in** button (`data-testid="login-submit"`) — disabled while the
  request is in flight; shows `Signing in…` during the call.

**What happens on success:**

1. The server returns a bearer token + project ID.
2. Both are stored in `localStorage` under
   `weftlyflow.access_token` and `weftlyflow.project_id`.
3. Node-type catalog pre-loads (so the editor opens instantly later).
4. You're redirected to the `?redirect=` query param if present, else
   the Home dashboard.

**Errors** appear inline in a red band (`data-testid="login-error"`) with
the specific message from the API — e.g. *"Invalid credentials"* or
*"Connection refused"*.

**Auto-logout:** any API call returning **401 Unauthorized** automatically
clears the token and redirects you back here with
`?redirect=<original-path>`, so you land back where you were once you
sign in again.

---

## Global chrome — the top bar

The dark gradient strip across the top of every authenticated page.

```
┌─────────────────────────────────────────────────────────────────────┐
│ [⬢] Weftlyflow   Workflows · Executions · Credentials       [A] [?] [⎋] │
└─────────────────────────────────────────────────────────────────────┘
```

From left to right:

- **Logo + brand** — click to go Home. The logo is an animated
  conic-gradient mark.
- **Nav links** — `Workflows` (Home), `Executions`, `Credentials`.
  The active link gets a gradient pill and glow.
- **User avatar** — first letter of your email, colored. Hover to see
  the full address.
- **Help button** (`data-testid="help-menu"`) — opens the tour replay
  menu (see [Tours and help](#tours-and-help)).
- **Logout** (`data-testid="logout"`) — clears your session and sends
  you back to `/login`.

---

## Dashboard — the Home screen

The landing page after login. Centered column, max-width 1180px. It is
divided into **eight sections** stacked vertically.

### 1. Hero card

`data-testid="hero-card"`

- **Time-of-day greeting** — "Good morning, `<you>`" changes with the
  clock (morning / afternoon / evening).
- **System-status badge** — polls `/healthz` + `/readyz` every 15s.
    - 🟢 *All systems operational* — green, OK.
    - 🟡 *Degraded* — API up, background worker struggling.
    - 🔴 *Down* — API unreachable.
- **One-line workflow launcher** — type a name in the input
  (`data-testid="workflow-name"`) and hit **Create workflow**
  (`data-testid="workflow-create"`). You land in the editor with a
  single Manual Trigger node ready to wire.

### 2. Quick actions

`data-testid="quick-actions"`

Four tinted cards for the most common tasks:

| Tile | Goes to |
|---|---|
| ➕ New workflow | Home (focuses the launcher) |
| 🔑 Add credential | `/credentials` |
| ▶ Recent runs | `/executions` |
| 📦 Browse nodes | Scrolls to the Integrations panel |

### 3. Stat cards

`data-testid="stats-row"`

Four KPIs, live-updated after every run:

| KPI | What it counts |
|---|---|
| **Workflows** | Total count + total nodes across all of them |
| **Active** | How many have triggers currently armed |
| **Runs** | Last 24 h and all-time |
| **Success rate** | `finished & success / finished total` as % |

### 4. Template gallery

`data-testid="templates-panel"`

22 pre-built automations you can install with one click. See
[The template gallery](#the-template-gallery) for the full catalog.
Each card has:

- A category-tinted icon and tag (DevOps / AI / Data / Growth / …).
- Workflow name and a one-sentence description.
- Tech-stack chips (`schedule · HTTP · OpenAI · Slack`, etc.).
- A **Use template** button
  (`data-testid="template-install-{id}"`).

Clicking **Use template** POSTs the complete graph to
`/api/v1/workflows`, shows a green toast, and drops you in the editor.

### 5. Integrations gallery

`data-testid="integrations-panel"`

A searchable grid of every installable connector (100+ nodes). Above the
grid is a **triggers strip** listing every trigger type (manual,
schedule, webhook, chat, email). The search box filters by node
display name or slug in real time.

### 6. Activity chart + recent runs

- **14-day bar chart** — stacked success (green) + error (red) bars.
  Scan for a red streak; click through to Executions to investigate.
- **Recent runs list** — the latest 8 executions with status badge,
  workflow name, mode (manual/webhook/scheduled), and a relative
  time ("4 min ago"). Click any row to open its execution detail.

### 7. Status mix + credentials + node palette summary

Three small tiles in a row:

- **Status donut** — counts by status (success / error / running /
  waiting) with a legend.
- **Credentials preview** — your 6 most recently updated credentials.
  Click **Manage →** to go to the full list.
- **Node palette summary** — per-category bar chart (trigger · core ·
  integration · ai) with a footer row of 8 sample chips.

### 8. Workflows grid

`data-testid="workflow-table"`

A tile grid of every workflow in the current project.

**Per-tile contents:**

- Status dot — green if **Active**, gray if inactive.
- Workflow name — click to open in the editor.
- Trash button — confirms then deletes.
- Meta chips — node count, run count, up to 2 tags.
- Footer — **Active**/**Inactive** badge + **Open →** link.

A search box at the top does a live `name.toLowerCase().includes(q)`
filter.

---

## The editor (`/workflows/:id`)

Where the real work happens. Three panels and a mini top bar.

```
┌───────────────────────────────────────────────────────────────────────┐
│ ← Back │ workflow-name [●unsaved]          Save  [Inactive ▯] [? ⌨] │
├──────────────┬────────────────────────────────────┬──────────────────┤
│              │                                    │                  │
│   PALETTE    │             CANVAS                 │    INSPECTOR     │
│              │                                    │                  │
│ ┌──────────┐ │   [trigger]──>[http]──>[slack]     │  ▣ HTTP request  │
│ │ Search…  │ │                   \                │  Node name       │
│ └──────────┘ │                    >[no_op]        │  ─ Parameters ─  │
│              │                                    │  URL             │
│  ▾ trigger   │                                    │  Method          │
│  ▾ core      │                                    │  …               │
│  ▾ integration│                                   │                  │
│  ▾ ai        │                                    │                  │
│              │                                    │                  │
├──────────────┴────────────────────────────────────┴──────────────────┤
│                    ▼  Execution panel (collapsible)                  │
└───────────────────────────────────────────────────────────────────────┘
```

### Top bar of the editor

From left to right:

- **Back** (`editor-back`) — returns to the dashboard. Unsaved changes
  trigger a confirm dialog.
- **Workflow name** (`editor-name`) — editable inline. Empty falls
  back to "Untitled workflow".
- **Unsaved indicator** — pulsing dot + `unsaved changes` label when
  `dirty === true`.
- **Save** (`editor-save`) — ⌘S also triggers it. Shows `Saving…` and
  then `Saved ✓` briefly.
- **Active toggle** (`editor-toggle-active`) — flips the workflow's
  `active` flag. Turns *on* scheduled / webhook / chat triggers.
- **Shortcuts** (`editor-shortcuts`) — opens the shortcut modal
  (also openable with `?`).

### Left — node palette

`data-testid="node-palette"`

- **Search** (`palette-search`) — 100+ nodes, filter by name or type
  slug. Jump here from anywhere with `⌘K` / `Ctrl+K`.
- **Collapsible categories** — ordered **trigger → core → integration
  → ai**, then alphabetical. Each header shows a count
  (`trigger (6)`).
- **Keyboard nav inside the palette:**
    - `↓/↑` — move the highlight through the visible filtered list.
    - `Enter` — add the highlighted node to the canvas.
    - `Esc` — clear the search.
- Clicking any node *or* pressing Enter drops it onto the canvas.

### Middle — canvas

`class="canvas-area"`

Built on **Vue Flow**. Pan with middle-mouse drag or two-finger
scroll; zoom with scroll-wheel; the bottom-left Controls widget
provides + / – / fit / lock buttons. A minimap in the bottom-right
gives a bird's-eye view.

**Operations on the canvas:**

| Action | How |
|---|---|
| Add a node | Click it in the palette or drag onto canvas |
| Move a node | Drag by its body |
| Connect two nodes | Drag from the source handle (right dot) onto the target handle (left dot) |
| Select a node | Click it — it highlights, inspector opens |
| Delete a node | Select + `Delete`/`Backspace`, or click the trash icon in the inspector |
| Rename a node | Edit the name input in the inspector |

**Empty-state overlay** (`canvas-empty-state`) shows when there are
no nodes, with the hint *"Pick a trigger from the palette on the
left, or press ⌘K to focus search."*

### Right — parameter inspector

`class="inspector"`

When you select a node, the inspector renders a rich form generated
from the node type's schema.

**Header card:**

- Type-initial badge (2-letter, deterministic color).
- Editable **node name** (`node-name`).
- **Delete** button (`node-delete`).
- Metadata row: category · node type slug.
- One-line description from the node definition.
- Live counter: **X / Y parameters set** plus a credential-count pill.

**Credentials section** (collapsible):

- One entry per credential slot declared by the node type.
- Red dot = required, dropdown to pick an existing credential of the
  matching type. Empty-state warning if no credential of the right
  type exists yet.

**Parameters section** (collapsible):

Every field in `NodeType.properties` gets a row. Field types and
their rendering:

| Type | UI |
|---|---|
| `string` | text input |
| `number` | number input (coerced on blur) |
| `boolean` | gradient toggle switch |
| `options` | dropdown |
| `json` | monospace textarea with live parse |
| `expression` | text input with subtle glow (expressions `={{ … }}` are evaluated at run time) |
| `password` / sensitive | masked input |

Every field also offers:

- **Example line** (`.f-example`) — a lightbulb icon plus a sample
  value. E.g. `e.g. https://api.example.com/v1/orders`.
- **Suggestion chips** (`.f-chips`) — clickable tokens that drop
  into the field when clicked. E.g. for a Cron field:
  `0 * * * * *`, `0 */5 * * * *`, `0 0 9 * * 1-5`.
- **Inline tip** (`.f-help-btn`) — the `?` next to the label toggles
  an expandable tip card with syntax hints, expression helpers
  (`{{ $json.fieldName }}`), and common pitfalls.

### Bottom — execution panel

`data-testid="execution-panel"`

A collapsible bottom sheet that shows the last run of the currently
open workflow. Header holds the **Run** button (▶) and overall
status.

Each node that ran gets a card:

- Status badge (success / error / running / waiting).
- Item count and execution time in ms.
- Click to expand — the first item of the last run pretty-printed
  as JSON.
- If a run errored, the error message is shown prominently in red.

### Keyboard shortcuts (editor)

| Keys | Action |
|---|---|
| ⌘S / Ctrl+S | Save the workflow |
| ⌘Enter / Ctrl+Enter | Execute the workflow |
| ⌘K / Ctrl+K | Focus the palette search |
| ? | Open the shortcuts modal |
| Delete / Backspace | Delete the selected node (when not typing) |

---

## Executions — run history

`/executions`

A single table of every run, newest first.

**Columns:**

| Column | Contents |
|---|---|
| Id | Execution ID, monospace, links to detail |
| Workflow | `workflow_id` that ran |
| Mode | `manual`, `scheduled`, `webhook`, `chat`, `trigger` |
| Status | Badge — `success` · `error` · `running` · `waiting` |
| Started | Local datetime |
| Finished | Local datetime, or `—` if still running |

Empty state: *"No executions yet — run a workflow to see its history
here."*

A **Refresh** button in the header re-pulls the list.

---

## Execution detail (`/executions/:id`)

Two stacked cards.

### Card 1 — metadata

- Execution ID (monospace) + status badge
- 2-column grid of meta:
    - Workflow (ID, monospace)
    - Mode
    - Started (formatted)
    - Finished (formatted, or `—`)
- Back link: **← Back to list**

### Card 2 — run data (`data-testid="run-data-detail"`)

One collapsible block per node that ran. Expanding reveals each
`Run` for that node with:

- Execution time (ms)
- Output `items` as pretty JSON
- Error payload if the run failed

This is where you debug — click through the failing node, read the
error, jump back to the editor, fix, re-run.

---

## Credentials (`/credentials`)

The secret vault. Everything here is **Fernet-encrypted at rest** and
never surfaces in logs or UI plaintext.

### The list

`data-testid="credentials-table"`

| Column | Contents |
|---|---|
| Name | Human label |
| Type | Slug, monospace (e.g. `weftlyflow.bearer_token`) |
| Test | **Test** button + inline badge with the result |
| Actions | **Delete** (confirms) |

Rows carry `data-credential-id={id}` for UI automation.

### Creating / editing

Click **New credential** (`data-testid="new-credential"`) to open the
editor modal.

Inside the modal:

1. **Name** — what you'll call it in the editor ("Prod Slack", "Stripe
   test key").
2. **Type** — dropdown with every supported credential type.
3. **Dynamic fields** — every type has its own schema; sensitive
   fields render as masked inputs.
4. **Submit** — POSTs to `/api/v1/credentials`, encrypts on the
   server, and refreshes the list.

### Testing a credential

Click **Test** — the server attempts a minimal call with the stored
credentials:

- ✅ green badge `ok` — the credential works.
- ❌ red badge — the failure reason (`401`, `timeout`,
  `invalid cluster`, …).

### Using credentials in a node

In the editor's parameter form, any node that requires a credential
shows a dropdown populated with credentials of the right *type*. If
none exist for that type, an inline warning links you to the
Credentials page.

---

## The template gallery

22 complete automations ship with Weftlyflow. Clicking **Use template**
creates a real workflow you can customise. Every AI node uses either
`response_format: "json_object"` (OpenAI) or a strict JSON system
prompt (Claude), followed by `guard_schema_enforce` — so outputs are
structured, typed, and safe to chain.

### Daily utility

| # | Template | Stack |
|---|---|---|
| 1 | **Uptime guard** | schedule → HTTP health check → `if` status≠200 → Slack `#incidents` / no-op |
| 2 | **Daily morning briefing** | 8 am weekday → weather API + HN top 5 → GPT 4-line brief → Slack DM |
| 3 | **Lead capture** | form webhook → normalise → *parallel* Sheets + HubSpot + Gmail welcome |
| 4 | **Weekly metrics report** | Mon 9 am → fetch KPIs → WoW deltas → GPT exec summary → `#leadership` |
| 5 | **Stripe → Slack notifier** | Stripe webhook → shape → `if` amount ≥ 500 → `#sales-vip` / `#orders` |
| 6 | **Hourly ETL → Airtable** | schedule → API fetch → batch(50) → transform → rename-keys → Airtable upsert |

### Popular AI agent flows

| # | Template | Stack |
|---|---|---|
| 7 | **AI email triage agent** | every 15 min Gmail list → GPT classify (URGENT · CUSTOMER · SPAM · ARCHIVE) + draft → `switch` → Slack / draft / trash / archive |
| 8 | **AI meeting notes agent** | transcript webhook → chunk → Claude JSON `{title,summary,decisions,actions}` → schema guard → Notion + Slack |
| 9 | **AI support auto-responder** | ticket webhook → jailbreak guard → embed → Qdrant → Claude draft → PII redact → `#support-queue` for review |
| 10 | **RAG chat assistant** | chat trigger → jailbreak guard → embed → Qdrant + memory-window → GPT-4o → schema guard → reply |

### Advanced professional

| # | Template | Stack |
|---|---|---|
| 11 | **AI code review agent** | GitHub PR webhook → filter → fetch diff → Claude JSON review → schema guard → post PR review |
| 12 | **Calendar prep briefing** | weekday 7 am → Gmail invites → GPT per-meeting prep JSON → Slack DM |
| 13 | **Social content repurposer** | blog webhook → Claude `{tweets[5],linkedin,hashtags}` → schema guard → *parallel* Buffer posts |
| 14 | **Competitor price monitor** | daily scrape → HTML parse → transform diff → `if` changed → Slack / no-op |
| 15 | **Customer feedback analyzer** | Intercom webhook → GPT sentiment/category JSON → schema guard → `switch` → `#cs-urgent` / wins / feedback DB |
| 16 | **Churn risk predictor** | daily event pull → batch → weighted risk score → filter `risk>70` → HubSpot tag + CSM ping |
| 17 | **Expense receipts OCR** | hourly Gmail search → Claude extract JSON → schema guard → Google Sheets ledger |
| 18 | **Weekly SEO audit** | Mon 6 am → PageSpeed/Lighthouse → GPT interpret JSON → Notion page + `#growth` |
| 19 | **Sales pipeline digest** | weekday 8:30 am → HubSpot deals → aggregate by stage → GPT exec headline → `#sales-daily` |
| 20 | **Incident postmortem drafter** | PagerDuty resolved → logs → Claude 5-section JSON → schema guard → Notion + SRE review |
| 21 | **Smart lead scoring** | HubSpot new-contact → Clearbit enrich → GPT `{score,tier,reasoning}` → HubSpot update → `if` Tier A → hot-lead alert |
| 22 | **Daily trend summariser** | weekday 8:30 am → Reddit + HN merge → GPT themes JSON → `#marketing` |

All 22 are defined in `frontend/src/lib/templates.ts` — the `build()`
method of each returns a full `WorkflowCreate` payload.

---

## Nodes — the building blocks

Every node in Weftlyflow belongs to exactly one of four categories:

| Category | Role | Example nodes |
|---|---|---|
| **trigger** | Starts a workflow | `manual_trigger`, `schedule_trigger`, `webhook_trigger`, `trigger_chat` |
| **core** | Control flow, data shaping, HTTP | `http_request`, `set`, `if`, `switch`, `filter`, `transform`, `merge`, `split_in_batches`, `no_op`, `stop_and_error`, `text_splitter`, `rename_keys`, `datetime_ops`, `evaluate_expression`, `html_parse`, `function_call` |
| **integration** | SaaS, DBs, cloud APIs (~80 nodes) | `slack`, `gmail`, `notion`, `airtable`, `stripe`, `hubspot`, `google_sheets`, `github`, `linear`, `jira`, `asana`, `salesforce`, `shopify`, `telegram`, `discord`, `twilio`, `sendgrid`, `aws_s3`, `mongodb_atlas`, `snowflake`, `supabase`, `elasticsearch`, `intercom`, `mailchimp`, `pagerduty`, … |
| **ai** | LLMs, embeddings, vector stores, guards, agents | `openai`, `anthropic`, `ollama`, `mistral`, `google_genai`, `embed_openai`, `embed_local`, `vector_qdrant`, `vector_pinecone`, `vector_chroma`, `vector_pgvector`, `vector_memory`, `memory_window`, `memory_buffer`, `memory_summary`, `guard_pii_redact`, `guard_jailbreak_detect`, `guard_schema_enforce`, `agent_react`, `agent_tool_dispatch`, `agent_tool_result`, `chat_respond` |

**Totals (live):** Weftlyflow currently registers **127** built-in
node types. You can confirm at any time with
`GET /api/v1/node-types` — the palette pulls from the same endpoint.

### Anatomy of a node type

Every node type advertises:

- `type` — unique slug (`weftlyflow.http_request`).
- `display_name` — human label.
- `description` — one-sentence tooltip.
- `category` — trigger / core / integration / ai.
- `version` — `type_version`; old workflows keep executing on their
  pinned version.
- `properties[]` — the fields shown in the inspector. Each property
  has `name`, `type`, `required`, `default`, `description`,
  `options` (for dropdowns), `placeholder`, `type_options`.
- `credentials[]` — the slots the node needs (e.g. the Slack node
  declares a slot of type `weftlyflow.slack_oauth`).
- `outputs[]` — named output ports (`main`, `true`/`false` for `if`,
  arbitrary labels for `switch`, etc.).

### Control-flow nodes worth knowing

- **if** — binary branch, exposes `true` and `false` output ports.
  Condition is a boolean expression: `={{ $json.status === 200 }}`.
- **switch** — N-way branch with named ports. Each rule has a
  condition; items that match none go to `fallback`.
- **filter** — drops items that don't match the condition (no
  branch).
- **merge** — combines parallel branches. Modes: `merge_by_index`,
  `append`, `merge_by_key`.
- **split_in_batches** — iterates large lists in chunks so
  rate-limited APIs stay happy.
- **transform** — run a tiny JavaScript snippet (`item.x = …; return
  item;`) on each item.
- **set** — shape the payload with an object literal, expressions
  allowed (`={{ $json.data.id }}`).
- **stop_and_error** — explicit failure with a custom error message.
- **no_op** — does nothing; useful as a sink for `if`'s `false` port.

### Expression syntax

Any parameter can hold a Weftlyflow expression by prefixing with `=`:

```text
={{ $json.user.email }}          # value from the current item
={{ $now.toISO() }}              # current timestamp
={{ $today }}                    # YYYY-MM-DD
={{ $workflow.id }}              # this workflow's ID
={{ $item(0).name }}             # first item's name
```

The full expression guide lives in
[`guide/expressions.md`](expressions.md).

---

## Credential types

The credentials vault supports any schema — each type is a plugin that
declares its own fields. Common types:

| Type slug | Used for |
|---|---|
| `weftlyflow.bearer_token` | Any API that wants `Authorization: Bearer …` |
| `weftlyflow.basic_auth` | Username + password HTTP basic auth |
| `weftlyflow.api_key` | Generic `X-API-Key` style |
| `weftlyflow.oauth2_generic` | OAuth 2 client-credentials / auth-code |
| `weftlyflow.slack_oauth` | Slack workspace token |
| `weftlyflow.google_oauth` | Google (Gmail, Calendar, Sheets, Drive) |
| `weftlyflow.stripe_api` | Stripe secret key |
| `weftlyflow.notion_integration` | Notion integration secret |
| `weftlyflow.openai_api` | OpenAI API key |
| `weftlyflow.anthropic_api` | Anthropic API key |
| `weftlyflow.postgres_dsn` | Postgres connection string |
| `weftlyflow.qdrant_cluster` | Qdrant URL + API key |
| …and dozens more | one per integration |

**How secrets are stored:**

1. Server generates a Fernet key at install time (kept in
   `WEFTLYFLOW_FERNET_KEY`).
2. On POST, each secret field is encrypted separately and the
   ciphertext stored in the `credentials.data` JSON column.
3. On decrypt, only the engine and a credential's owner can read the
   plaintext — the UI only ever shows the *name* and *type*.

See [`guide/credentials.md`](credentials.md) and
[`guide/external-secrets.md`](external-secrets.md) for the vault
internals and optional Vault/Secrets-Manager integration.

---

## Tours and help

Weftlyflow ships four first-run tours that spotlight the UI with a
floating popover and a "Next / Back / Skip" footer.

| Tour id | Page | Steps | What it covers |
|---|---|---|---|
| `home.v2` | Dashboard | 7 | Welcome · Hero · Quick actions · Stats · Templates · Integrations · Create |
| `editor.v2` | Editor | 7 | Welcome · Palette · Canvas · Inspector · Examples & suggestions · Inline tips · Save & run |
| `credentials.v1` | Credentials | 3 | Vault intro · Add new · Test & manage |
| `executions.v1` | Executions | 2 | Run history intro · Status + drill-down |

- Tours **auto-play on first visit** to each page.
- Completion/skip is remembered in `localStorage` under
  `weftlyflow.tour.seen.<id>`.
- You can **replay** any tour from the **Help menu** in the top bar:
    - *Replay dashboard tour*
    - *Replay editor tour* (only enabled inside the editor)
    - *Replay credentials tour*
    - *Replay executions tour*
    - *Reset all tours* — clears every `seen` flag; all tours will
      auto-play again on next visit.

**Keyboard inside a tour:** `→` next, `←` back, `Esc` skip,
`Enter` next.

**Toasts.** Small pop-up notifications in the corner. Green = success
(3.5s), blue = info (3.5s), red = error (6s). They stack, don't block
the UI, and can be dismissed with a click.

---

## Keyboard shortcut reference

Everything at a glance. ⌘ = `Cmd` on macOS, `Ctrl` on Windows / Linux.

### Global

| Keys | Action |
|---|---|
| `⌘K` | Focus the palette search (editor only) |

### Editor

| Keys | Action |
|---|---|
| `⌘S` | Save workflow |
| `⌘Enter` | Execute workflow |
| `⌘K` | Focus palette search |
| `?` | Open shortcuts modal |
| `Delete` / `Backspace` | Delete selected node |
| `↓ / ↑` (palette) | Move highlight |
| `Enter` (palette) | Add highlighted node |
| `Esc` (palette) | Clear search |

### Tours

| Keys | Action |
|---|---|
| `→` / `Enter` | Next step |
| `←` | Previous step |
| `Esc` | Skip tour |

---

## Data model cheat sheet

The three core objects you'll interact with via the API.

### Workflow

```json
{
  "id": "wf_01KQ...",
  "name": "Uptime guard · 5-min health check",
  "active": false,
  "tags": ["monitoring", "slack"],
  "nodes": [
    {
      "id": "node_abc",
      "name": "Every 5 minutes",
      "type": "weftlyflow.schedule_trigger",
      "type_version": 1,
      "parameters": { "cron": "0 */5 * * * *" },
      "credentials": {},
      "position": [80, 200],
      "disabled": false,
      "continue_on_fail": false,
      "notes": null
    },
    ...
  ],
  "connections": [
    {
      "source_node": "node_abc",
      "target_node": "node_xyz",
      "source_port": "main",
      "target_port": "main",
      "source_index": 0,
      "target_index": 0
    }
  ]
}
```

### Execution

```json
{
  "id": "exec_01KQ...",
  "workflow_id": "wf_01KQ...",
  "mode": "manual",
  "status": "success",
  "started_at": "2026-04-25T09:12:03.412Z",
  "finished_at": "2026-04-25T09:12:04.188Z",
  "run_data": {
    "node_abc": [
      { "status": "success", "execution_time_ms": 312, "items": [...], "error": null }
    ],
    "node_xyz": [
      { "status": "success", "execution_time_ms": 61, "items": [...], "error": null }
    ]
  }
}
```

### Credential (summary — data is never returned)

```json
{
  "id": "cred_01KQ...",
  "name": "Prod Slack",
  "type": "weftlyflow.slack_oauth",
  "created_at": "2026-04-20T12:00:00Z",
  "updated_at": "2026-04-24T09:30:00Z"
}
```

---

## Troubleshooting

**I keep getting bounced to `/login`.**
Your token expired. That's normal — the app auto-redirects and
preserves where you were in `?redirect=`. Sign in again, you'll come
right back.

**"No credentials of type X" warning in the inspector.**
You added a node (say, Slack) that needs a credential, but you
haven't created one of the matching type yet. Click the warning, or
go to `/credentials` → **New credential** → pick the matching type.

**My scheduled workflow isn't running.**
Three things to check, in order:

1. Is the workflow's **Active** toggle on (top bar in the editor)?
2. Does the Celery beat / worker process have a green status badge
   on the Home page?
3. Does the schedule node have a valid cron expression? Try clicking
   the suggestion chips — they're all valid.

**An AI node returned a parse error.**
The LLM returned something that wasn't valid JSON. Two fixes:

1. Make sure the OpenAI node has `response_format: "json_object"` or
   the Anthropic system prompt says **"strict JSON only"**.
2. Add a `guard_schema_enforce` node right after the LLM — it rejects
   responses that don't match the schema, so you fail loud and early
   instead of corrupting downstream nodes.

**The canvas is empty but I have nodes.**
Probably a zoom / pan problem. Open the Controls widget
(bottom-left of the canvas) and click the **Fit view** icon.

**Pasting `{{ $json.x }}` doesn't interpolate.**
Expressions need the leading `=`. The field value has to start with
`={{ … }}` to be treated as an expression, otherwise it's a literal
string.

**I deleted a workflow by accident.**
Workflows are soft-deleted in most deployments — check with your
admin; they can often be restored from the DB. Executions for a
deleted workflow are retained by default so the audit trail survives.

---

## Where to go next

- **Build your first workflow:** [`getting-started/first-workflow.md`](../getting-started/first-workflow.md)
- **Deep-dive on triggers:** [`guide/triggers-and-schedules.md`](triggers-and-schedules.md)
- **Using expressions:** [`guide/expressions.md`](expressions.md)
- **The Code node sandbox:** [`guide/code-node.md`](code-node.md)
- **Webhooks in production:** [`guide/webhooks.md`](webhooks.md)
- **AI & agents guide:** [`guide/ai-and-agents.md`](ai-and-agents.md)
- **Self-hosting checklist:** [`guide/self-hosting.md`](self-hosting.md)
- **Every built-in node (full reference):** [`nodes/`](../nodes/index.md)
