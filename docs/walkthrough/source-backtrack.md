# Source-Code Backtracking

> "I see this symbol — where does it live?" A reverse index of every
> cross-cutting type, registry, error, and constant in the codebase, with
> file:line refs.

## How to use this page

1. Search-in-page (⌘F / Ctrl-F) for the symbol you saw in code.
2. The right column tells you which file owns it.
3. Click through to the [API reference](../reference/index.md) for the full
   signature.

If you're not sure of the symbol name, scan the [Glossary](#glossary) at the
bottom — it's keyed by concept rather than name.

---

## Domain types

| Symbol | Module | Usually constructed by |
| ------ | ------ | ---------------------- |
| `Workflow` | `weftlyflow.domain.workflow` | `db/mappers/workflow.py:from_entity`, `server/mappers/workflow.py:to_domain` |
| `Node` | `weftlyflow.domain.workflow` | mapper + workflow loader |
| `Connection` | `weftlyflow.domain.workflow` | same |
| `Port` | `weftlyflow.domain.workflow` | declared inside `NodeSpec` |
| `RetryPolicy` | `weftlyflow.domain.workflow` | optional on `Node` |
| `WorkflowSettings` | `weftlyflow.domain.workflow` | per-workflow settings DTO |
| `Item` | `weftlyflow.domain.execution` | by node `execute()` results |
| `BinaryRef` | `weftlyflow.domain.execution` | `binary.store.BinaryStore.put` |
| `NodeError` | `weftlyflow.domain.execution` | `engine.executor._handle_node_exception` |
| `NodeRunData` | `weftlyflow.domain.execution` | `engine.executor._run_one` |
| `RunData` | `weftlyflow.domain.execution` | `engine.runtime.RunState.run_data` |
| `Execution` | `weftlyflow.domain.execution` | `engine.runtime.RunState.build_execution` |
| `PairedItem` | `weftlyflow.domain.execution` | nodes that branch / merge |
| `NodeSpec` | `weftlyflow.domain.node_spec` | `ClassVar` on every `BaseNode` subclass |
| `PropertySchema` | `weftlyflow.domain.node_spec` | inside each `NodeSpec.properties` |
| `NodeCategory` | `weftlyflow.domain.node_spec` | enum: `CORE`, `AI`, `INTEGRATION`, `TRIGGER`, `UTILITY` |
| `Credential` | `weftlyflow.domain.credential` | `db.mappers` from `CredentialEntity` |

## Engine types

| Symbol | Module | Notes |
| ------ | ------ | ----- |
| `WorkflowExecutor` | `weftlyflow.engine.executor` | one per process, reused across runs |
| `WorkflowGraph` | `weftlyflow.engine.graph` | built per run from `Workflow` |
| `OutgoingEdge` / `IncomingEdge` | `weftlyflow.engine.graph` | indexed neighbour lookup |
| `RunState` | `weftlyflow.engine.runtime` | per-run mutable state |
| `ExecutionContext` | `weftlyflow.engine.context` | passed to every `node.execute(ctx, items)` |
| `LifecycleHooks` (Protocol) | `weftlyflow.engine.hooks` | implementations: `NullHooks`, `PersistenceHooks` |
| `NullHooks` | `weftlyflow.engine.hooks` | default no-op |
| `SubWorkflowRunner` | `weftlyflow.engine.subworkflow` | nested workflows |
| `STATUS_SUCCESS` / `_ERROR` / `_DISABLED` | `weftlyflow.engine.constants` | string literals |
| `NodeTypeNotFoundError` | `weftlyflow.engine.errors` | raised by `_resolve_node` |

## Node plugin types

| Symbol | Module | Notes |
| ------ | ------ | ----- |
| `BaseNode` | `weftlyflow.nodes.base` | action node ABC |
| `BaseTriggerNode` | `weftlyflow.nodes.base` | webhook / event trigger ABC |
| `BasePollerNode` | `weftlyflow.nodes.base` | interval poller ABC |
| `NodeRegistry` | `weftlyflow.nodes.registry` | keyed by `(type, version)` |
| `NodeRegistryError` | `weftlyflow.nodes.registry` | duplicate / missing |
| Built-in node classes | `weftlyflow.nodes.core.<name>.node` | one folder per node |
| Integration nodes | `weftlyflow.nodes.integrations.<service>.node` | one folder per service |
| AI nodes | `weftlyflow.nodes.ai.<name>` | LLM / agents / vector / memory |

## Expression types

| Symbol | Module | Notes |
| ------ | ------ | ----- |
| `tokenize` / `LiteralChunk` / `ExpressionChunk` | `weftlyflow.expression.tokenizer` | pure splitter |
| `contains_expression` / `is_single_expression` | `weftlyflow.expression.tokenizer` | predicates |
| `compile_restricted_eval` (re-exported) | `weftlyflow.expression.sandbox` | RestrictedPython wrapper |
| `resolve` / `resolve_tree` / `clear_cache` | `weftlyflow.expression.resolver` | the public API |
| `build_proxies` / `filter_env` | `weftlyflow.expression.proxies` | proxy assembly |
| `InputProxy` / `WeftlyflowDateTime` | `weftlyflow.expression.proxies` | the `$input` / `$now` objects |
| `ExpressionError` (+ `Syntax`, `Eval`, `Security`, `Timeout`) | `weftlyflow.expression.errors` | exception family |

## Credential types

| Symbol | Module | Notes |
| ------ | ------ | ----- |
| `CredentialCipher` | `weftlyflow.credentials.cipher` | Fernet + key rotation |
| `generate_key` | `weftlyflow.credentials.cipher` | new Fernet key |
| `CredentialTypeRegistry` | `weftlyflow.credentials.registry` | keyed by `name` |
| `BaseCredentialType` | `weftlyflow.credentials.base` | per-type ABC |
| `CredentialField` | `weftlyflow.credentials.base` | one form field |
| `CredentialResolver` (Protocol) | `weftlyflow.credentials.resolver` | reads + decrypts |
| `DatabaseCredentialResolver` | `weftlyflow.credentials.resolver` | the production impl |
| `SecretProvider` (Protocol) | `weftlyflow.credentials.external.base` | external secret stores |
| `SecretProviderRegistry` | `weftlyflow.credentials.external.registry` | provider lookup chain |
| `EnvSecretProvider` | `weftlyflow.credentials.external.env_provider` | `${env:VAR}` |
| `VaultSecretProvider` | `weftlyflow.credentials.external.vault_provider` | HashiCorp Vault |
| `OnePasswordSecretProvider` | `weftlyflow.credentials.external.onepassword_provider` | 1Password Connect |
| `AWSSecretsManagerProvider` | `weftlyflow.credentials.external.aws_provider` | boto3 (lazy import) |
| 80 credential type classes | `weftlyflow.credentials.types.<service>` | one module per service |

## Auth types

| Symbol | Module | Notes |
| ------ | ------ | ----- |
| `hash_password` / `verify_password` / `needs_rehash` | `weftlyflow.auth.passwords` | Argon2id |
| `issue_access_token` / `decode_access_token` | `weftlyflow.auth.jwt` | HS256 |
| `issue_refresh_token` / `rotate_refresh_token` | `weftlyflow.auth.jwt` | persisted in `refresh_tokens` |
| `require_scope(name)` | `weftlyflow.server.deps` | dep factory |
| `ensure_bootstrap_admin` | `weftlyflow.auth.bootstrap` | first-boot seed |
| `OIDCConfig` / `OIDCProvider` | `weftlyflow.auth.sso.oidc` | enabled per settings |
| `SAMLConfig` / `SAMLProvider` | `weftlyflow.auth.sso.saml` | needs `python3-saml` extra |
| `NonceStore` (Protocol) | `weftlyflow.auth.sso.nonce_store` | replay protection |
| `InMemoryNonceStore` / `RedisNonceStore` | `weftlyflow.auth.sso.nonce_store` | dev / prod backends |

## Database types

| Symbol | Module | Notes |
| ------ | ------ | ----- |
| `Base` | `weftlyflow.db.base` | `DeclarativeBase` |
| `get_engine` / `get_async_engine` / `session_scope` | `weftlyflow.db.engine` | cached |
| `UserEntity` | `weftlyflow.db.entities.user` | `users` table |
| `RefreshTokenEntity` | `weftlyflow.db.entities.refresh_token` | `refresh_tokens` |
| `ProjectEntity` | `weftlyflow.db.entities.project` | tenant boundary |
| `WorkflowEntity` | `weftlyflow.db.entities.workflow` | JSONB nodes/connections |
| `ExecutionEntity` | `weftlyflow.db.entities.execution` | per-run row |
| `ExecutionDataEntity` | `weftlyflow.db.entities.execution_data` | off-row payload |
| `CredentialEntity` | `weftlyflow.db.entities.credential` | encrypted body |
| `WebhookEntity` | `weftlyflow.db.entities.webhook` | one per active webhook |
| `TriggerScheduleEntity` | `weftlyflow.db.entities.trigger_schedule` | cron / interval |
| `OAuthStateEntity` | `weftlyflow.db.entities.oauth_state` | OAuth dance state |
| `AuditEventEntity` | `weftlyflow.db.entities.audit_event` | append-only |
| `TimestampMixin` / `ProjectScopedMixin` / `IdMixin` | `weftlyflow.db.entities.mixins` | shared columns |
| `<Resource>Repository` (12) | `weftlyflow.db.repositories.<resource>_repo` | per-entity query helpers |
| `<Resource>Mapper` | `weftlyflow.db.mappers.<resource>` | entity ↔ domain |

## Server types

| Symbol | Module | Notes |
| ------ | ------ | ----- |
| `app` (FastAPI instance) | `weftlyflow.server.app` | `create_app()` factory output |
| `lifespan` | `weftlyflow.server.app` | async context manager |
| `RequestContextMiddleware` | `weftlyflow.server.middleware` | request-id + structlog binding |
| `register_exception_handlers` | `weftlyflow.server.errors` | domain → HTTP |
| `PersistenceHooks` | `weftlyflow.server.persistence_hooks` | engine ↔ DB seam |
| `get_session` / `get_node_registry` / `get_credential_resolver` | `weftlyflow.server.deps` | DI helpers |
| `get_current_user` / `require_scope` | `weftlyflow.server.deps` | auth deps |
| Routers (`auth`, `workflows`, `executions`, `node_types`, `credentials`, `oauth2`, `sso`, `webhooks_ingress`, `health`, `metrics`) | `weftlyflow.server.routers.<name>` | one module per resource |
| Schemas | `weftlyflow.server.schemas.<name>` | request + response Pydantic v2 |
| Mappers (server-side) | `weftlyflow.server.mappers.<name>` | schema ↔ domain |

## Trigger / worker / webhook types

| Symbol | Module | Notes |
| ------ | ------ | ----- |
| `ActiveTriggerManager` | `weftlyflow.triggers.manager` | activate / deactivate / warm_up |
| `Scheduler` (Protocol) | `weftlyflow.triggers.scheduler` | `InMemoryScheduler` (APScheduler) |
| `ScheduleSpec` | `weftlyflow.triggers.scheduler` | cron / interval |
| `LeaderLock` (Protocol) | `weftlyflow.triggers.leader` | `InMemoryLeaderLock` / `RedisLeaderLock` |
| `Poller` | `weftlyflow.triggers.poller` | interval-driven `BasePollerNode` host |
| `celery_app` | `weftlyflow.worker.app` | the Celery instance |
| `execute_workflow` | `weftlyflow.worker.tasks` | the executions queue task |
| `refresh_oauth_credential` | `weftlyflow.worker.tasks` | OAuth token renew |
| `prune_audit_events` | `weftlyflow.worker.tasks` | daily Beat task |
| `run_execution` | `weftlyflow.worker.execution` | the async body of `execute_workflow` |
| `ExecutionQueue` (Protocol) | `weftlyflow.worker.queue` | `InlineExecutionQueue` / `CeleryExecutionQueue` |
| `dedup_check` | `weftlyflow.worker.idempotency` | webhook-replay protection |
| `WebhookRegistry` | `weftlyflow.webhooks.registry` | path → entry |
| `WebhookHandler` | `weftlyflow.webhooks.handler` | request → enqueue |
| `WebhookRequestParser` | `weftlyflow.webhooks.parser` | body / query / headers |
| `WebhookEntry` / `WebhookRequest` / `WebhookResponse` | `weftlyflow.webhooks.types` | dataclasses |
| `static_path` | `weftlyflow.webhooks.paths` | webhook URL composer |

## Cross-cutting types

| Symbol | Module | Notes |
| ------ | ------ | ----- |
| `WeftlyflowSettings` | `weftlyflow.config.settings` | Pydantic `BaseSettings` |
| `get_settings` | `weftlyflow.config` | LRU-cached |
| `configure_logging` | `weftlyflow.config.logging` | structlog setup |
| `metrics.executions_total` etc. | `weftlyflow.observability.metrics` | Prometheus collectors |
| `safe_error_message` | `weftlyflow.utils.redaction` | secret redaction (use everywhere errors persist) |
| `redact` | `weftlyflow.utils.redaction` | dict redactor |
| `BinaryStore` (Protocol) | `weftlyflow.binary.store` | put / get / delete |
| `InMemoryBinaryStore` / `FilesystemBinaryStore` | `weftlyflow.binary.<backend>` | concrete impls |

## Error hierarchy at a glance

```
WeftlyflowError                              (domain.errors)
├── WorkflowValidationError
│   ├── CycleDetectedError
│   └── InvalidConnectionError
└── NodeExecutionError

ExpressionError                              (expression.errors)
├── ExpressionSyntaxError
├── ExpressionEvalError
├── ExpressionSecurityError
└── ExpressionTimeoutError

NodeRegistryError                            (nodes.registry)
NodeTypeNotFoundError                        (engine.errors)

AuthenticationError / AuthorizationError     (server-level, in errors.py)
RateLimitedError                             (server-level)

CredentialNotFoundError / CredentialDecryptError (credentials.* — see resolver/cipher)
```

Every persisted error message routes through `safe_error_message`. If you
add a new error path, do the same.

## Glossary

Concept-keyed lookup for when you don't know the symbol name yet.

| You're thinking about… | Look at |
| ---------------------- | ------- |
| The whole graph being run | `Workflow` (`domain.workflow`) |
| One step in a workflow | `Node` (`domain.workflow`) |
| An edge between steps | `Connection` (`domain.workflow`) |
| One record flowing through nodes | `Item` (`domain.execution`) |
| A node's manifest (display name, properties, ports) | `NodeSpec` (`domain.node_spec`) |
| One run of one node | `NodeRunData` (`domain.execution`) |
| One full run | `Execution` (`domain.execution`) |
| The main loop | `WorkflowExecutor` (`engine.executor`) |
| What a node sees | `ExecutionContext` (`engine.context`) |
| Side-effect seam (logging, persistence) | `LifecycleHooks` (`engine.hooks`) |
| `{{ ... }}` evaluation | `expression.resolver.resolve_tree` |
| Encrypted secret storage | `CredentialCipher` (`credentials.cipher`) |
| Decrypt + external-secret substitution | `DatabaseCredentialResolver` (`credentials.resolver`) |
| Login + JWT | `auth.passwords` + `auth.jwt` |
| Multi-tenant boundary | `ProjectEntity` + `project_id` everywhere |
| Webhook URL routing | `WebhookRegistry` (`webhooks.registry`) |
| Cron / interval triggers | `Scheduler` + `ActiveTriggerManager` |
| The Celery side | `worker.app` + `worker.tasks` |
| Code-node sandbox | `worker.sandbox_runner` + `sandbox_child` |
| Settings | `config.settings.WeftlyflowSettings` |
| Logging | `config.logging.configure_logging` |
| Prometheus metrics | `observability.metrics` |
| Redaction (always use this for error messages) | `utils.redaction.safe_error_message` |
| Binary attachments | `binary.store.BinaryStore` + `domain.execution.BinaryRef` |
| Frontend axios client | `frontend/src/api/client.ts` |
| Frontend route definitions | `frontend/src/router/index.ts` |
| Frontend state | `frontend/src/stores/*.ts` |
| The editor canvas | `frontend/src/views/Editor.vue` + `components/canvas/WorkflowNodeCard.vue` |

!!! tip "Couldn't find what you wanted?"
    The mkdocstrings-driven [API reference](../reference/index.md) covers every
    symbol with full signatures and source links. This page is intentionally
    curated — if a missing symbol is *commonly searched for*, please open a
    PR adding it here.
