# Cross-cutting Modules

> The small, leaf-level subpackages every layer touches. Each one is a focused
> utility — read it once and you can recognise the imports anywhere.

## `config/` — settings + logging

:material-folder: `src/weftlyflow/config/`

### Files

| File | Purpose |
| ---- | ------- |
| `settings.py` | :material-tag: `WeftlyflowSettings` — Pydantic `BaseSettings`. |
| `logging.py` | `configure_logging(level, fmt)` — structlog setup. |
| `__init__.py` | Exposes `get_settings()` (cached) + the settings class. |

### `config/settings.py` — `WeftlyflowSettings`

Single Pydantic model carrying every `WEFTLYFLOW_*` env var. Field groups:

| Group | Sample fields |
| ----- | ------------- |
| Core | `env`, `log_level`, `log_format`, `data_dir`. |
| HTTP | `cors_origin_list`, `request_timeout_ms`. |
| Database | `database_url`, `database_pool_size`, `database_pool_pre_ping`. |
| Redis / Celery | `redis_url`, `celery_broker_url`, `celery_result_backend`. |
| Worker | `worker_task_soft_time_limit_seconds`, `worker_task_time_limit_seconds`. |
| Encryption | `encryption_key`, `encryption_key_old_keys`. |
| Auth / JWT | `jwt_secret`, `jwt_access_ttl_seconds`, `jwt_refresh_ttl_seconds`, `argon2_*`. |
| MFA | `mfa_issuer`, `mfa_window_steps`. |
| SSO | `sso_oidc_*`, `sso_saml_*`, `sso_nonce_store_*`. |
| Webhooks | `webhook_idempotency_ttl_seconds`, `webhook_max_body_bytes`. |
| Triggers | `scheduler_timezone`, `leader_lock_ttl_seconds`. |
| Expression | `expression_timeout_ms`, `exposed_env_var_list`. |
| Sandbox | `sandbox_cpu_seconds`, `sandbox_memory_mb`, `sandbox_wall_seconds`. |
| External secrets | `vault_*`, `onepassword_*`, `aws_secrets_*`. |
| Binary store | `binary_store_backend`, `binary_inline_limit_bytes`. |

`get_settings()` is `@lru_cache(maxsize=1)`-decorated so the env is parsed
once per process. Tests override by clearing the cache.

### `config/logging.py` — `configure_logging`

Wires structlog with:

- ISO 8601 timestamps (UTC).
- `add_log_level`, `add_logger_name`, `StackInfoRenderer`.
- Format: `"json"` (production) or `"console"` (dev pretty-printed).
- Routes the stdlib `logging` root through structlog so library logs (uvicorn,
  SQLAlchemy, Celery) come out in the same format.

The `RequestContextMiddleware` binds `request_id` / `method` / `path` per
request via `structlog.contextvars`, so every log line during a request
carries those keys automatically.

---

## `observability/` — metrics + traces

:material-folder: `src/weftlyflow/observability/`

### Files

| File | Purpose |
| ---- | ------- |
| `metrics.py` | Prometheus `Counter` / `Histogram` instances. |
| `__init__.py` | Re-exports `metrics` namespace + OTel setup helpers. |

### `observability/metrics.py` — Prometheus collectors

| Metric | Type | Labels | Where incremented |
| ------ | ---- | ------ | ----------------- |
| `executions_total` | Counter | `status`, `mode` | `engine/executor.py:run`. |
| `execution_duration_seconds` | Histogram | — | `engine/executor.py:run`. |
| `node_duration_seconds` | Histogram | `node_type` | `engine/executor.py:run`. |
| `webhook_requests_total` | Counter | `path`, `status` | `webhooks/handler.py`. |
| `oauth_refresh_total` | Counter | `provider`, `result` | `worker/tasks.py:refresh_oauth_credential`. |
| `audit_events_pruned_total` | Counter | — | `worker/tasks.py:prune_audit_events`. |

Exposed at `GET /api/v1/metrics` via `server/routers/metrics.py` using
`prometheus_client.exposition.generate_latest`.

### OpenTelemetry

Auto-instruments FastAPI, SQLAlchemy, and httpx via the OTel auto-instrument
packages declared in `pyproject.toml`. Trace export is opt-in via
`OTEL_EXPORTER_OTLP_ENDPOINT` (no Weftlyflow-specific setting — we follow
upstream OTel env conventions).

---

## `binary/` — large blob store

:material-folder: `src/weftlyflow/binary/`

The runtime layer behind `BinaryRef`. Decouples item JSON from large
attachments (PDFs, images, CSV exports).

### Files

| File | Purpose |
| ---- | ------- |
| `store.py` | `BinaryStore` Protocol + `BinaryHandle` dataclass. |
| `memory.py` | `InMemoryBinaryStore` — dict-backed, ephemeral. Tests + dev. |
| `filesystem.py` | `FilesystemBinaryStore` — writes to `data_dir/binary/`. |
| `__init__.py` | Public surface. |

### `binary/store.py` — `BinaryStore` Protocol

```python
class BinaryStore(Protocol):
    async def put(self, data: bytes, *, mime_type: str, filename: str | None = None) -> BinaryRef: ...
    async def get(self, ref: BinaryRef) -> bytes: ...
    async def delete(self, ref: BinaryRef) -> None: ...
```

`BinaryRef.data_ref` carries the storage scheme so a single execution can
carry refs from multiple backends without ambiguity:

- `mem:<id>` — `InMemoryBinaryStore`.
- `fs:<relative-path>` — `FilesystemBinaryStore`.
- `s3://bucket/key` — future S3 backend (interface is in place).

The `binary_store_backend` setting picks the default backend the server
constructs at boot and parks on `app.state.binary_store`. Nodes access it
via `ctx.binary` in the `ExecutionContext`.

---

## `utils/` — leaf helpers

:material-folder: `src/weftlyflow/utils/`

### Files

| File | Purpose |
| ---- | ------- |
| `redaction.py` | :material-shield-lock: `safe_error_message(exc) -> str` + `redact(value, *, keys)`. |
| `__init__.py` | Public surface. |

### `utils/redaction.py` :material-shield-lock:

`safe_error_message(exc)` is the **single** function the engine and the HTTP
error handlers route exception messages through before the message touches
persistent storage or the response body.

It strips:

- DB DSNs (`postgresql://user:pass@host/db`) → `postgresql://[redacted]@host/db`.
- HTTP responses with bodies > N bytes → header-only summary.
- Common credential field names (`api_key`, `token`, `password`, `secret`,
  `authorization`) inside dict-y reprs.
- File paths under user home → `~/`.

`redact(value, *, keys)` walks a nested dict/list and replaces values whose
keys match `keys` (case-insensitive) with `"***"`.

---

## `cli.py` + `__main__.py` — command-line entry

### `cli.py` — `typer` app

| Command | Action |
| ------- | ------ |
| `weftlyflow version` | Print `__version__`. |
| `weftlyflow start --host --port --reload` | Wraps `uvicorn.run("weftlyflow.server.app:app", ...)`. |
| `weftlyflow worker` | Stub — directs operator to `celery -A weftlyflow.worker.app worker`. |
| `weftlyflow beat` | Stub — directs operator to `celery -A weftlyflow.worker.app beat`. |

### `__main__.py`

Two lines:

```python
from weftlyflow.cli import app
app()
```

Lets you do `python -m weftlyflow ...` without installing the entry point
(useful in CI containers that run pre-install smoke tests).

---

## How these modules are referenced everywhere

```mermaid
graph LR
    Settings[config.settings.WeftlyflowSettings] --> Cipher[CredentialCipher]
    Settings --> JWT[auth.jwt]
    Settings --> Sandbox[expression.sandbox]
    Settings --> Worker[worker.app]
    Settings --> Server[server.app]

    Logging[config.logging.configure_logging] --> Server
    Logging --> Worker
    Logging --> Beat[Celery Beat]

    Metrics[observability.metrics] --> Engine[engine.executor]
    Metrics --> Webhook[webhooks.handler]
    Metrics --> WorkerTasks[worker.tasks]

    Redaction[utils.redaction.safe_error_message] --> Engine
    Redaction --> Errors[server.errors]

    Binary[binary.store.BinaryStore] --> Engine
    Binary --> NodesIO[file IO nodes]
```

If you see a `from weftlyflow.config import get_settings` or
`from weftlyflow.observability import metrics` in any file, that's the link
back here.

## Cross-references

- The lifespan wiring that constructs all of these:
  [Server & DB](server-db.md).
- Where `safe_error_message` is critical (error path on node failure):
  [Domain → Engine → Nodes](domain-engine-nodes.md).
- The settings that gate optional features at boot:
  [Auth, Credentials, Expression](auth-credentials-expression.md).
