# Domain → Engine → Nodes

> The conceptual pipeline. Reading these three subpackages in order is the
> single fastest way to understand the system. Allow ~45 minutes for a careful
> first pass.

## Layer 0 — `domain/`

:material-folder: `src/weftlyflow/domain/`

Pure dataclasses. **Imports nothing from the rest of the project.** Other
layers import *from* domain; this is the load-bearing isolation rule.

### Files

| File | What lives here |
| ---- | --------------- |
| `__init__.py` | Re-exports the public surface (`Workflow`, `Node`, `Item`, …). |
| `workflow.py` | `Workflow`, `Node`, `Connection`, `Port`, `RetryPolicy`, `WorkflowSettings`. |
| `execution.py` | `Execution`, `NodeRunData`, `RunData`, `Item`, `BinaryRef`, `NodeError`, `PairedItem`. |
| `node_spec.py` | `NodeSpec`, `PropertySchema`, `NodeCategory`, property type enums. |
| `credential.py` | `Credential` dataclass + `CredentialField`. |
| `errors.py` | `WeftlyflowError` root, `WorkflowValidationError`, `CycleDetectedError`, `InvalidConnectionError`, `NodeExecutionError`. |
| `ids.py` | `new_workflow_id()`, `new_node_id()`, `new_execution_id()`, `new_webhook_id()` — ULID-based. |
| `constants.py` | `MAIN_PORT`, port-kind literals, default values. |

### `domain/workflow.py` — class-by-class

:material-tag: `Port`
: Frozen dataclass. Logical name (`"main"`, `"true"`, `"false"`, `"ai_tool"`),
  `kind` (`PortKind` literal), zero-based `index`, optional `display_name`,
  `required` flag.

:material-tag: `RetryPolicy`
: `max_attempts`, `backoff_factor`, `base_delay_ms`, `max_delay_ms`. Per-node
  retry config (default: no retry).

:material-tag: `Node`
: A single step. Mutable on `parameters` and `position` only. Carries:
  `id`, `name`, `type` (registry key like `"weftlyflow.http_request"`),
  `type_version`, `parameters` dict (validated against `PropertySchema`),
  `credentials` slot-name → credential-id map, `position` (UI only),
  `disabled`, `notes`, `continue_on_fail`, `retry_policy`.

:material-tag: `Connection`
: Frozen edge. `source_node`, `source_port`, `source_index`,
  `target_node`, `target_port`, `target_index`. The executor's
  `WorkflowGraph` indexes these into `OutgoingEdge` / `IncomingEdge`.

:material-tag: `WorkflowSettings`
: Per-workflow execution settings — error-workflow id, save-data-options,
  timezone, caller-policy.

:material-tag: `Workflow`
: The whole graph. `id`, `name`, `nodes`, `connections`, `active`,
  `settings`, `static_data`, `pin_data`, `tags`, `created_at`, `updated_at`,
  `version`.

### `domain/execution.py` — the run record

:material-tag: `Item`
: One record flowing between nodes. `json` (the structured payload),
  `binary` (named refs to large blobs), `paired_item` (lineage),
  `error` (set when `continue_on_fail` produced an error item).

:material-tag: `BinaryRef`
: Pointer to binary data — `filename`, `mime_type`, `size_bytes`, `data_ref`
  (`"db:<id>"`, `"fs:/path"`, `"s3://bucket/key"`).

:material-tag: `NodeRunData`
: One run of a single node. Status `"success"` / `"error"` / `"disabled"`,
  `items: list[list[Item]]` (port × items axis), `started_at`,
  `execution_time_ms`, optional `error`.

:material-tag: `RunData`
: `per_node[node_id]` is a *list* (not single entry) because loop nodes can
  re-run the same node many times.

:material-tag: `Execution`
: `id`, `workflow_id`, `workflow_snapshot` (frozen at start time —
  edits-during-run can't corrupt the record), `mode`, `status`,
  `started_at`, `finished_at`, `run_data`.

### `domain/node_spec.py`

:material-tag: `NodeSpec`
: A node's manifest. `type`, `version`, `display_name`, `description`,
  `icon`, `category` (a `NodeCategory` enum: `CORE`, `AI`, `INTEGRATION`,
  `TRIGGER`, `UTILITY`), `inputs: list[Port]`, `outputs: list[Port]`,
  `properties: list[PropertySchema]`, `credentials_required: list[str]`,
  `subtitle_template`, `defaults`, `webhook_settings`, `polling`.

:material-tag: `PropertySchema`
: One UI form field. Type, name, label, placeholder, default, options,
  `display_options` (conditional show/hide), validators.

### `domain/errors.py` — exception hierarchy

```
WeftlyflowError
├── WorkflowValidationError
│   ├── CycleDetectedError
│   └── InvalidConnectionError
└── NodeExecutionError
```

All raised exceptions in node code or engine code derive from
`WeftlyflowError`. Surface code in `server/errors.py` maps these to HTTP
codes.

---

## Layer 1 — `engine/`

:material-folder: `src/weftlyflow/engine/`

The pure execution kernel. **No IO, no DB, no FastAPI.** All side effects
exit through `LifecycleHooks`.

### Files

| File | What lives here |
| ---- | --------------- |
| `executor.py` | :material-flash: `WorkflowExecutor`. The main loop. |
| `graph.py` | `WorkflowGraph` + `OutgoingEdge` / `IncomingEdge`. Validates DAG-shape, exposes O(1) neighbour queries. |
| `runtime.py` | `RunState` — per-run mutable accumulator. |
| `context.py` | `ExecutionContext` — the per-node view handed to `node.execute()`. |
| `hooks.py` | `LifecycleHooks` Protocol + `NullHooks` default. |
| `subworkflow.py` | `SubWorkflowRunner` — for nodes that nest workflows. |
| `errors.py` | `NodeTypeNotFoundError` (registry miss). |
| `constants.py` | `STATUS_SUCCESS`, `STATUS_ERROR`, `STATUS_DISABLED`. |

### `engine/executor.py` — `WorkflowExecutor` :material-flash:

The single most important class in the project. Read every line of
`src/weftlyflow/engine/executor.py:59-269`.

**Constructor** — `WorkflowExecutor(registry, *, hooks=None,
credential_resolver=None, sub_workflow_runner=None)`. Stateless: one instance
is safe to reuse across runs.

**Method: `run(workflow, *, initial_items=None, mode="manual",
execution_id=None) -> Execution`** — the entry point.

1. Build a `WorkflowGraph` from the immutable workflow.
2. Initialise a fresh `RunState`.
3. Seed root nodes with `initial_items`.
4. Compute initial *pending parents* per node (the readiness gate).
5. Drain the ready queue:
    - Pop a node id.
    - Build its `ExecutionContext`.
    - Fire `on_node_start` hook.
    - Call `_run_one(node, ctx, state)` — executes, captures `NodeRunData`.
    - Record metrics (`metrics.node_duration_seconds`).
    - Fire `on_node_end` hook.
    - On error without `continue_on_fail`: mark state failed, fall through.
    - Otherwise: propagate outputs to downstream input buckets, mark
      newly-ready downstream nodes.
6. Build the final `Execution` from `RunState`. Emit metrics. Fire
   `on_execution_end`.

**Method: `_run_one(node, ctx, state)`** — disabled-node short-circuit,
pin-data short-circuit, otherwise resolve the node class via
`_resolve_node`, call `implementation.execute(ctx, ctx.get_input(MAIN_PORT))`,
catch exceptions and route through `_handle_node_exception`.

**Method: `_resolve_node(node)`** — looks up `(node.type, node.type_version)`
in the registry. Raises `NodeTypeNotFoundError` for unknown types or when a
trigger/poller is referenced as an action.

**Method: `_handle_node_exception(...)`** — :material-shield-lock:
**Always routes the exception message through
`utils.redaction.safe_error_message`** so credential decrypt errors, HTTP
response bodies, and DB DSNs never land in `NodeError.message`. Operators
keep the full traceback in structured logs.

**Module-level helpers** (intentionally not methods — keep `WorkflowExecutor`
small and `__slots__`-friendly):

| Function | Purpose |
| -------- | ------- |
| `_seed_inputs_for_roots` | Inject `initial_items` on root nodes. |
| `_compute_initial_pending` | Build the `{node: {parent_node, …}}` readiness map. |
| `_propagate_outputs` | Push a node's outputs into downstream input buckets. |
| `_advance_readiness` | Discard a finished parent; enqueue any node whose pending set hits empty. |
| `_items_for_source_index` | Bounds-safe accessor into `outputs[port_idx]`. |
| `_disabled_run_data` | Pass-through `NodeRunData` for `node.disabled`. |
| `_elapsed`, `_elapsed_ms` | Build `NodeRunData` with timing. |
| `_exit_context`, `_synthetic_node` | Edge cases for empty workflows. |

### `engine/graph.py` — `WorkflowGraph`

Pure shape analysis. Builds:

- `_outgoing[node_id] -> list[OutgoingEdge]`
- `_incoming[node_id] -> list[IncomingEdge]`
- `root_ids` (no incoming edges)
- `topological_order()` (Kahn's algorithm; raises `CycleDetectedError`)

Validates:

- Every connection's `source_node` and `target_node` exist.
- Port kinds are compatible (`main` ↔ `main`, `ai_tool` ↔ `ai_tool`).
- No cycles.
- No connection to a `disabled` trigger node.

### `engine/runtime.py` — `RunState`

See `src/weftlyflow/engine/runtime.py:31-89`. Mutable, owned by the executor.
Exposes:

- `record(node_id, run_data)` — appends to `run_data.per_node[node_id]`,
  caches latest port outputs.
- `mark_failed(node_id, error)` — sets the abort flags.
- `build_execution()` — finalises into an immutable `Execution`.

The `static_data` field is seeded in `__post_init__` from
`workflow.static_data` *defensively copied* so per-run mutations don't leak
into the workflow snapshot.

### `engine/context.py` — `ExecutionContext`

The narrow per-node view. Methods nodes actually call:

| Method | Returns |
| ------ | ------- |
| `param(name, default)` | Raw parameter (no expression eval). |
| `resolved_param(name, default)` | Parameter with `{{ ... }}` evaluated against current proxies. |
| `get_input(port="main")` | List of `Item` on the named port. |
| `input_port(name)` | Same, named for clarity in multi-port nodes. |
| `credentials(slot_name)` | Resolved decrypted credential dict (via `CredentialResolver`). |
| `static(key, default)` | Read from per-workflow `static_data`. |
| `set_static(key, value)` | Write to `static_data` (persisted post-run). |
| `proxies()` | Build `{ "$json": ..., "$now": ..., "$node": ... }` for expression resolution. |
| `binary` | Access the configured `BinaryStore`. |

The `_cached_exposed_env()` LRU-1 snapshots `os.environ ∩ allowlist` once
per process so expression evaluation stays allocation-free on the hot path.

### `engine/hooks.py` — `LifecycleHooks` Protocol

Six methods, all `async`, all return `None`:

- `on_execution_start(ctx)`
- `on_execution_end(ctx, execution)`
- `on_node_start(ctx, node)`
- `on_node_end(ctx, node, run_data)`
- `on_node_error(ctx, node, error)`
- `on_node_progress(ctx, node, payload)` — for streaming nodes (LLM tokens, etc.)

`NullHooks` implements them all as no-ops; the executor uses it when no hook
is provided so the loop never branches on `hooks is None`.

Production wiring lives in `server/persistence_hooks.py` (writes
`ExecutionEntity` rows + publishes to `exec-events:{execution_id}` on Redis
for the WebSocket consumer).

### `engine/subworkflow.py` — `SubWorkflowRunner`

Indirection so the `execute_workflow` node can spawn a nested execution
without the engine importing the worker (which would create a cycle).

---

## Layer 2 — `nodes/`

:material-folder: `src/weftlyflow/nodes/`

The plugin system. Built-in nodes live alongside the runtime they need; the
registry treats them all as plain classes.

### Top-level files

| File | Purpose |
| ---- | ------- |
| `base.py` | `BaseNode`, `BaseTriggerNode`, `BasePollerNode`. |
| `registry.py` | `NodeRegistry` keyed by `(type, version)`. |
| `discovery.py` | Built-in auto-loader + `weftlyflow.nodes` entry-point loader. |
| `__init__.py` | Public surface. |

### Subpackages

| Subpackage | Contents |
| ---------- | -------- |
| `core/` | Engine-shipped nodes: `http_request`, `code`, `if_node`, `switch_node`, `merge_node`, `set_node`, `filter_node`, `transform_node`, `wait_node`, `manual_trigger`, `webhook_trigger`, `schedule_trigger`, `read_binary_file`, `write_binary_file`, `html_parse_node`, `xml_parse_node`, `datetime_ops_node`, `evaluate_expression_node`, `execution_data_node`, `compare_datasets`, `function_call`, `no_op`, `rename_keys_node`, `split_in_batches`, `stop_and_error_node`. |
| `ai/` | LLM + agent + memory + vector nodes: `agent_react`, `agent_tool_dispatch`, `agent_tool_result`, `chat_respond`, `embed_local`, `embed_openai`, `guard_jailbreak_detect`, `guard_pii_redact`, `guard_schema_enforce`, `memory_buffer`, `memory_window`, `memory_summary`, `memory_store.py`, `text_splitter`, `trigger_chat`, `vector_chroma`, `vector_memory`, `vector_pgvector`, `vector_pinecone`, `vector_qdrant`. |
| `integrations/` | 86 third-party services. One folder per service, each with a node module + an `__init__.py` that registers the class. Examples: `airtable/`, `slack/`, `notion/`, `github/`, `gmail/`, `openai/`, `anthropic/`, `stripe/` (… ~80 more). |
| `utils/` | `paths.py` (JSONPath + dotted-path access), `predicates.py` (filter/if/switch comparators). |

### `nodes/base.py` — the contract

:material-tag: `BaseNode`
: The action-node ABC.

  ```python
  class BaseNode(ABC):
      spec: ClassVar[NodeSpec]

      @abstractmethod
      async def execute(self, ctx: ExecutionContext, items: list[Item]) -> list[list[Item]]:
          ...
  ```

  Returns `[output_port_index][item_index]`. A single-output node returns
  `[[item1, item2, ...]]`.

:material-tag: `BaseTriggerNode`
: Webhook / event triggers. Two abstract methods: `setup(ctx)` (register
  listener) and `teardown(ctx)` (unregister).

:material-tag: `BasePollerNode`
: Interval triggers. One abstract method: `poll(ctx) -> list[Item]`. The
  `Poller` in `triggers/poller.py` calls this on a schedule.

### `nodes/registry.py` — `NodeRegistry`

Keyed by `(type, version)`. Multiple versions of the same node coexist so
existing workflows keep running on v1 after v2 ships.

| Method | Purpose |
| ------ | ------- |
| `register(node_cls, *, replace=False)` | Add a class. Idempotency-checked unless `replace=True`. |
| `get(type, version)` | Resolve to a class. Raises `KeyError` on miss. |
| `latest(type)` | Highest registered version of a node type. |
| `iter_specs()` | Iterate all `(type, version) → NodeSpec` pairs — used by the `/api/v1/node-types` endpoint. |
| `load_builtins()` | Walk `nodes/core/`, `nodes/ai/`, `nodes/integrations/` and register every `BaseNode`-subclass found. |

### `nodes/discovery.py` — finding plugins

Two channels:

1. **Built-ins** — `_iter_builtin_modules()` walks the `nodes/core/`, `ai/`,
   `integrations/` directories and imports each module. Modules register
   themselves via `@registry.register` decorator on the class.
2. **Entry points** — `_iter_entry_point_specs()` reads
   `[project.entry-points."weftlyflow.nodes"]` from installed packages.
   Third-party node packages register here.

### Anatomy of a built-in node

Every node directory follows the same pattern. Take
`nodes/core/http_request/`:

```
http_request/
├── __init__.py    # `from .node import HttpRequestNode`; registers on import.
└── node.py        # The class — spec + execute.
```

The class declares its `spec: ClassVar[NodeSpec]` with full property schema,
icon path, port definitions, and credential requirements. The `execute`
method reads parameters via `ctx.resolved_param(...)`, optionally fetches
credentials via `ctx.credentials(...)`, performs the action, and returns
`[[Item(json=response_body)]]`.

!!! tip "When you add a new node"
    Read [`contributing/node-plugins.md`](../../contributing/node-plugins.md).
    The short version: one folder under `nodes/integrations/<service>/`, one
    `node.py` with a `NodeSpec` and an `execute`, register on import.

## Where to next

- See it all run end-to-end: [Data-flow tracer](../data-flow.md).
- The HTTP boundary that calls the executor: [Server & DB](server-db.md).
- How async + scheduled triggers feed the executor:
  [Triggers, Worker, Webhooks](triggers-worker-webhooks.md).
