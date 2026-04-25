# Server & Database

> The HTTP boundary and the persistence layer it sits on top of. The server
> module is a thin presentation layer; all business logic delegates into the
> engine or a repository.

## `server/` — the FastAPI app

:material-folder: `src/weftlyflow/server/`

### Files

| File | Purpose |
| ---- | ------- |
| `app.py` | App factory + lifespan. Wires every dependency at boot. |
| `lifespan.py` | Async lifespan context manager helpers. |
| `middleware.py` | `RequestContextMiddleware` (request id, structlog binding, access log). |
| `errors.py` | `register_exception_handlers(app)` — domain → HTTP mapping. |
| `deps.py` | Reusable FastAPI `Depends(...)` factories (current user, session, registry). |
| `persistence_hooks.py` | `LifecycleHooks` implementation that writes execution rows + publishes Redis events. |
| `routers/` | One module per resource. |
| `schemas/` | Pydantic v2 request + response models. |
| `mappers/` | `domain ↔ schema` translators. |

### `server/app.py` — boot sequence

`create_app()` returns a fresh `FastAPI`. Used by both the production
`uvicorn weftlyflow.server.app:app` and the test harness (which calls
`create_app()` per test for isolation).

The interesting work is in `lifespan(app)`:

1. **Logging** — `configure_logging(level, fmt)` from `config/logging.py`.
2. **Engine + sessions** — `create_async_engine(database_url)` +
   `async_sessionmaker(...)`. Schema is created via
   `Base.metadata.create_all` in dev; prod uses `alembic upgrade head`.
3. **Node registry** — `NodeRegistry()` + `load_builtins()`.
4. **Bootstrap admin** — `auth.bootstrap.ensure_bootstrap_admin(...)` reads
   `WEFTLYFLOW_BOOTSTRAP_ADMIN_*` env and seeds the first user + project on
   empty installs.
5. **Credential stack** — `_build_credential_stack(...)` returns
   `(CredentialCipher, CredentialTypeRegistry, DatabaseCredentialResolver)`.
   Generates an *ephemeral* Fernet key with a warning if
   `WEFTLYFLOW_ENCRYPTION_KEY` is missing.
6. **Webhook + scheduler + queue** — `WebhookRegistry`, `InMemoryScheduler`,
   `InlineExecutionQueue`. (Production swaps `InlineExecutionQueue` for
   `CeleryExecutionQueue`.)
7. **Trigger manager** — `ActiveTriggerManager.warm_up()` reloads webhook +
   schedule rows from the DB into the in-memory registries on boot.
8. **SSO** — `_build_oidc_provider`, `_build_saml_provider`, `_build_nonce_store`
   (Memory or Redis backend).
9. **Secret providers** — `_build_secret_provider_registry(...)` always
   registers `EnvSecretProvider`; conditionally adds Vault, 1Password, AWS
   based on settings.
10. Everything is parked on `app.state` for routers to pick up via `Depends`.
11. **Shutdown** — scheduler shutdown, leader release, `engine.dispose()`.

### `server/middleware.py` — `RequestContextMiddleware`

Per-request:

- Generate or read `X-Request-ID`.
- Bind `request_id`, `method`, `path` into structlog context vars.
- Time the request, emit `http_request` log on completion with status code.

### `server/errors.py` — exception → HTTP mapping

| Domain exception | HTTP code |
| ---------------- | --------- |
| `WorkflowValidationError` (and subclasses) | `422` |
| `NodeExecutionError` | `500` (with safe message) |
| `CredentialNotFoundError` | `404` |
| `CredentialDecryptError` | `500` (logs detail; redacts response) |
| `AuthenticationError` | `401` |
| `AuthorizationError` | `403` |
| `RateLimitedError` | `429` |
| `WeftlyflowError` (catch-all) | `500` |

Every handler routes through `utils.redaction.safe_error_message` so secrets
never reach the response body.

### `server/routers/` — every endpoint

| Router | Mount | Endpoints (high level) |
| ------ | ----- | ---------------------- |
| `health.py` | `/api/v1/health` | `GET /` (live), `GET /ready` (DB + Redis ping). |
| `metrics.py` | `/api/v1/metrics` | Prometheus exposition. |
| `auth.py` | `/api/v1/auth` | `POST /login`, `POST /logout`, `POST /refresh`, `POST /mfa/setup`, `POST /mfa/verify`, `GET /me`. |
| `workflows.py` | `/api/v1/workflows` | Full CRUD + `POST /{id}/activate`, `/deactivate`, `/run`, `/duplicate`, `GET /{id}/executions`. |
| `executions.py` | `/api/v1/executions` | `GET /`, `GET /{id}`, `POST /{id}/retry`, `POST /{id}/cancel`, `WS /{id}/stream`. |
| `node_types.py` | `/api/v1/node-types` | `GET /` lists all registered nodes (specs only). |
| `credentials.py` | `/api/v1/credentials` + `/credential-types` | CRUD on credentials + list available types. |
| `oauth2.py` | `/api/v1/oauth2` | OAuth2 dance for credential types that need it (`/authorize`, `/callback`). |
| `sso.py` | `/api/v1/sso/oidc/...` + `/sso/saml/...` | OIDC + SAML SP endpoints (`/login`, `/callback`, `/metadata`, `/acs`). |
| `webhooks_ingress.py` | `/webhook/...` | The HTTP front-door for webhook trigger nodes — *no* `/api/v1` prefix. |

### `server/schemas/` — Pydantic v2 DTOs

| File | Models |
| ---- | ------ |
| `auth.py` | `LoginRequest`, `LoginResponse`, `TokenPair`, `MeResponse`, MFA payloads. |
| `workflows.py` | `WorkflowRead`, `WorkflowWrite`, `NodeRead/Write`, `ConnectionRead/Write`, `WorkflowSettings*`. |
| `executions.py` | `ExecutionRead`, `NodeRunRead`, `ItemRead`, `ExecutionListRequest`. |
| `credentials.py` | `CredentialWrite`, `CredentialRead` (encrypted body redacted), `CredentialTypeRead`. |
| `node_types.py` | `NodeTypeRead`, `PortRead`, `PropertySchemaRead`. |
| `common.py` | `Pagination`, `ProblemDetails`, `IdResponse`. |

Schemas never carry secrets. Read paths always omit decrypted credential
bodies; write paths accept a single `data: dict[str, Any]` that the resolver
encrypts before persistence.

### `server/mappers/` — translating types

Each mapper exposes `from_domain(domain_obj) -> schema` and
`to_domain(schema) -> domain_obj`. The same pattern lives in
`db/mappers/` for domain ↔ entity. **Two-step pipeline**:

```
schema  ──to_domain──▶  domain  ──to_entity──▶  entity (DB row)
schema  ◀─from_domain── domain  ◀─from_entity── entity
```

Keeping mappers separate lets us evolve the wire format and the DB schema
independently of the conceptual model.

### `server/persistence_hooks.py` — engine ↔ DB seam

Implements `LifecycleHooks`:

| Method | Side effect |
| ------ | ----------- |
| `on_execution_start(ctx)` | Insert `ExecutionEntity` row, status `running`. Publish `exec:start`. |
| `on_node_start(ctx, node)` | No-op (UI gets node start from `on_node_end` payload). |
| `on_node_end(ctx, node, run_data)` | Update execution row's `run_data` JSON column; publish `exec:node` event. |
| `on_node_error(ctx, node, error)` | Log; the actual error row is written on `on_execution_end`. |
| `on_execution_end(ctx, execution)` | Final UPDATE: status, `finished_at`, full `run_data`. Publish `exec:end`. |
| `on_node_progress(ctx, node, payload)` | Publish `exec:progress` (LLM token streaming). |

Publishes go to Redis channel `exec-events:{execution_id}`. The
`/api/v1/executions/{id}/stream` WebSocket consumes them.

### `server/deps.py` — DI building blocks

| Dependency | Returns |
| ---------- | ------- |
| `get_session(request)` | `AsyncSession` from `app.state.session_factory`. |
| `get_node_registry(request)` | `NodeRegistry` from `app.state`. |
| `get_credential_resolver(request)` | `DatabaseCredentialResolver`. |
| `get_current_user(authorization, session)` | Decodes JWT, fetches `UserEntity`. Raises `AuthenticationError` on bad token. |
| `require_scope(scope)` | Factory: returns a dep that asserts the user has the named scope. |
| `get_trigger_manager(request)` | The `ActiveTriggerManager`. |

All side effects on `app.state` set up in `lifespan` are read here.

---

## `db/` — persistence

:material-folder: `src/weftlyflow/db/`

### Top-level files

| File | Purpose |
| ---- | ------- |
| `base.py` | `class Base(DeclarativeBase)` — SQLAlchemy 2.x typed declarative base. |
| `engine.py` | `get_engine`, `get_async_engine` (cached), `session_scope` context manager. |
| `execution_storage.py` | Pluggable storage backend for *large* execution payloads (db / fs / s3). |
| `__init__.py` | Public surface (just `Base` + the engine helpers). |

### `db/entities/` — table classes

One module per table. All inherit `Base` and use `Mapped[...]` /
`mapped_column(...)` (no legacy `Column`).

| Entity | Table | Notes |
| ------ | ----- | ----- |
| `UserEntity` | `users` | Argon2 password hash, MFA secret (encrypted), scopes. |
| `RefreshTokenEntity` | `refresh_tokens` | JWT refresh-token registry (revocable). |
| `ProjectEntity` | `projects` | Multi-tenant boundary; every other table has `project_id`. |
| `WorkflowEntity` | `workflows` | JSONB columns for nodes/connections/settings. |
| `ExecutionEntity` | `executions` | Status, mode, started/finished, `run_data` JSONB or pointer. |
| `ExecutionDataEntity` | `execution_data` | Off-row payload for large `run_data` (db/fs/s3 stored here). |
| `CredentialEntity` | `credentials` | Encrypted body (Fernet); type id + name. |
| `WebhookEntity` | `webhooks` | One row per active webhook trigger; static path + node id. |
| `TriggerScheduleEntity` | `trigger_schedules` | One row per active cron / interval trigger. |
| `OAuthStateEntity` | `oauth_states` | Short-lived OAuth state tokens. |
| `AuditEventEntity` | `audit_events` | Append-only audit log; pruned by `prune_audit_events` Beat task. |
| `mixins.py` | `TimestampMixin`, `ProjectScopedMixin`, `IdMixin` (ULID PK helper). |

### `db/repositories/` — query helpers

One repository per entity. Repositories own the SQLAlchemy queries; routers
own the HTTP plumbing; the engine owns the business logic. Three layers,
clean separation.

Common method shape:

```python
class WorkflowRepository:
    def __init__(self, session: AsyncSession): ...
    async def get(self, id: str, *, project_id: str) -> WorkflowEntity | None: ...
    async def list(self, *, project_id: str, ...) -> list[WorkflowEntity]: ...
    async def create(self, entity: WorkflowEntity) -> WorkflowEntity: ...
    async def update(self, entity: WorkflowEntity) -> WorkflowEntity: ...
    async def delete(self, id: str, *, project_id: str) -> None: ...
```

Every read takes `project_id` for multi-tenancy enforcement at the SQL layer
— never relying on application-level filtering alone.

### `db/mappers/` — entity ↔ domain

Same shape as `server/mappers/` but on the other side. `from_entity(...)`
and `to_entity(...)` per entity. Keeps both ends of the storage round-trip
explicit and testable.

### `db/migrations/` — Alembic

```
db/migrations/
├── env.py                # Alembic environment, async-aware.
├── script.py.mako
└── versions/
    ├── 0001_initial_schema.py        # Users, projects, workflows, executions, credentials.
    ├── 0002_phase3_triggers.py       # webhooks, trigger_schedules.
    ├── 0003_phase4_credentials.py    # Credential body encryption columns.
    ├── 0004_phase8_audit_events.py   # audit_events table + indices.
    └── 0005_phase9_execution_storage.py # execution_data off-row payloads.
```

Migrations are numbered and linear. New migration:
`alembic revision --autogenerate -m "description"`. Always review autogenerate
output — it occasionally invents drops it shouldn't.

### `db/execution_storage.py` — large payload offload

Execution `run_data` blobs can be hundreds of MB on data-pipeline workloads.
This module routes the storage:

| Backend | When | Storage |
| ------- | ---- | ------- |
| `"db"` (default) | Small payloads (`< binary_inline_limit_bytes`) | JSONB column on `executions`. |
| `"fs"` | Local-disk operator preference | `data_dir/execution_data/<id>.json.gz`. |
| `"s3"` | Production at scale | `s3://bucket/prefix/<id>.json.gz`. |

The choice is per-execution; rows in `execution_data` carry the storage tag.

## Cross-references

- The hooks the executor fires into the persistence layer:
  [Domain → Engine → Nodes](domain-engine-nodes.md).
- How webhooks reach `routers/webhooks_ingress.py`:
  [Triggers, Worker, Webhooks](triggers-worker-webhooks.md).
- Auth + JWT flow that protects every router:
  [Auth, Credentials, Expression](auth-credentials-expression.md).
- An end-to-end trace touching every layer: [Data flow](../data-flow.md).
