# Changelog

All notable user-facing changes. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added — Phase 8b (2026-04-23)

**Expression sandbox & Code node hardening**
- Subprocess-based sandbox runner for the `weftlyflow.code` node with `RLIMIT_CPU`,
  `RLIMIT_AS`, and wall-clock ceilings; parent-side `subprocess.run(timeout=...)`
  kill switch. New settings: `enable_code_node`, `code_node_cpu_seconds`,
  `code_node_memory_bytes`, `code_node_wall_clock_seconds`.
- Expression engine gains a per-evaluation `expression_timeout_seconds` budget
  and a `$env` proxy gated by the `exposed_env_vars` allowlist — expressions
  can no longer see the full process environment.
- Sandbox-bypass corpus and Hypothesis-driven fuzz suite added under
  `tests/unit/expression/`.

**Error redaction (`weftlyflow.utils.redaction`)**
- Central helper that scrubs secrets, tokens, and known-sensitive keys from
  tracebacks and structured log events before they reach stderr or the audit
  log.

**Observability**
- Prometheus `/metrics` endpoint, gated by `metrics_enabled` (on by default).
  Emits request, execution, queue, and sandbox counters/histograms.
- New `weftlyflow.observability.metrics` module and `server.routers.metrics`.

**External secret providers**
- `SecretProvider` Protocol + `SecretProviderRegistry` under
  `weftlyflow.credentials.external`. Credential values can now reference
  `<scheme>:<path>[#<field>]` and the resolver dereferences them at workflow-run
  time.
- **HashiCorp Vault** (`vault:<mount>/<path>#<field>`) — KV v2, token auth,
  optional namespace. Settings: `vault_enabled`, `vault_address`,
  `vault_token`, `vault_namespace`, `vault_timeout_seconds`.
- **1Password Connect** (`op:vaults/<uuid>/items/<uuid>#<field-label>`) —
  bearer-token REST. Settings: `onepassword_enabled`,
  `onepassword_connect_url`, `onepassword_connect_token`,
  `onepassword_timeout_seconds`.
- **AWS Secrets Manager** (`aws:<secret-id>[#<field>]`) — boto3 wrapped in
  `asyncio.to_thread`; shipped behind the `aws-secrets` optional extra so the
  default install stays boto3-free. Settings: `aws_secrets_enabled`,
  `aws_secrets_region`.
- Always-on `EnvSecretProvider` (`env:VARNAME`) registered unconditionally.

**Authentication**
- **OIDC SSO** adapter (`weftlyflow.auth.sso.oidc`) with `/api/v1/auth/sso/oidc/login`
  and `/callback` routes, authlib-backed discovery, auto-provisioning of local
  users + personal projects. Settings: `sso_oidc_enabled`,
  `sso_oidc_issuer_url`, `sso_oidc_client_id`, `sso_oidc_client_secret`,
  `sso_oidc_redirect_uri`, `sso_oidc_scopes`, `sso_oidc_auto_provision`,
  `sso_post_login_redirect`.

**Audit log**
- `audit_events` table + repository, Alembic migration `0004_phase8_audit_events`,
  Celery Beat retention sweep. Setting: `audit_retention_days` (default 90).

**Deployment**
- Helm chart under `deploy/helm/weftlyflow/` — API / worker / beat deployments,
  migration job, ConfigMap/Secret, Service, Ingress, NetworkPolicy, PDB, HPA,
  ServiceAccount. Bitnami Postgres + Redis as conditional dependencies.

### Added — Phases 0–8a (historical)

- **Phase 0** — repo bootstrap, `pyproject.toml`, Makefile, Dockerfiles,
  docker-compose, pre-commit, mkdocs-material, smoke CI gate.
- **Phase 1** — domain dataclasses (`Workflow`, `Node`, `Connection`,
  `Execution`, `Item`, `RunData`, `NodeSpec`), FastAPI + Celery skeletons.
- **Phase 2** — SQLAlchemy 2 entities, Alembic, repositories, auth (argon2 +
  JWT + refresh tokens + TOTP), RBAC, workflows/executions/credentials
  routers, first-boot admin bootstrap.
- **Phase 3** — execution engine, `ExecutionContext`, node registry,
  expression engine (`{{ ... }}` → RestrictedPython), credential plugin
  system + Fernet encryption with key rotation.
- **Phase 4** — webhook ingress, cron/poll/event triggers, APScheduler,
  in-memory leader lock, `ActiveTriggerManager`.
- **Phase 5** — core nodes (`http_request`, `set`, `if`, `switch`, `merge`,
  `split_in_batches`, `wait`, `function`, `function_item`, `code`,
  `execute_workflow`, `no_op`, `webhook`, `cron`, `manual`).
- **Phase 6** *(in progress)* — integration nodes; ~90 shipped to date
  (HTTP/REST, OAuth, signing, messaging, storage, transport variants).
- **Phase 8a** — Celery worker hardening, execution queue, inline-queue dev
  mode, structured logging via structlog.

### Known gaps

- **SAML SSO** adapter not yet wired — `python3-saml` is available as an
  optional extra (`weftlyflow[sso]`) but the provider class and
  `/api/v1/auth/sso/saml/*` routes are pending.
- **Phase 7 AI nodes** — LangChain / OpenAI / Anthropic / vector-store nodes
  have not started; the `ai` optional extra is reserved for that tranche.
- **Phase 6 integrations** — ongoing; roughly one-third of the planned node
  catalogue is live.
