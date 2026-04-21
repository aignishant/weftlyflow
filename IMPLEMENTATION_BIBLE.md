# Weftlyflow — Implementation Bible

> The canonical plan. Every architectural decision, every phase, every coding standard.
> Treat this file as load-bearing. If code diverges from it, either fix the code or update the bible and note the change in the revision log at the bottom.

---

## Table of contents

1. [Project identity](#1-project-identity)
2. [Non-goals and scope boundaries](#2-non-goals-and-scope-boundaries)
3. [Glossary](#3-glossary)
4. [Technology stack decisions](#4-technology-stack-decisions)
5. [High-level architecture](#5-high-level-architecture)
6. [Source layout](#6-source-layout)
7. [Domain model](#7-domain-model)
8. [Execution engine](#8-execution-engine)
9. [Node plugin system](#9-node-plugin-system)
10. [Expression engine](#10-expression-engine)
11. [Credential system](#11-credential-system)
12. [Webhook system](#12-webhook-system)
13. [Trigger and polling system](#13-trigger-and-polling-system)
14. [Queue and worker system](#14-queue-and-worker-system)
15. [REST API surface](#15-rest-api-surface)
16. [Authentication, authorization, multi-tenancy](#16-authentication-authorization-multi-tenancy)
17. [Frontend architecture](#17-frontend-architecture)
18. [AI and agent integration](#18-ai-and-agent-integration)
19. [Observability](#19-observability)
20. [Testing strategy](#20-testing-strategy)
21. [Documentation strategy (mkdocs)](#21-documentation-strategy-mkdocs)
22. [Coding standards](#22-coding-standards)
23. [Intellectual-property compliance rules](#23-intellectual-property-compliance-rules)
24. [Phased delivery roadmap](#24-phased-delivery-roadmap)
25. [Node porting priority](#25-node-porting-priority)
26. [Risk register](#26-risk-register)
27. [Revision log](#27-revision-log)

---

## 1. Project identity

- **Name:** Weftlyflow
- **One-line:** Self-hosted, open-architecture workflow automation platform — visual node graphs, triggers, polling, 100s of integrations, AI agents.
- **Inspiration:** n8n (fair-code, TypeScript). Weftlyflow is an **independent, clean-room Python reimagination** — the architecture is borrowed at the *conceptual* level, no code/identifiers/data-shape is copied verbatim.
- **Working directory:** `/home/nishantgupta/Desktop/ng8`
- **Primary user:** Self-hoster who wants a fully understood, hackable Python codebase with strong docs.

### Why Python (not TypeScript like n8n)
- Strong ecosystem for AI/LLM (LangChain-Python, llama-index, pydantic-ai).
- SQLAlchemy + Alembic + FastAPI is a mature, typed, async-capable server stack.
- User's primary language preference; existing tooling in `low-spec-2/.claude`.
- Code-node / expression sandboxing is genuinely cleaner in Python (RestrictedPython + subprocess isolation).

### Why Vue 3 (frontend, not HTMX)
- Visual editor needs a rich node-graph canvas. **Vue Flow** is the best-maintained, license-compatible node editor and it pairs with Vue 3.
- Pinia + Composition API matches the mental model of a live workflow (dirty state, undo/redo, WebSocket-driven execution overlays).
- Hand-rolling a node canvas with HTMX/Alpine would waste weeks; reuse the proven library.

---

## 2. Non-goals and scope boundaries

- **Not** a drop-in replacement for n8n workflows (different node identifiers, different expression syntax, different credential slugs).
- **Not** cloud-hosted SaaS in v1 — self-host first, multi-tenant is a feature of the core but there is no hosted offering.
- **Not** re-implementing every one of n8n's 306 base + 135 AI nodes in v1. See [§25 Node porting priority](#25-node-porting-priority) for the tiering.
- **Not** a code-for-code translation — where Python idioms (context managers, async generators, dataclasses, pydantic) are cleaner, we use them even if the original uses a different pattern.
- **Not** compatible with n8n's JSON workflow export format — Weftlyflow has its own schema (intentional, for IP hygiene).

---

## 3. Glossary

| Term | Meaning |
|---|---|
| **Workflow** | Directed graph of nodes + connections + settings. Persisted as a row in `workflows`, serializable to JSON. |
| **Node** | One step in a workflow. Implemented as a Python class. Three flavors: **action** (runs when upstream data arrives), **trigger** (starts a workflow from an external event), **poller** (periodically calls an API). |
| **Connection** | Directed edge from one node's output port to another node's input port. |
| **Port** | A typed input or output socket on a node. Each port has a `name`, `type` (`main`, `ai_tool`, `ai_memory`, etc.), and `index`. |
| **Execution** | One run of a workflow. Has a status (`new`, `running`, `success`, `error`, `waiting`, `canceled`), a mode (`manual`, `trigger`, `webhook`, `retry`), and run data. |
| **Run data** | Per-node, per-output-port list of items (`list[list[ItemData]]`) captured during an execution. |
| **Item** | A single JSON object + optional binary attachments, flowing between nodes. The unit of iteration. |
| **Credential** | Encrypted authentication blob (OAuth2 tokens, API keys, basic auth) + a `type` identifier matching a `CredentialType` plugin. |
| **Trigger** | A node that *starts* a workflow (manual, webhook, schedule, polling, event). |
| **Webhook** | An HTTP endpoint registered by a trigger node. **Static** = known path at activation; **dynamic** = UUID-based, registered at runtime. |
| **Expression** | `{{ ... }}` templated value resolved against execution context (`$json`, `$input`, `$env`, `$now`). |
| **Project** | Multi-tenancy unit. Every workflow/credential belongs to exactly one project. Users have roles per project. |
| **Static data** | Per-workflow persistent key-value store (e.g., remembered webhook IDs, OAuth state tokens, last-seen poll cursor). |
| **Pin data** | Hard-coded output data pinned to a specific node, used in dev to skip real API calls. |

---

## 4. Technology stack decisions

| Layer | Choice | Rationale |
|---|---|---|
| **Language (backend)** | Python 3.12 | Modern typing (`list[int]`, `X \| None`), `match`/`case`, perf improvements. 3.11 also supported. |
| **Package manager / build** | `pip` + `hatch` (PEP 621) | Matches user's convention (`low-spec-2`). Editable installs via `pip install -e ".[all]"`. Not `poetry`, not `uv`. |
| **HTTP framework** | FastAPI | Async-first, Pydantic integration, OpenAPI free, WebSocket support for live execution streams. |
| **Async IO client** | httpx | Shared sync+async API, HTTP/2, used by all HTTP-based nodes. |
| **ORM / DB** | SQLAlchemy 2.x + Alembic | Typed `Mapped[...]`, async engine, mature migrations. JSONB on Postgres, JSON on SQLite. |
| **Databases** | SQLite (dev), Postgres (prod). MySQL deferred. | Same choice as n8n; single SQL dialect switch via env. |
| **Validation** | Pydantic v2 | DTOs, settings, node-parameter schema. |
| **Task queue** | Celery + Redis | Industry standard, reliable retries, priority queues, Beat for schedules. |
| **In-process scheduler** | APScheduler | For lightweight polling orchestration that doesn't need full Celery. |
| **Code-node sandbox** | RestrictedPython + subprocess + `resource` rlimits | Layered defense: AST restriction + OS-level memory/CPU cap + timeout. |
| **Crypto** | `cryptography` (Fernet) | Credential encryption at rest. Key rotation via `MultiFernet`. |
| **Auth** | PyJWT (HS256 for self-host, RS256 for SSO), bcrypt / argon2 (passwords) | Standard. |
| **OAuth client** | `authlib` | Mature OAuth2 client + server helpers. |
| **Logging** | structlog + stdlib logging | Structured JSON logs, context binding per execution/node. |
| **Tracing / metrics** | OpenTelemetry + `prometheus-client` | Optional, behind env flag. |
| **Error tracking** | Sentry SDK (optional, behind env flag) | |
| **Testing** | pytest, pytest-asyncio, pytest-cov, hypothesis, respx (HTTP mock), Playwright (E2E) | |
| **Lint/format** | ruff (lint + format), black (safety net), isort, mypy `--strict` | |
| **Docs** | mkdocs-material + mkdocstrings[python] + mkdocs-gen-files + mkdocs-literate-nav | Per-module auto-generated API ref + hand-written guides. |
| **Frontend framework** | Vue 3 (Composition API, `<script setup>`) | Matches domain fit. |
| **Frontend language** | TypeScript | Catches entire classes of canvas bugs early. |
| **Frontend build** | Vite | Instant HMR, tiny config. |
| **State management** | Pinia | Setup stores, Composition-API-native. |
| **Canvas** | Vue Flow (`@vue-flow/core`) | Node graph, handles, minimap, controls. |
| **Code editor (in browser)** | CodeMirror 6 | For the Code node and expression editor with Weftlyflow-expression highlighting. |
| **UI component library** | Element Plus + a small custom design system | Buttons, modals, tables without reinventing. |
| **Data grid (execution results)** | TanStack Table v8 + virtualization | Free, license-safe. |
| **Icons** | Lucide (SVG) | MIT-licensed, enormous icon set. |
| **Infra** | Docker + docker-compose; Redis + Postgres services | |

---

## 5. High-level architecture

```
                 ┌──────────────────────────────────────────────────────────┐
                 │                   Browser (Vue 3 + Vue Flow)             │
                 │   Editor · Execution monitor · Credentials · Projects    │
                 └───────────────┬──────────────────┬───────────────────────┘
                                 │ REST /api/v1/*   │ WS /ws/executions
                                 ▼                  ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                          Weftlyflow API server (FastAPI)                     │
│  · Auth (JWT)     · Workflow CRUD   · Credential CRUD  · Execution CRUD    │
│  · Webhook routes · Node-type registry endpoint        · OpenAPI schema    │
└──────┬──────────────────┬───────────────────┬────────────────┬─────────────┘
       │                  │                   │                │
       ▼                  ▼                   ▼                ▼
  ┌────────┐      ┌──────────────┐      ┌──────────┐    ┌──────────────┐
  │Postgres│      │ Redis        │      │ Trigger  │    │  Secrets /   │
  │ / SQLite│     │ (broker, pub/sub,   │ registry │    │  Key Vault   │
  │  via   │      │  locks, cache)      │ (active  │    │  (optional)  │
  │SQLAlch.│      └──────────────┘      │ wfs)     │    └──────────────┘
  └────────┘              ▲             └──────┬───┘
                          │                    │
                          │ task enqueue       │ fires (webhook/cron/poll)
                          ▼                    ▼
                   ┌────────────────────────────────────┐
                   │        Celery worker fleet         │
                   │  · Workflow executor (sandboxed)   │
                   │  · Code-node subprocess runner     │
                   │  · OAuth refresh runner            │
                   └────────────────────────────────────┘
```

**Processes in a typical deployment:**
1. `weftlyflow-api` (uvicorn/gunicorn) — FastAPI HTTP + WebSocket server.
2. `weftlyflow-worker` (celery) — runs workflow executions, 1..N instances.
3. `weftlyflow-beat` (celery beat) — single-instance cron scheduler for time-based triggers.
4. `redis`, `postgres` — stateful services.

**Multi-instance coordination:** A single leader (elected via Redis `SETNX` lock with TTL) runs the active-workflow registry — owns webhook registration state. Workers are stateless.

---

## 6. Source layout

```
ng8/                                 ← working directory
├── IMPLEMENTATION_BIBLE.md          ← this document (source of truth)
├── README.md
├── LICENSE
├── pyproject.toml                   ← PEP 621, hatch backend
├── Makefile                         ← dev workflow shortcuts
├── docker-compose.yml
├── Dockerfile                       ← multi-stage; api/worker/beat images
├── .gitignore
├── .env.example
├── mkdocs.yml
├── .pre-commit-config.yaml
├── alembic.ini
│
├── .claude/                         ← Claude Code config, mirrored from low-spec-2
│   ├── CLAUDE.md
│   ├── settings.json
│   ├── .mcp.json
│   ├── agents/
│   ├── skills/
│   ├── hooks/
│   ├── commands/
│   └── memory/
│
├── src/
│   └── weftlyflow/
│       ├── __init__.py              ← package version, __all__
│       ├── __main__.py              ← `python -m weftlyflow ...`
│       ├── cli.py                   ← Typer CLI (start, worker, beat, db, export, import)
│       │
│       ├── config/                  ← Pydantic Settings
│       │   ├── __init__.py
│       │   ├── settings.py          ← WeftlyflowSettings (env-driven)
│       │   └── logging.py           ← structlog setup
│       │
│       ├── domain/                  ← pure data types; no IO
│       │   ├── __init__.py
│       │   ├── workflow.py          ← Workflow, Node, Connection dataclasses
│       │   ├── execution.py         ← Execution, RunData, Item, ItemBinary
│       │   ├── credential.py        ← CredentialDescriptor
│       │   ├── node_spec.py         ← NodeSpec, NodeVersion, Port, PropertySchema
│       │   ├── errors.py            ← WeftlyflowError + subtypes (no nodes use these)
│       │   └── ids.py               ← ULID generators, ID prefixes
│       │
│       ├── db/                      ← SQLAlchemy entities + repositories
│       │   ├── __init__.py
│       │   ├── base.py              ← DeclarativeBase, session factory
│       │   ├── engine.py            ← sync + async engine factories
│       │   ├── entities/
│       │   │   ├── workflow.py
│       │   │   ├── execution.py
│       │   │   ├── execution_data.py
│       │   │   ├── credential.py
│       │   │   ├── user.py
│       │   │   ├── project.py
│       │   │   ├── shared_workflow.py
│       │   │   ├── shared_credential.py
│       │   │   ├── webhook.py
│       │   │   ├── tag.py
│       │   │   ├── variable.py
│       │   │   ├── workflow_history.py
│       │   │   ├── audit_event.py
│       │   │   └── ...
│       │   ├── repositories/
│       │   │   ├── workflow_repo.py
│       │   │   ├── execution_repo.py
│       │   │   ├── credential_repo.py
│       │   │   ├── user_repo.py
│       │   │   ├── webhook_repo.py
│       │   │   └── ...
│       │   └── migrations/          ← Alembic versions
│       │       ├── env.py
│       │       └── versions/
│       │
│       ├── engine/                  ← execution engine (the heart)
│       │   ├── __init__.py
│       │   ├── executor.py          ← WorkflowExecutor (main loop)
│       │   ├── graph.py             ← DAG analysis (parents, children, topo order, cycles)
│       │   ├── context.py           ← ExecutionContext, ExecuteHelpers passed to nodes
│       │   ├── item.py              ← Item wrapping, paired-item tracking
│       │   ├── hooks.py             ← LifecycleHooks (on_start, on_node_finish, on_error, ...)
│       │   ├── partial.py           ← partial-run support (resume from failed node)
│       │   ├── retry.py             ← per-node retry policy
│       │   ├── pin_data.py          ← pinned-output short-circuit
│       │   └── cancel.py            ← cooperative cancellation
│       │
│       ├── expression/              ← templating engine
│       │   ├── __init__.py
│       │   ├── tokenizer.py         ← split text into literal + {{ ... }} chunks
│       │   ├── sandbox.py           ← RestrictedPython + guards
│       │   ├── resolver.py          ← eval chunk against ExecutionContext
│       │   ├── proxies.py           ← $json, $input, $output, $env, $now, $today
│       │   └── extensions.py        ← .keys(), .values(), .to_date(), .first(), .last()
│       │
│       ├── nodes/                   ← built-in node plugins (see §9)
│       │   ├── __init__.py
│       │   ├── base.py              ← BaseNode, BaseTriggerNode, BasePollerNode ABCs
│       │   ├── registry.py          ← NodeRegistry
│       │   ├── decorator.py         ← @register_node decorator
│       │   ├── loader.py            ← entry-point + directory scanner
│       │   ├── core/                ← Tier-1 utility nodes (see §25)
│       │   │   ├── http_request/
│       │   │   ├── webhook/
│       │   │   ├── schedule/
│       │   │   ├── manual_trigger/
│       │   │   ├── if_node/
│       │   │   ├── switch_node/
│       │   │   ├── merge/
│       │   │   ├── set/
│       │   │   ├── split_in_batches/
│       │   │   ├── code/
│       │   │   ├── filter/
│       │   │   ├── aggregate/
│       │   │   ├── wait/
│       │   │   └── ...
│       │   ├── integrations/        ← Tier-2 + Tier-3 (populated incrementally)
│       │   │   ├── slack/
│       │   │   ├── github/
│       │   │   └── ...
│       │   └── ai/                  ← Tier-2 AI nodes (see §18)
│       │       ├── llm_openai/
│       │       ├── llm_anthropic/
│       │       ├── agent_react/
│       │       ├── memory_buffer/
│       │       ├── vector_store_*/
│       │       └── ...
│       │
│       ├── credentials/             ← credential plugins + encryption
│       │   ├── __init__.py
│       │   ├── base.py              ← BaseCredentialType ABC
│       │   ├── registry.py          ← CredentialTypeRegistry
│       │   ├── cipher.py            ← Fernet wrapper
│       │   ├── oauth2.py            ← OAuth2 flow helpers (authlib)
│       │   ├── test_runner.py       ← runs `test()` on a credential
│       │   └── types/               ← one file per credential type
│       │       ├── bearer_token.py
│       │       ├── basic_auth.py
│       │       ├── api_key_header.py
│       │       ├── api_key_query.py
│       │       ├── oauth2_generic.py
│       │       └── ...
│       │
│       ├── server/                  ← FastAPI app
│       │   ├── __init__.py
│       │   ├── app.py               ← create_app() factory
│       │   ├── lifespan.py          ← startup/shutdown tasks
│       │   ├── deps.py              ← FastAPI dependencies (DB, current_user, project)
│       │   ├── middleware.py        ← logging, request-id, CORS, error envelope
│       │   ├── errors.py            ← HTTP error mapping
│       │   ├── schemas/             ← Pydantic DTOs in/out
│       │   │   ├── workflow.py
│       │   │   ├── credential.py
│       │   │   ├── execution.py
│       │   │   ├── node_type.py
│       │   │   ├── user.py
│       │   │   └── ...
│       │   └── routers/             ← one router per resource
│       │       ├── auth.py
│       │       ├── workflows.py
│       │       ├── credentials.py
│       │       ├── executions.py
│       │       ├── node_types.py
│       │       ├── webhooks_ingress.py  ← the public webhook entrypoint
│       │       ├── projects.py
│       │       ├── users.py
│       │       ├── variables.py
│       │       ├── tags.py
│       │       └── health.py
│       │
│       ├── webhooks/                ← webhook lifecycle + routing
│       │   ├── __init__.py
│       │   ├── registry.py          ← active webhook table (path → workflow + node)
│       │   ├── router.py            ← match incoming request → workflow
│       │   ├── handler.py           ← parse request → ItemData → kick off execution
│       │   └── waiting.py           ← resume executions paused at a Wait node
│       │
│       ├── triggers/                ← trigger/poll lifecycle
│       │   ├── __init__.py
│       │   ├── manager.py           ← ActiveTriggerManager
│       │   ├── scheduler.py         ← APScheduler wrapper for cron/interval
│       │   └── poller.py            ← generic poller loop
│       │
│       ├── worker/                  ← Celery app + tasks
│       │   ├── __init__.py
│       │   ├── app.py               ← celery_app
│       │   ├── tasks.py             ← execute_workflow, refresh_oauth, ...
│       │   ├── signals.py           ← logging hooks
│       │   └── sandbox_runner.py    ← Code-node subprocess entrypoint
│       │
│       ├── auth/                    ← authn + authz
│       │   ├── __init__.py
│       │   ├── passwords.py         ← argon2 hashing
│       │   ├── jwt.py               ← token issue/verify
│       │   ├── rbac.py              ← Role, Scope, has_scope()
│       │   ├── mfa.py               ← TOTP
│       │   └── sso/                 ← SAML, OIDC (enterprise tier)
│       │
│       ├── observability/
│       │   ├── __init__.py
│       │   ├── logging.py           ← structlog processors
│       │   ├── metrics.py           ← Prometheus counters/histograms
│       │   └── tracing.py           ← OpenTelemetry setup
│       │
│       └── utils/
│           ├── __init__.py
│           ├── datetime.py          ← tz-aware helpers
│           ├── json_helpers.py      ← safe loads/dumps, canonicalization
│           ├── http.py              ← httpx client factory with retry
│           └── paths.py             ← data-dir resolver
│
├── frontend/                        ← Vue 3 + Vite app (separate package)
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   ├── src/
│   │   ├── main.ts
│   │   ├── App.vue
│   │   ├── router/
│   │   ├── stores/                  ← Pinia (workflow, execution, nodeTypes, credentials, ui, auth, project)
│   │   ├── api/                     ← typed REST client
│   │   ├── components/
│   │   │   ├── canvas/              ← Vue Flow integration
│   │   │   │   ├── Canvas.vue
│   │   │   │   ├── WeftlyflowNode.vue
│   │   │   │   └── NodeMenu.vue
│   │   │   ├── node-settings/       ← dynamic parameter form
│   │   │   ├── credentials/
│   │   │   ├── execution/
│   │   │   ├── header/
│   │   │   └── shared/
│   │   ├── views/
│   │   │   ├── Home.vue
│   │   │   ├── Editor.vue
│   │   │   ├── Executions.vue
│   │   │   ├── Credentials.vue
│   │   │   └── Settings.vue
│   │   └── styles/
│   └── tests/
│       ├── unit/
│       └── e2e/                     ← Playwright
│
├── tests/                           ← backend tests
│   ├── unit/
│   ├── integration/
│   ├── nodes/
│   └── conftest.py
│
├── docker/
│   ├── api.Dockerfile
│   ├── worker.Dockerfile
│   └── beat.Dockerfile
│
└── docs/                            ← mkdocs source
    ├── index.md
    ├── architecture.md
    ├── guide/
    ├── reference/                   ← auto-generated per module
    ├── nodes/                       ← one page per built-in node
    └── assets/
```

---

## 7. Domain model

### 7.1 In-memory dataclasses (`weftlyflow.domain.*`)

```python
# domain/workflow.py
@dataclass(slots=True, frozen=True)
class Port:
    name: str                # "main", "ai_tool", "ai_memory"
    type: Literal["main", "ai_tool", "ai_memory", "ai_embedding", "ai_document"]
    index: int = 0
    display_name: str | None = None
    required: bool = False

@dataclass(slots=True)
class Node:
    id: str                  # "node_01H..."
    name: str                # user-facing name in the workflow
    type: str                # registry key, e.g. "weftlyflow.http_request"
    type_version: int        # multi-version node support
    parameters: dict[str, Any]
    credentials: dict[str, str]  # credential-slot-name -> credential-id
    position: tuple[float, float]
    disabled: bool = False
    notes: str | None = None
    continue_on_fail: bool = False
    retry_policy: RetryPolicy | None = None

@dataclass(slots=True, frozen=True)
class Connection:
    source_node: str
    source_port: str = "main"
    source_index: int = 0
    target_node: str
    target_port: str = "main"
    target_index: int = 0

@dataclass(slots=True)
class Workflow:
    id: str
    project_id: str
    name: str
    nodes: list[Node]
    connections: list[Connection]
    settings: WorkflowSettings
    static_data: dict[str, Any]      # node-scoped persistent kv
    pin_data: dict[str, list[Item]]  # node-id -> pinned output items
    active: bool = False
    archived: bool = False
    tags: list[str] = field(default_factory=list)
    version_id: str | None = None
```

### 7.2 Execution runtime

```python
# domain/execution.py
@dataclass(slots=True)
class Item:
    """One record flowing between nodes."""
    json: dict[str, Any]
    binary: dict[str, BinaryRef] = field(default_factory=dict)
    paired_item: list[PairedItem] = field(default_factory=list)
    error: NodeError | None = None

@dataclass(slots=True)
class NodeRunData:
    items: list[list[Item]]          # [output_port_index][item_index]
    execution_time_ms: int
    started_at: datetime
    status: Literal["success", "error", "disabled"]
    error: NodeError | None = None
    source: list[NodeRunSource] = field(default_factory=list)

@dataclass(slots=True)
class RunData:
    """Per-execution recording of every node run."""
    per_node: dict[str, list[NodeRunData]]  # a node can run multiple times (loops)

@dataclass(slots=True)
class Execution:
    id: str
    workflow_id: str
    workflow_snapshot: Workflow       # frozen copy at run start
    mode: Literal["manual", "trigger", "webhook", "retry", "test"]
    status: Literal["new", "running", "success", "error", "waiting", "canceled"]
    started_at: datetime
    finished_at: datetime | None
    wait_till: datetime | None
    run_data: RunData
    data_storage: Literal["db", "fs", "s3"]  # where run_data is stored
    triggered_by: str | None          # user id, webhook id, or schedule id
```

### 7.3 Persistence mapping

Every dataclass above has a corresponding SQLAlchemy entity in `weftlyflow.db.entities.*`. Translation layer lives in `weftlyflow.db.mappers.*` so `domain/` stays pure (no ORM imports, no IO).

### 7.4 Key SQL tables

| Table | Purpose | Notable columns |
|---|---|---|
| `projects` | Multi-tenancy root | `id`, `name`, `kind` (`personal`/`team`) |
| `users` | Human accounts | `id`, `email`, `password_hash`, `mfa_secret`, `global_role` |
| `workflows` | Workflow def | `id`, `project_id`, `name`, `nodes` (JSONB), `connections` (JSONB), `settings`, `active`, `archived`, `version_id` |
| `workflow_history` | Versioned snapshots | `id`, `workflow_id`, `snapshot` (JSONB), `created_at`, `author_id` |
| `executions` | Run metadata | `id`, `workflow_id`, `mode`, `status`, `started_at`, `finished_at`, `wait_till`, `triggered_by` |
| `execution_data` | Run data blob | `execution_id` (PK+FK), `run_data` (JSONB/TEXT), `storage_kind` |
| `credentials` | Encrypted auth | `id`, `project_id`, `name`, `type`, `data_ciphertext`, `data_nonce` |
| `shared_workflows` | ACL | `workflow_id`, `user_id`, `role` |
| `shared_credentials` | ACL | `credential_id`, `user_id`, `role` |
| `webhooks` | Active webhooks | `id`, `workflow_id`, `node_id`, `path`, `method`, `is_dynamic` |
| `workflow_static_data` | Per-workflow KV | `workflow_id`, `key`, `value` (JSONB) |
| `variables` | Env-like vars | `id`, `project_id`, `key`, `value_ciphertext` |
| `tags` | Labels | `id`, `name`; M2M `workflow_tags` |
| `audit_events` | Audit log | `id`, `actor_id`, `action`, `resource`, `metadata` (JSONB), `at` |
| `oauth_states` | OAuth CSRF tokens | `state`, `credential_id`, `expires_at` |
| `binary_data_files` | Large binary chunks | `id`, `execution_id`, `node_id`, `mime_type`, `size_bytes`, `storage_path` |

---

## 8. Execution engine

### 8.1 Algorithm (simplified)

```
run(workflow, start_node, initial_items, mode):
    graph = build_graph(workflow)
    ctx = ExecutionContext(workflow, execution_id, mode, hooks)

    stack = [(start_node, input_port=0, initial_items)]
    run_data = {}

    while stack:
        node, port, items = stack.pop()
        if node.disabled: continue

        if node.id in workflow.pin_data:           # short-circuit
            output = workflow.pin_data[node.id]
        else:
            output = await execute_node(node, items, ctx)

        run_data[node.id].append(NodeRunData(items=output, ...))
        await hooks.on_node_finish(node, output)

        for conn in graph.outgoing(node.id):
            next_items = output[conn.source_index]
            stack.append((graph.node(conn.target_node), conn.target_port, next_items))

    return Execution(status="success", run_data=run_data, ...)
```

### 8.2 Cancellation

- `asyncio.Task` with a cooperative `CancelScope` (via `anyio` abstraction).
- API `POST /executions/{id}/cancel` sets a Redis key; engine checks between nodes.

### 8.3 Error handling

Per-node policy:
- **Throw (default)** — execution stops, status `error`, error node (if configured) runs.
- **Continue on fail** — node returns items with `error` attached.
- **Retry** — `RetryPolicy(max=N, backoff=exp, max_delay=60s)`.

Workflow-level:
- **Error workflow** — a second workflow runs with the error event as input.

### 8.4 Partial execution

When the user clicks "rerun from this node," the engine:
1. Takes the last successful execution's `run_data`.
2. Walks back from failed node to collect upstream inputs.
3. Rebuilds the node-execution stack from there.
4. Reuses upstream outputs (no re-running successful nodes).

### 8.5 Loops and branching

- Nodes with multiple outputs (If, Switch, Merge) return `list[list[Item]]` — one list per output port.
- The engine propagates down only the populated ports.
- `SplitInBatches` is special: yields items in chunks and expects re-entry via a loopback edge — implemented as generator-style `poll_loop()`.

---

## 9. Node plugin system

### 9.1 Base class

```python
# nodes/base.py
class BaseNode(ABC):
    """All action nodes inherit from this."""

    spec: ClassVar[NodeSpec]   # declared on the class

    @abstractmethod
    async def execute(self, ctx: ExecutionContext, items: list[Item]) -> list[list[Item]]:
        ...

class BaseTriggerNode(ABC):
    """Webhook/event triggers."""
    spec: ClassVar[NodeSpec]

    @abstractmethod
    async def setup(self, ctx: TriggerContext) -> TriggerHandle: ...

    @abstractmethod
    async def teardown(self, handle: TriggerHandle) -> None: ...

class BasePollerNode(ABC):
    """Interval-polled triggers."""
    spec: ClassVar[NodeSpec]

    @abstractmethod
    async def poll(self, ctx: PollContext) -> list[Item] | None: ...
```

### 9.2 NodeSpec (declarative metadata)

```python
@dataclass(frozen=True)
class NodeSpec:
    type: str                         # unique key: "weftlyflow.http_request"
    version: int                      # class version, supports 1, 2, 3
    display_name: str
    description: str
    icon: str                         # path to SVG
    category: NodeCategory            # enum: Trigger, Core, Integration, AI
    group: list[str]                  # tags for UI filtering
    inputs: list[Port]
    outputs: list[Port]
    credentials: list[CredentialSlot] # which credential types this node requires
    properties: list[PropertySchema]  # parameter definitions
    supports_binary: bool = False
```

### 9.3 PropertySchema

The declarative parameter schema — drives the frontend's auto-form:
```python
@dataclass(frozen=True)
class PropertySchema:
    name: str
    display_name: str
    type: Literal["string","number","boolean","options","multi_options",
                  "json","datetime","color","expression","credentials","fixed_collection"]
    default: Any = None
    required: bool = False
    description: str | None = None
    options: list[PropertyOption] | None = None
    display_options: DisplayOptions | None = None  # conditional visibility
    placeholder: str | None = None
    type_options: dict[str, Any] | None = None     # password=True, rows=4, etc.
```

### 9.4 Discovery

Weftlyflow loads nodes from:
1. Built-ins under `src/weftlyflow/nodes/` — `registry.load_builtins()` walks subpackages for modules exporting a `NODE` attribute.
2. Python packages declaring entry points:
   ```toml
   [project.entry-points."weftlyflow.nodes"]
   my_node = "mypkg.module:MyNode"
   ```
3. A community-nodes directory configured via `WEFTLYFLOW_COMMUNITY_NODES_DIR`.

### 9.5 Versioning

A node type can ship multiple versions. The registry stores them keyed by `(type, version)`. Workflows pin `type_version` — old workflows keep running on v1 after v2 ships.

### 9.6 Testing a node

Every node ships a sibling `tests/` folder:
- `tests/nodes/<node>/test_execute.py` — unit tests with mocked HTTP (`respx`).
- `tests/nodes/<node>/fixtures/` — sample input/output JSON.
- Integration test tier (opt-in, marked `@pytest.mark.integration`) — hits real APIs using sandbox credentials from env.

---

## 10. Expression engine

### 10.1 Syntax

Weftlyflow expressions live in any parameter string wrapped in `{{ ... }}`:
```
https://api.example.com/{{ $json.id }}/details?since={{ $now.to_iso() }}
```

Inside `{{ }}` the language is a **restricted Python subset**:
- Literal expressions only (no `exec`/`eval`/imports/assignments).
- Builtins allow-list: `len, range, sum, min, max, abs, round, str, int, float, bool, list, dict, tuple, sorted, reversed, enumerate, zip, any, all, map, filter`.
- All `$`-prefixed names are proxy objects (not real globals).

### 10.2 Proxies

| Proxy | Meaning |
|---|---|
| `$json` | `dict` — current item's JSON payload. |
| `$binary` | `dict` — current item's binary refs. |
| `$input` | `InputProxy` — `$input.all()` returns all items of port 0; `$input.item(i)`; `$input.first()`; `$input.last()`. |
| `$output` | `OutputProxy` — `$output("Node Name").all()` to reach into another node's output. |
| `$prev_node` | `NodeOutputProxy` — shortcut for previous node in graph order. |
| `$now` | `WeftlyflowDateTime` — tz-aware "now". `.to_iso()`, `.plus(days=1)`, `.minus(hours=3)`. |
| `$today` | `WeftlyflowDateTime` — today at 00:00 UTC. |
| `$env` | `dict` — **only** variables prefixed `WEFTLYFLOW_VAR_*` (everything else hidden). |
| `$workflow` | `{id, name, project_id}` — limited. |
| `$execution` | `{id, mode, started_at}` — limited. |
| `$vars` | User-defined project variables (see `variables` table). |
| `$credentials` | **Not exposed.** Nodes access credentials through a different API. |

### 10.3 Evaluation

```python
# expression/resolver.py
def resolve(template: str, ctx: ExecutionContext, item: Item) -> Any:
    """
    Resolve a template string containing zero or more {{ ... }} chunks.

    - If the entire template is one {{ ... }} chunk, returns the evaluated value (preserves type).
    - Otherwise concatenates string representations of chunks with literal text.

    Raises:
        ExpressionSyntaxError: on malformed {{ ... }}
        ExpressionEvalError:   on runtime error inside a chunk
        ExpressionTimeoutError: if evaluation exceeds SOFT_TIMEOUT_MS (default 100 ms)
    """
```

Implementation: `RestrictedPython.compile_restricted_eval` → `eval()` with a locked-down globals dict.

### 10.4 Extensions

Tasteful helpers added as **methods on built-in types** via a wrapper proxy (not monkey-patching `list`/`str`):
- `string`: `.to_date(fmt=None)`, `.extract_email()`, `.truncate(n)`, `.slug()`
- `list`: `.first()`, `.last()`, `.compact()`, `.pluck(key)`, `.sum_by(key)`
- `dict`: `.keys()`, `.values()`, `.entries()`, `.pick(*keys)`, `.omit(*keys)`
- `datetime`: `.to_iso()`, `.plus(**kwargs)`, `.minus(**kwargs)`, `.format(fmt)`

---

## 11. Credential system

### 11.1 Credential type plugin

```python
# credentials/base.py
class BaseCredentialType(ABC):
    slug: ClassVar[str]                         # "weftlyflow.api_key_header"
    display_name: ClassVar[str]
    properties: ClassVar[list[PropertySchema]]
    generic: ClassVar[bool] = False              # generic vs service-specific

    async def inject(self, creds: dict, req: httpx.Request) -> httpx.Request:
        """Apply credential to an outgoing HTTP request (headers/query/body)."""

    async def test(self, creds: dict) -> CredentialTestResult:
        """Optional: self-test (e.g., GET /me)."""
```

### 11.2 Encryption at rest

- **Key source:** `WEFTLYFLOW_ENCRYPTION_KEY` env var — a base64-encoded 32-byte key.
- **Algorithm:** Fernet (AES-128-CBC + HMAC-SHA256 + version byte).
- **Rotation:** `MultiFernet` with old keys; rotate via `weftlyflow db rotate-encryption-key`.
- **Stored shape:** `data_ciphertext` (bytes), `data_nonce` (part of Fernet token), no plaintext ever at rest.

### 11.3 OAuth2 flow

1. `POST /credentials/oauth2/authorize-url` → returns provider auth URL; server stores a row in `oauth_states` keyed by CSRF `state`.
2. Browser redirects to provider → user consents → provider redirects to `/oauth2/callback?code=&state=`.
3. Server matches `state`, exchanges code for token, stores encrypted credential, deletes `oauth_states` row.
4. Refresh: a Celery task `refresh_oauth` runs hourly for credentials with `expires_at < now + 10min`.

### 11.4 External secret providers (optional, later phase)

Adapter layer under `weftlyflow.credentials.external/` — AWS Secrets Manager, HashiCorp Vault, 1Password. A credential can set `external_ref: "vault:path/to/secret"` instead of `data_ciphertext`.

---

## 12. Webhook system

### 12.1 Path schema

- **Static:** `/webhook/<project-slug>/<workflow-id>/<node-slug>` — known at activation time.
- **Dynamic:** `/webhook/u/<uuid4>` — generated per activation, stored in the `webhooks` table.
- **Test:** `/webhook-test/<webhook-id>` — only listens while the user has the editor open "test" panel.

### 12.2 Registration lifecycle

When a workflow is activated:
1. `triggers.manager.activate(workflow)` iterates its trigger nodes.
2. For each webhook trigger: the node's `setup()` is called, which registers a row in `webhooks` and may call out to the external service to install the webhook.
3. Redis pub/sub broadcasts `webhook.registered` so all API instances refresh their in-memory route table.

When deactivated: `teardown()` reverses both steps.

### 12.3 Request handling

```
HTTP request → FastAPI route /webhook/*
            → webhooks.router.match(path, method) → WebhookEntry
            → webhooks.handler.handle(entry, request)
            → build Item from request (headers/body/query/binary)
            → enqueue Celery task execute_workflow(workflow_id, mode=webhook, ...)
            → (sync mode) await response node; (async mode) respond 200 immediately
```

Response mode is a node-level setting: `respond: immediately | using_response_node | when_finished`.

---

## 13. Trigger and polling system

### 13.1 Types

- **Manual** — user clicks "Execute".
- **Webhook** — see §12.
- **Schedule** — cron/interval.
- **Polling** — fetch an API every N seconds, emit new items.
- **Event bus** — Redis pub/sub topic (for workflow-to-workflow triggers).

### 13.2 Scheduler

Weftlyflow uses **both**:
- **Celery Beat** for durable cron (persisted schedule entries).
- **APScheduler** (in the leader API process) for per-workflow polling with dynamic add/remove without a Beat redeploy.

### 13.3 Leader election

The active-workflow manager must not run on every replica. Implementation:
- `SET weftlyflow:leader:lock <instance-id> NX EX 30` every 10 seconds.
- Only the leader runs APScheduler and webhook registration against external services.
- On loss of leadership, the new leader reads `webhooks` + active workflows and replays registrations.

---

## 14. Queue and worker system

### 14.1 Queues

| Queue | Consumer | Purpose |
|---|---|---|
| `executions` | worker | `execute_workflow(workflow_id, trigger_payload)` |
| `polling` | worker | `poll_workflow_node(workflow_id, node_id)` |
| `io` | worker | outbound HTTP calls (OAuth refresh, external webhook registration) |
| `priority` | worker | manual/test runs (jumps the queue) |
| `beat` | beat | Celery Beat internal |

### 14.2 Task idempotency

Every enqueued execution carries a deterministic `idempotency_key`. Redis `SETNX` on this key prevents duplicate runs from at-least-once delivery.

### 14.3 Sandbox runner

`worker.sandbox_runner.py` is the **subprocess entrypoint** for the Code node. Isolation layers:
1. Separate Python process (spawn via `multiprocessing.spawn`).
2. `RestrictedPython`-compiled user code.
3. `resource.setrlimit(RLIMIT_AS, 256 MB)`, `RLIMIT_CPU=30`.
4. `os.chdir('/tmp/empty_dir')` — no filesystem context.
5. `os.setuid(nobody)` on systems that allow it (optional).
6. IPC via `multiprocessing.Queue` with a JSON-only serializer (no pickle).

---

## 15. REST API surface

All routes under `/api/v1/`. Auth via `Authorization: Bearer <jwt>` unless noted.

### 15.1 Auth
- `POST /auth/login` → `{access_token, refresh_token}`
- `POST /auth/refresh`
- `POST /auth/logout`
- `POST /auth/mfa/setup`, `POST /auth/mfa/verify`
- `POST /auth/register` (gated by `WEFTLYFLOW_REGISTRATION_ENABLED`)

### 15.2 Workflows
- `GET /workflows?project_id=&tag=&active=&q=&page=`
- `POST /workflows`
- `GET /workflows/{id}`
- `PUT /workflows/{id}`
- `DELETE /workflows/{id}` (soft delete)
- `POST /workflows/{id}/activate` | `/deactivate`
- `POST /workflows/{id}/execute` (manual; body = initial items)
- `GET /workflows/{id}/history`
- `POST /workflows/{id}/share` (assign role to user)

### 15.3 Executions
- `GET /executions?workflow_id=&status=&from=&to=&page=`
- `GET /executions/{id}`
- `POST /executions/{id}/cancel`
- `POST /executions/{id}/retry`
- `GET /executions/{id}/run-data`
- WebSocket `/ws/executions/{id}` — live events

### 15.4 Credentials
- `GET /credentials?type=&project_id=`
- `POST /credentials`
- `PUT /credentials/{id}`
- `DELETE /credentials/{id}`
- `POST /credentials/{id}/test`
- `POST /credentials/oauth2/authorize-url`
- `GET /oauth2/callback`

### 15.5 Node types
- `GET /node-types` — full catalog (cached, ETag)
- `GET /node-types/{type}@{version}` — single definition

### 15.6 Projects / users / tags / variables
Straightforward CRUD for each.

### 15.7 Public webhooks
- `ANY /webhook/{path:path}` — not under `/api/v1/`, no auth by default.
- `ANY /webhook-test/{path:path}`

### 15.8 Health & meta
- `GET /healthz` — liveness
- `GET /readyz` — readiness (DB, Redis reachable)
- `GET /metrics` — Prometheus
- `GET /api/v1/config` — feature flags for the frontend

---

## 16. Authentication, authorization, multi-tenancy

### 16.1 Password handling
- `argon2-cffi` with `Argon2id`, params from OWASP 2024 recommendations.
- Passwords never logged; redaction via structlog processor.

### 16.2 JWT
- Access token: 15-minute TTL, stateless.
- Refresh token: 14-day TTL, stored hashed in `refresh_tokens` table; revocable.

### 16.3 Roles and scopes

| Global role | Scopes granted |
|---|---|
| `owner` | `*` (everything) |
| `admin` | user management, instance settings, all projects |
| `member` | workflows/credentials within projects they belong to |

Per-resource roles (on workflow/credential):
- `owner` — full including delete
- `editor` — edit, execute
- `viewer` — read-only

Scope check: `has_scope(user, "workflow:execute", resource=wf)` combines global + per-resource.

### 16.4 Projects
Every mutation takes a project context from the current JWT claim `default_project_id`, overridable via `X-Weftlyflow-Project` header. Every query is auto-filtered by project in the repository layer — leakage-by-default prevention.

### 16.5 SSO (enterprise, phase 6)
- OIDC (Google/Microsoft/Keycloak) via `authlib`.
- SAML via `python3-saml`.

---

## 17. Frontend architecture

### 17.1 Screens

1. **Home** — workflows list, search, tag filter, new-workflow CTA.
2. **Editor** — the main canvas.
   - Left: node palette (searchable catalog).
   - Center: Vue Flow canvas.
   - Right (when a node is selected): parameter form + credentials picker + notes.
   - Bottom: execution panel (last-run status, per-node inputs/outputs).
3. **Executions** — history table with filters, per-execution drill-down.
4. **Credentials** — list + create/edit modal.
5. **Projects** — list, member management.
6. **Settings** — user profile, MFA, API keys, instance settings (admin).

### 17.2 Parameter form generator

Given `NodeSpec.properties`, render:
- `string` → `<input>` (with expression-mode toggle → CodeMirror with expression syntax).
- `options` → `<el-select>`.
- `boolean` → switch.
- `json` / `code` → CodeMirror with JSON/expression grammar.
- `credentials` → credential picker modal.
- `fixed_collection` → repeatable sub-form.
- Conditional visibility via `display_options`: watch sibling fields, hide/show.

### 17.3 Live execution overlay

When a run starts:
1. Frontend opens `WS /ws/executions/{id}`.
2. Server streams events: `node_start`, `node_finish`, `execution_finish`.
3. Canvas animates the active node; finished nodes get a green/red badge; click → see input/output in the bottom panel.

### 17.4 Undo / redo
Pinia store keeps a `history[]` ring buffer of the last 50 workflow mutations; `ctrl+z` / `ctrl+shift+z` apply forward/backward.

### 17.5 Auto-save
Debounced POST every 2 seconds when `dirty == true` to a "draft" endpoint. Explicit "Save" freezes a version in `workflow_history`.

---

## 18. AI and agent integration

### 18.1 Guiding principles

- Keep AI nodes **orthogonal** to the core engine — they're just nodes that happen to call LLMs.
- Use **LangChain Python** for primitives (LLM clients, vector stores, retrievers, memory) but wrap each in a thin Weftlyflow node — don't expose LangChain types in public APIs.
- No LangChain in `domain/` or `engine/` — prevents vendor lock-in.

### 18.2 Node families

**LLM providers** (one node each):
- `llm_openai`, `llm_anthropic`, `llm_google`, `llm_ollama`, `llm_mistral`, `llm_groq`, `llm_azure_openai`, `llm_bedrock`.

**Agents** (a node with `ai_tool` input ports):
- `agent_react` (tool-using ReAct loop).
- `agent_openai_functions` / `agent_anthropic_tools` (function-calling style).
- `agent_plan_execute` (plan-then-execute).

**Memory**:
- `memory_buffer` (full history), `memory_summary` (rolling summary), `memory_window` (last-N), `memory_vector`.

**Vector stores / embeddings**:
- `vector_pgvector`, `vector_qdrant`, `vector_pinecone`, `vector_chroma`, `vector_weaviate`.
- `embed_openai`, `embed_cohere`, `embed_local`.

**Document loaders / splitters / retrievers** as separate nodes.

**Guardrails**:
- `guard_pii_redact`, `guard_jailbreak_detect`, `guard_schema_enforce`.

**MCP (Model Context Protocol)**:
- `mcp_tool_client` — lets an agent call MCP-exposed tools.
- A Weftlyflow-as-MCP-server mode — expose active workflows as MCP tools.

### 18.3 Chat-trigger

A first-class node `trigger_chat` — renders a public chat widget at a generated URL, messages flow as workflow triggers, responses are returned via a response node. Enables the "deploy a chatbot in 5 minutes" use case.

---

## 19. Observability

### 19.1 Logging (structlog)

```python
# observability/logging.py
import structlog
log = structlog.get_logger(__name__)

# In engine:
log = log.bind(execution_id=exec.id, workflow_id=wf.id)
for node in plan:
    node_log = log.bind(node_id=node.id, node_type=node.type)
    node_log.info("node_start")
    ...
    node_log.info("node_finish", duration_ms=dt, items_out=n)
```

- JSON formatter in prod (`WEFTLYFLOW_LOG_FORMAT=json`), pretty console in dev.
- Secret redaction processor — removes any key matching `password|token|secret|authorization|api[_-]?key`.

### 19.2 Metrics (Prometheus)

Counters & histograms:
- `weftlyflow_executions_total{status,mode}`
- `weftlyflow_execution_duration_seconds` (histogram)
- `weftlyflow_node_duration_seconds{node_type}`
- `weftlyflow_webhook_requests_total{node_type}`
- `weftlyflow_active_workflows`
- `weftlyflow_http_requests_total{route,status}`

### 19.3 Tracing (OpenTelemetry)

Auto-instrument: FastAPI, SQLAlchemy, httpx, Celery. Custom spans: `workflow.execute`, `node.execute`, `expression.evaluate`.

### 19.4 Audit log

Every write mutation (`create workflow`, `delete credential`, `login`, `share workflow`, etc.) writes an `audit_events` row. Retention configurable.

---

## 20. Testing strategy

### 20.1 Tiers

| Tier | Where | Marker | What |
|---|---|---|---|
| unit | `tests/unit/` | `@pytest.mark.unit` (default) | Pure logic, no DB/network. |
| integration | `tests/integration/` | `@pytest.mark.integration` | FastAPI + SQLite-memory + fake Redis. |
| node | `tests/nodes/<node>/` | `@pytest.mark.node` | Per-node unit tests (HTTP mocked via `respx`). |
| node-live | (opt-in) | `@pytest.mark.live` | Hits real APIs; requires env creds. Not in CI default. |
| e2e | `frontend/tests/e2e/` | Playwright | Headless browser through the full stack. |
| load | `tests/load/` | `@pytest.mark.load` | Throughput benchmarks (locust). |

### 20.2 Coverage target

- Domain + engine: **90%** line, 80% branch (these are the crown jewels).
- Nodes: **80%** line.
- Server layer: **80%** line.
- Frontend: **70%** line (unit), plus E2E happy paths.

### 20.3 Golden-path E2E (Playwright)

A single spec that:
1. Registers a user.
2. Creates a workflow (Manual Trigger → HTTP Request → Set → End).
3. Executes, asserts last-node output.
4. Deletes the workflow.

Must pass on every PR.

---

## 21. Documentation strategy (mkdocs)

### 21.1 Site structure

```
docs/
├── index.md                          ← landing: what + quickstart
├── getting-started/
│   ├── install.md                    ← Docker compose + pip install
│   ├── first-workflow.md
│   └── concepts.md                   ← workflow, node, trigger, credential, expression
├── architecture.md                   ← same diagram as in this bible
├── guide/
│   ├── workflows.md
│   ├── triggers-and-schedules.md
│   ├── expressions.md
│   ├── code-node.md
│   ├── credentials.md
│   ├── ai-and-agents.md
│   ├── multi-tenancy.md
│   ├── webhooks.md
│   └── self-hosting.md
├── nodes/                            ← one page per built-in node
│   ├── core/http_request.md
│   ├── core/webhook.md
│   └── ...
├── reference/                        ← auto-generated from docstrings
│   └── weftlyflow/...                  ← mirrors the src tree
├── contributing/
│   ├── node-plugins.md
│   ├── credential-plugins.md
│   └── coding-standards.md
└── changelog.md
```

### 21.2 Auto-reference generation

`scripts/gen_ref_pages.py` walks `src/weftlyflow/` and emits one `docs/reference/*.md` per module, each containing a `::: module.path` block. Paired with `mkdocs-literate-nav` so new modules appear automatically.

### 21.3 Per-node pages

`scripts/gen_node_pages.py` reads each node's `NodeSpec` + class docstring and emits `docs/nodes/<category>/<node>.md` with display name, description, properties table, credentials used, example input/output.

### 21.4 Serve

```bash
make docs-serve   # mkdocs serve → http://localhost:8000
make docs-build   # static site in ./site/
```

---

## 22. Coding standards

### 22.1 File-level docstring

Every `.py` module begins with a module docstring:
```python
"""Workflow executor — the main loop that traverses a DAG and runs nodes.

This module owns the `WorkflowExecutor` class. It is intentionally framework-free:
it knows nothing about FastAPI, SQLAlchemy, Celery, or HTTP. It takes a `Workflow`
domain object and an `ExecutionContext` and produces a `RunData` snapshot.

Invariants:
    - Node execution order is always a reachable topological walk from the start node.
    - A node is never re-executed within a single run (loop nodes are special-cased).
    - Cancellation is cooperative; checked between nodes.

See also:
    - `docs/architecture.md` for the high-level picture.
    - `IMPLEMENTATION_BIBLE.md#8-execution-engine` for the full algorithm.
"""
```

### 22.2 Class docstring (Google style)

```python
class WorkflowExecutor:
    """Executes a workflow to completion.

    The executor is single-run: instantiate, call `run`, discard. It is **not**
    thread-safe, but multiple executors can run concurrently in different asyncio
    tasks because they share no mutable state.

    Attributes:
        hooks: `LifecycleHooks` instance — receives callbacks at each boundary.
        timeout_s: Hard wall-clock timeout for the whole run. Default is 3600.

    Example:
        >>> engine = WorkflowExecutor(hooks=DefaultHooks())
        >>> result = await engine.run(workflow, initial_items=[])
        >>> result.status
        'success'
    """
```

### 22.3 Function docstring

```python
def build_graph(workflow: Workflow) -> Graph:
    """Build a traversable graph from a workflow.

    Args:
        workflow: The workflow to analyze. Must have unique node IDs.

    Returns:
        A `Graph` with indexed adjacency lists keyed by node ID.

    Raises:
        CycleDetectedError: If the workflow contains a cycle (except
            whitelisted loop-back edges from a `SplitInBatches` node).
        InvalidConnectionError: If a connection references an unknown node.

    Example:
        >>> g = build_graph(wf)
        >>> g.parents("node_2")
        ['node_1']
    """
```

### 22.4 Logging

- Always bind context early: `log = log.bind(execution_id=..., node_id=...)`.
- One log record per meaningful event — don't log every line of code.
- Levels:
  - `debug` — rare; disabled in prod.
  - `info` — normal lifecycle (workflow started, node finished).
  - `warning` — recoverable issues (retry, rate-limit, skipped).
  - `error` — a node failed or a request errored.
  - `critical` — system-level broken state (DB unreachable, encryption key missing).

### 22.5 Errors

Every module has an `errors.py` (or uses `domain/errors.py`) with named exceptions inheriting from `WeftlyflowError`. Callers **never catch** bare `Exception` outside system boundaries (request handler, task runner, main loop).

### 22.6 Type hints
- `mypy --strict`; no `Any` without a `# type: ignore[no-any] # reason` comment.
- Prefer `TypedDict` / `Protocol` over `dict[str, Any]`.
- Use `typing.Annotated` for validated fields.

### 22.7 Comments
- **Defaults to zero comments.** Docstrings do the heavy lifting.
- A comment only explains **why** something non-obvious exists, never **what** the code does.

### 22.8 Imports
- Absolute only; ordered by isort: stdlib, third-party, first-party, local.
- `from __future__ import annotations` at top of every module.

### 22.9 Module size
- Soft cap 400 lines. Past that, split.

---

## 23. Intellectual-property compliance rules

Weftlyflow is an **independent implementation inspired by n8n's architecture**. To keep it clean:

1. **Never copy source code** from `/home/nishantgupta/Downloads/n8n-master/`. Read it for understanding, then close the file and write Weftlyflow code from scratch.
2. **Never copy identifiers** verbatim. Examples:
   - n8n: `n8n-nodes-base.httpRequest` → Weftlyflow: `weftlyflow.http_request`.
   - n8n: `IExecuteFunctions` → Weftlyflow: `ExecutionContext` / `NodeExecuteHelpers`.
   - n8n: `IRunExecutionData` → Weftlyflow: `RunData`.
   - n8n: `$json`, `$input.all()` — generic enough to keep, but our evaluator is our own.
3. **Never copy credential slugs.** n8n: `slackOAuth2Api` → Weftlyflow: `weftlyflow.credential.slack_oauth2`.
4. **Never copy node SVG icons.** Source our own from Lucide / Simple Icons (CC0 or MIT).
5. **Never copy test fixtures** containing n8n's sample API responses. Re-record our own.
6. **Never copy commit messages, PR descriptions, or changelog entries.**
7. **Never copy the workflow JSON schema.** Ours intentionally differs (see §7).
8. **Never fork any n8n file into this repo** — not even as a "starting point."
9. **Re-read primary API docs** (not n8n's integrations code) when writing integration nodes. Cite the provider's official documentation in the node module docstring.
10. **If in doubt, ask.** A PR that introduces content with uncertain provenance must state provenance in the description.

The `.claude/` agents include a **`ip-checker`** agent that scans new files for suspicious similarity (identifiers, string literals) against the n8n source.

---

## 24. Phased delivery roadmap

### Phase 0 — Bootstrap (this session + next)

Goal: a repo that lints, builds docs, and has a working CI loop with a "hello" workflow executing end-to-end through an in-memory stub engine.

**Deliverables:**
- [x] `IMPLEMENTATION_BIBLE.md` (this file)
- [x] `.claude/` adapted
- [x] `pyproject.toml`, `Makefile`, `README.md`, `LICENSE`, `.gitignore`
- [x] `docker-compose.yml` + `Dockerfile`s
- [x] `pre-commit` config (ruff, black, isort, mypy)
- [x] `mkdocs.yml` + `docs/index.md` + auto-reference generation
- [x] Directory tree with every `__init__.py` carrying a module docstring
- [x] `src/weftlyflow/config/settings.py` — Pydantic settings
- [x] `src/weftlyflow/config/logging.py` — structlog (lives under `config/` since
      it is boot-time setup, not a reusable runtime utility; see the docstring
      in `src/weftlyflow/observability/__init__.py`)
- [x] `src/weftlyflow/cli.py` — Typer skeleton
- [x] `tests/unit/test_smoke.py` — passing smoke test

**Acceptance:** `make lint && make typecheck && make test && make docs-build` all green.

### Phase 1 — Core engine (2–3 sessions)

Goal: a callable Python API that runs a workflow in-memory.

**Deliverables:**
- [x] Domain dataclasses (Workflow, Node, Connection, Execution, Item, RunData).
- [x] `engine.graph` — DAG analysis (Kahn's topo + cycle detection + fan-in/out).
- [x] `engine.executor.WorkflowExecutor.run()` — readiness-based async scheduler.
- [x] `engine.hooks.LifecycleHooks` + `NullHooks` default.
- [x] `nodes.registry.NodeRegistry` + `@register_node` decorator + `load_builtins()`.
- [x] Tier-1 core nodes: Manual Trigger, If, Set, NoOp, Code (identity stub).
- [x] Unit tests: happy-path, branching, continue-on-fail, error propagation,
      disabled nodes, pin_data, unknown node type, execution-id override,
      every predicate operator, dotted-path helpers, registry semantics.

**Acceptance:** `tests/unit/engine/test_five_node_run.py` constructs a 5-node
workflow (ManualTrigger → Set → If → NoOp | Code), runs it through
:class:`WorkflowExecutor`, and asserts routing + tagging produced the expected
shape. Full `make lint && make typecheck && make test && make docs-build` is
green.

### Phase 2 — Persistence + API (2–3 sessions)

- [x] SQLAlchemy 2.x entities (users, projects, workflows, executions,
      execution_data, refresh_tokens) + typed ``Mapped[...]`` style + Alembic
      initial migration.
- [x] Async repositories (user, project, workflow, execution, refresh_token)
      — all project-scoped on mutable queries.
- [x] FastAPI routers: ``auth`` (login/refresh/logout/register/me),
      ``workflows`` (CRUD + execute), ``executions`` (list + detail),
      ``node_types`` (catalog + by-type), ``health`` (readyz pings DB).
- [x] JWT auth (argon2id passwords, access + refresh pair, rotation +
      revocation) + project-scoping deps.
- [x] Structlog request-id middleware with access-log emission.
- [x] First-boot admin + project seed (env-driven in prod, auto-generated
      in dev).

**Acceptance:** ``tests/integration/test_workflow_lifecycle.py::test_post_workflow_execute_read``
walks login → POST /workflows → POST /workflows/{id}/execute → GET
/executions/{id} and asserts routing + tagging on the returned run-data.
Full ``make lint && make typecheck && make test && pytest -m integration
&& make docs-build`` is green (96 tests pass).

### Phase 3 — Workers + webhooks + triggers (2–3 sessions)

- Celery app, task `execute_workflow`.
- Redis job queue, leader election.
- Webhook router + registry.
- APScheduler-driven polling.
- Manual-trigger + webhook-trigger + schedule-trigger nodes.

**Acceptance:** An HTTP POST to a webhook URL triggers a workflow, which executes in a worker and writes the execution.

### Phase 4 — Expression engine + credentials (1–2 sessions)

- `{{ ... }}` tokenizer + RestrictedPython sandbox.
- Proxies (`$json`, `$input`, `$now`, ...).
- Credential registry + Fernet encryption.
- Credential types: bearer, basic, API key (header/query), generic OAuth2.
- OAuth2 callback route + refresh task.

**Acceptance:** HTTP Request node can use a credential and an expression in its URL.

### Phase 5 — Frontend MVP (3–4 sessions)

- Vue 3 + Vite scaffold.
- Pinia stores, typed API client.
- Editor view with Vue Flow canvas, node palette, parameter form generator.
- Executions view (list + detail with run-data inspector).
- Credentials view.
- Golden-path Playwright E2E test.

**Acceptance:** A user can build + run a workflow entirely in the browser.

### Phase 6 — Integration nodes wave 1 (ongoing, each integration is a ticket)

Tier-2 nodes (see §25). Add them one PR at a time — never in a single mega-PR.

### Phase 7 — AI nodes (3–4 sessions)

- LLM provider nodes (OpenAI, Anthropic, Ollama).
- ReAct agent node.
- Memory + vector store nodes.
- Chat trigger.

### Phase 8 — Hardening (ongoing)

- SAML/OIDC SSO.
- Prometheus/OTel dashboards.
- Kubernetes Helm chart.
- External-secrets integration.
- Role-based audit log retention.

---

## 25. Node porting priority

See `memory/project_weftlyflow.md` for context. These are the Weftlyflow-side names — do **not** copy n8n's slugs.

### Tier 1 — MVP core (must ship in Phase 1–4, ~24 nodes)

Control flow (6): `if`, `switch`, `merge`, `filter`, `split_in_batches`, `evaluate_expression`.

Data manipulation (9): `set`, `rename_keys`, `transform`, `datetime_ops`, `html_parse`, `xml_parse`, `compare_datasets`, `read_binary_file`, `write_binary_file`.

Execution control (5): `code`, `function_call`, `wait`, `noop`, `stop_and_error`.

Triggers (3): `manual_trigger`, `webhook_trigger`, `schedule_trigger`.

Utility (1): `execution_data`.

### Tier 2 — Popular integrations (Phase 6, ~40 nodes)

Communication: `slack`, `discord`, `telegram`, `whatsapp`, `twilio_sms`, `sendgrid`, `mailgun`, `smtp_email`, `brevo`.

CRM: `salesforce`, `hubspot`, `pipedrive`, `zendesk`, `freshdesk`, `intercom`.

Productivity: `notion`, `airtable`, `asana`, `monday`, `clickup`, `trello`, `jira`, `github`, `gitlab`, `google_sheets`, `google_drive`, `gmail`, `google_calendar`, `ms_teams`, `outlook`, `excel`, `onedrive`, `dropbox`.

E-commerce: `shopify`, `woocommerce`, `stripe`, `paypal`, `chargebee`.

### Tier 3 — Long tail (Phase 6+, ~240 nodes)

Per-integration ticket. Don't bulk-port.

### AI nodes (Phase 7, ~15 nodes to start)

LLM: `llm_openai`, `llm_anthropic`, `llm_google`, `llm_ollama`, `llm_mistral`.

Agents: `agent_react`, `agent_openai_functions`, `agent_anthropic_tools`.

Memory: `memory_buffer`, `memory_summary`, `memory_window`.

Vector: `vector_pgvector`, `vector_qdrant`, `embed_openai`, `embed_local`.

Chat: `trigger_chat`, `chat_respond`.

---

## 26. Risk register

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| 1 | Scope overrun (441 nodes) | Miss v1 indefinitely | Strict Tier 1 scope; defer Tier 3 to community contributions. |
| 2 | Code-node sandbox escape | RCE / data exfiltration | Layered defense: RestrictedPython + subprocess + rlimits + Docker container. Pentest before v1. |
| 3 | IP / license dispute | Legal risk | §23 rules; automated IP-checker agent in `.claude/`; clean-room process. |
| 4 | Execution perf vs n8n | Users perceive us as slow | Profile early; use asyncio throughout; batch DB writes; pg `COPY` for bulk run-data. |
| 5 | Credential encryption key loss | All credentials unusable | `MultiFernet` rotation; documented backup procedure in `docs/self-hosting.md`. |
| 6 | Leader election split-brain | Duplicate webhook registrations | TTL-based lock; deterministic recovery — every new leader reconciles against `webhooks` table. |
| 7 | Expression sandbox bypass | RCE in a benign-looking field | RestrictedPython + attr guards; fuzz-test the sandbox in CI. |
| 8 | Vue Flow upstream changes | Editor breaks | Pin minor version; contract tests around graph mutations. |
| 9 | OAuth token refresh storms | Rate-limited by providers | Jittered refresh schedule; exponential backoff per provider. |
| 10 | Execution data bloat | DB balloons | Pluggable storage backends (DB / FS / S3); TTL cleanup task; "save failed only" mode. |
| 11 | Weftlyflow maintainers burnout | Project stalls | Automate aggressively: `.claude/` skills for PR review, node scaffolding, doc generation. |

---

## 27. Revision log

| Date (YYYY-MM-DD) | Author | Change |
|---|---|---|
| 2026-04-21 | Initial | First draft as **Loomflow**. Stack locked: Python 3.12 / FastAPI / SQLAlchemy 2 / Vue 3 / Vue Flow / Celery / Redis / RestrictedPython. |
| 2026-04-21 | Rename | **Loomflow → Weftlyflow.** Reason: `loomflow.com` was held by an unrelated Mumbai catalog-software firm; `weftlyflow` validated clean on PyPI, npm, GitHub, and trademark registries. Python package path changed from `src/loomflow/` to `src/weftlyflow/`; env-var prefix `LOOMFLOW_` → `WEFTLYFLOW_`; node-type slugs `loomflow.*` → `weftlyflow.*`. Mass find/replace across 91 files; `LoomDateTime` identifier replaced with `WeftlyflowDateTime`; no functional changes. |

---

*End of bible. All subsequent design changes must update this file (and its revision log) in the same PR as the change.*
