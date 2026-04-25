# How to Read This Project (New-Developer Path)

> A 7-step learning path. Follow it in order — each step compounds on the last,
> so by the end you can read any file in the repo and place it on the mental
> map.

<div class="grid cards" markdown>

-   :material-numeric-1-circle:{ .lg .middle } &nbsp;**The 60-second pitch**

    ---

    *Workflow automation, like Zapier/n8n, self-hostable, written in Python.*
    A workflow is a **directed graph of nodes**. A trigger fires; the engine
    walks the graph; each node transforms a list of *items*; the result is
    persisted as an *execution*.

-   :material-numeric-2-circle:{ .lg .middle } &nbsp;**Three processes, one repo**

    ---

    `weftlyflow-api` (FastAPI) + `weftlyflow-worker` (Celery) +
    `weftlyflow-beat` (Celery Beat). They share `src/weftlyflow/` and talk over
    Postgres + Redis. See [`docker-compose.yml`](#).

-   :material-numeric-3-circle:{ .lg .middle } &nbsp;**The dependency rule**

    ---

    `server, worker, webhooks, triggers → engine → nodes, credentials, expression → domain`.
    Anything in `domain/` imports nothing else from the project. Memorise this;
    every layer above respects it.

</div>

## The 7-step reading order

Each step gives you a file (or two) to open, and the *one thing* you should
take away from it. Resist the urge to dive deeper — depth comes in later steps.

### Step 1 — The package manifest

**Open:** `pyproject.toml`

**Take away:** What we depend on, and what features are gated behind extras.
Notice:

- `dependencies` is small but pointed — FastAPI, SQLAlchemy 2.x, Celery,
  RestrictedPython, structlog. Each one anchors a subsystem you'll meet later.
- `optional-dependencies.ai` (LangChain, OpenAI, Anthropic) is **opt-in** —
  the AI nodes import lazily so non-AI installs stay slim.
- `[project.entry-points."weftlyflow.nodes"]` is the third-party plugin point.

### Step 2 — The package boundary

**Open:** [`src/weftlyflow/__init__.py`](https://github.com/aignishant/weftlyflow/blob/main/src/weftlyflow/__init__.py)

**Take away:** The 13-subpackage map, in the docstring. Every import path you
encounter later resolves under one of these subpackages. The docstring is the
canonical layout reference.

### Step 3 — The CLI entry points

**Open:** [`src/weftlyflow/cli.py`](https://github.com/aignishant/weftlyflow/blob/main/src/weftlyflow/cli.py)
&nbsp;|&nbsp; [`src/weftlyflow/__main__.py`](#)

**Take away:** Every long-running process boots through one of:

| Command | Process | Wires to |
| ------- | ------- | -------- |
| `weftlyflow start` | API server | `weftlyflow.server.app:app` |
| `celery -A weftlyflow.worker.app worker` | Worker | `weftlyflow.worker.tasks` |
| `celery -A weftlyflow.worker.app beat` | Beat | `worker.app.celery_app.conf.beat_schedule` |

### Step 4 — The conceptual model (`domain/`)

**Open:** in this order:

1. [`domain/workflow.py`](https://github.com/aignishant/weftlyflow/blob/main/src/weftlyflow/domain/workflow.py) — `Workflow`, `Node`, `Connection`, `Port`.
2. [`domain/execution.py`](#) — `Execution`, `NodeRunData`, `Item`, `NodeError`.
3. [`domain/node_spec.py`](#) — `NodeSpec`, `PropertySchema`, `NodeCategory`.

**Take away:** These are **plain dataclasses with no IO**. Everything else in
the codebase is a function over these types or a translation layer from/to
them. Keep this file open in a side panel for the rest of your reading.

### Step 5 — The engine

**Open:** in this order:

1. [`engine/graph.py`](#) — converts `Workflow` → traversable `WorkflowGraph`.
2. [`engine/runtime.py`](#) — `RunState`, the per-execution mutable accumulator.
3. [`engine/context.py`](#) — `ExecutionContext`, what nodes see at runtime.
4. [`engine/executor.py`](#) — the main loop. **This is the most important
   file in the project.** Read every line.
5. [`engine/hooks.py`](#) — lifecycle hooks (the persistence + logging seam).

**Take away:** Execution = breadth-first walk of the graph in readiness order,
where readiness = "all unique parents have produced output". The executor
itself does **no IO** — persistence happens through `LifecycleHooks`.

### Step 6 — The plugin system

**Open:**

1. [`nodes/base.py`](#) — `BaseNode`, `BaseTriggerNode`, `BasePollerNode`.
2. [`nodes/registry.py`](#) — keyed by `(spec.type, spec.version)`.
3. [`nodes/discovery.py`](#) — built-in auto-load + entry-point loader.
4. Pick **one** node end-to-end, e.g. `nodes/core/http_request/`.

**Take away:** A node is a class with a `spec: NodeSpec` and an `async execute`.
The registry doesn't care where the class lives. New nodes never modify core.

### Step 7 — The boundary layers

**Open:**

1. [`server/app.py`](#) — FastAPI `lifespan` is the *integration test* for
   what the system needs to boot.
2. [`server/routers/workflows.py`](#) — REST shape for the most-used resource.
3. [`worker/tasks.py`](#) — what the queue consumes.
4. [`triggers/manager.py`](#) — how a "save + activate" turns into webhook
   registrations and scheduler entries.

**Take away:** Every router method is thin — it validates a Pydantic schema,
calls into the engine or a repository, and maps the result back to a schema.
Business logic does not live in routers.

## After step 7

You're now equipped to read any file. The remaining walkthrough pages are
**reference**, not narrative — open them when you need depth on a specific
module:

- [Backend overview](backend/index.md) → all 13 backend subpackages.
- [Frontend](frontend.md) → Vue 3 / Pinia / Vue Flow editor.
- [Data flow](data-flow.md) → what happens between trigger fire and DB row.
- [Source backtracking](source-backtrack.md) → "where does this symbol live?"

## Reading-order shortcuts by role

=== "Backend engineer"

    1. `domain/` → `engine/` → `nodes/base.py` → `worker/tasks.py`
    2. `db/entities/` → `db/repositories/` → `server/routers/workflows.py`
    3. `engine/hooks.py` → `server/persistence_hooks.py`

=== "Frontend engineer"

    1. `frontend/src/main.ts` → `App.vue` → `router/index.ts`
    2. `views/Editor.vue` → `components/canvas/WorkflowNodeCard.vue`
    3. `stores/workflows.ts` → `api/endpoints.ts` → `api/client.ts`

=== "Integrations / node author"

    1. `domain/node_spec.py` → `nodes/base.py` → `nodes/registry.py`
    2. `nodes/core/http_request/` (a complete reference node)
    3. `credentials/types/` → `credentials/registry.py`
    4. `contributing/node-plugins.md` (in the main docs)

=== "Platform / DevOps"

    1. `docker/`, `docker-compose.yml`, `deploy/helm/`
    2. `config/settings.py` → `config/logging.py`
    3. `db/migrations/` → `alembic.ini`
    4. `observability/metrics.py` → `server/routers/metrics.py`

=== "Security review"

    1. `auth/` (passwords, JWT, scopes, SSO)
    2. `credentials/cipher.py` → `credentials/resolver.py`
    3. `expression/sandbox.py` → `expression/proxies.py`
    4. `worker/sandbox_runner.py`, `worker/sandbox_child.py`
    5. `utils/redaction.py`

!!! success "You're done with onboarding"
    Continue with the [repository tour](repo-tour.md) for the top-level layout,
    or jump straight to the [backend deep-dive](backend/index.md).
