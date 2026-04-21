# Architecture

> This page is a condensed view of `IMPLEMENTATION_BIBLE.md §5`. The bible is the canonical source — edit it first, then mirror the changes here.

## Processes

1. **`weftlyflow-api`** — FastAPI + WebSocket. Accepts REST calls, registers live execution streams, hosts the editor's backend.
2. **`weftlyflow-worker`** — one or more Celery workers. Runs workflows, refreshes OAuth tokens, writes execution results.
3. **`weftlyflow-beat`** — single instance. Celery Beat — emits scheduled triggers.

Stateful services: **Postgres** (prod) / **SQLite** (dev) for persistence, **Redis** for Celery broker + pub/sub + leader election.

## Layer diagram

```
                 ┌──────────────────────────────────────────────────────────┐
                 │                   Browser (Vue 3 + Vue Flow)             │
                 └───────────────┬──────────────────┬───────────────────────┘
                                 │ REST            │ WebSocket
                                 ▼                  ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                          Weftlyflow API server (FastAPI)                     │
└──────┬──────────────────┬───────────────────┬────────────────┬─────────────┘
       ▼                  ▼                   ▼                ▼
  ┌────────┐      ┌──────────────┐      ┌──────────┐    ┌──────────────┐
  │ SQL DB │      │ Redis        │      │ Trigger  │    │  Secrets /   │
  │        │      │              │      │ registry │    │  Key Vault   │
  └────────┘      └──────────────┘      └──────┬───┘    └──────────────┘
                          ▲                    │
                          │ task enqueue       │ fires
                          ▼                    ▼
                   ┌────────────────────────────────────┐
                   │        Celery worker fleet         │
                   └────────────────────────────────────┘
```

## Dependency rule

`server, worker, webhooks, triggers → engine → nodes, credentials, expression → domain`

`domain/` imports **nothing** from other Weftlyflow subpackages. This is enforced in review (see `.claude/agents/code-reviewer.md`).

## Data flow on execution

1. Trigger fires (webhook POST, scheduled tick, manual click).
2. API writes an `Execution` row with status `new`.
3. Celery task `execute_workflow(execution_id)` is enqueued.
4. Worker fetches the execution, builds an `ExecutionContext`, instantiates the `WorkflowExecutor`, walks the graph.
5. For each node: engine resolves parameters (including `{{ ... }}` expressions), calls `node.execute(ctx, items)`, records `NodeRunData`.
6. On completion: worker writes final `run_data`, status, `finished_at`; publishes to `exec-events:{execution_id}` Redis channel.
7. Browser's WebSocket consumer receives events, updates the canvas overlay in real time.

## Further reading

- `IMPLEMENTATION_BIBLE.md §7` — domain model.
- `IMPLEMENTATION_BIBLE.md §8` — engine algorithm.
- `IMPLEMENTATION_BIBLE.md §9` — node plugin system.
- `IMPLEMENTATION_BIBLE.md §10` — expression engine.
