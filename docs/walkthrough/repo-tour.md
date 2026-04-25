# Repository Tour

> Top-level files and directories, annotated. Read this once; refer back when
> a tool starts complaining about a config file you don't recognise.

## Annotated tree

```
weftlyflow/
├── src/weftlyflow/         # ← Python package. Everything important lives here.
├── frontend/               # ← Vue 3 + Vue Flow editor (separate build).
├── tests/                  # ← unit / integration / load / security suites.
├── docs/                   # ← This documentation site (mkdocs-material).
├── scripts/                # ← Doc-generation scripts (gen_ref_pages, gen_node_pages).
├── docker/                 # ← API, worker, beat Dockerfiles.
├── deploy/helm/            # ← Helm chart for Kubernetes.
├── data/                   # ← Local SQLite + dev artifacts (gitignored).
│
├── pyproject.toml          # ← Package manifest, deps, ruff/mypy/pytest config.
├── alembic.ini             # ← Alembic migration config.
├── docker-compose.yml      # ← Default dev stack: api + worker + beat + redis + postgres.
├── docker-compose.override.yml  # ← Local overrides (gitignored typically).
├── Makefile                # ← Common dev tasks: lint, test, fmt, docs serve.
├── .pre-commit-config.yaml # ← Pre-commit hooks (ruff, black, mypy).
├── mkdocs.yml              # ← This site's nav + theme + plugins.
├── README.md               # ← User-facing readme.
├── RUN.md                  # ← Operator runbook: how to run, deploy, recover.
├── weftlyinfo.md           # ← Canonical design document (the spec).
├── LICENSE                 # ← Apache 2.0.
└── .env.example            # ← Reference env vars (every WEFTLYFLOW_* setting).
```

## Top-level files — what & why

<div class="grid cards" markdown>

-   :material-package-variant: &nbsp;**`pyproject.toml`**

    ---

    Single source of truth for: dependencies, optional extras (`ai`, `sso`,
    `aws-secrets`, `dev`, `docs`, `load`), the `weftlyflow` CLI script, ruff
    + black + isort + mypy + pytest config, and the `weftlyflow.nodes`
    entry-point group for third-party node packages.

-   :material-database-cog: &nbsp;**`alembic.ini`**

    ---

    Points Alembic at `src/weftlyflow/db/migrations`. Migrations are
    auto-applied at API boot in dev (`Base.metadata.create_all`) and run
    explicitly in prod (`alembic upgrade head`).

-   :material-docker: &nbsp;**`docker-compose.yml`**

    ---

    Reference dev stack: `api` (uvicorn), `worker` (celery), `beat`,
    `postgres`, `redis`. The `*.override.yml` lets you bind-mount source
    for live-reload without committing your changes.

-   :material-tools: &nbsp;**`Makefile`**

    ---

    `make install`, `make fmt`, `make lint`, `make test`, `make docs-serve`,
    `make migrate`. New contributors should be able to get green tests using
    only `make` targets.

-   :material-shield-check: &nbsp;**`.pre-commit-config.yaml`**

    ---

    Hooks: `ruff` (lint + format), `black`, `mypy`, plus the standard whitespace
    cleanup. CI re-runs these so a missed local hook fails the build.

-   :material-book-open-page-variant: &nbsp;**`weftlyinfo.md`**

    ---

    The canonical design spec. **Architectural decisions live here**, not in
    code comments. If a doc and the spec disagree, edit the spec, then mirror.

-   :material-file-cog: &nbsp;**`.env.example`**

    ---

    Every settable env var (`WEFTLYFLOW_*`) with a sane default. Mirrors the
    fields in `config/settings.py:WeftlyflowSettings`.

-   :material-play-box: &nbsp;**`RUN.md`**

    ---

    Operator runbook — how to run locally, deploy, recover from common
    failure modes. The README is the *what*; RUN.md is the *how*.

</div>

## `src/weftlyflow/` — the Python package

13 subpackages. Each one has its own walkthrough page in the [backend
section](backend/index.md). Quick map:

| Subpackage | Purpose | Walkthrough |
| ---------- | ------- | ----------- |
| `domain/` | Pure dataclasses — Workflow, Node, Execution, Item. No IO. | [Domain & engine](backend/domain-engine-nodes.md) |
| `engine/` | The execution loop — `WorkflowExecutor`, `WorkflowGraph`, `RunState`. | [Domain & engine](backend/domain-engine-nodes.md) |
| `nodes/` | Built-in nodes (`core/`, `ai/`, `integrations/`) + registry + discovery. | [Domain & engine](backend/domain-engine-nodes.md) |
| `expression/` | `{{ ... }}` template engine — tokenizer, sandbox, proxies. | [Auth, credentials, expression](backend/auth-credentials-expression.md) |
| `credentials/` | Credential types + Fernet cipher + external providers. | [Auth, credentials, expression](backend/auth-credentials-expression.md) |
| `auth/` | Passwords, JWT, scopes, SSO (OIDC + SAML). | [Auth, credentials, expression](backend/auth-credentials-expression.md) |
| `db/` | SQLAlchemy entities, repositories, mappers, Alembic migrations. | [Server & DB](backend/server-db.md) |
| `server/` | FastAPI app, routers, schemas, middleware, persistence hooks. | [Server & DB](backend/server-db.md) |
| `triggers/` | Scheduler, leader election, manager, poller. | [Triggers, worker, webhooks](backend/triggers-worker-webhooks.md) |
| `worker/` | Celery app, execution task, code-node sandbox runner. | [Triggers, worker, webhooks](backend/triggers-worker-webhooks.md) |
| `webhooks/` | Webhook registry, route parser, request handler. | [Triggers, worker, webhooks](backend/triggers-worker-webhooks.md) |
| `binary/` | Binary-data store abstractions (memory, filesystem). | [Cross-cutting](backend/cross-cutting.md) |
| `observability/` | Prometheus metrics, structlog config, OTel hooks. | [Cross-cutting](backend/cross-cutting.md) |
| `config/` | Pydantic settings + structlog config. | [Cross-cutting](backend/cross-cutting.md) |
| `utils/` | Tiny leaf-level helpers (redaction). | [Cross-cutting](backend/cross-cutting.md) |
| `cli.py` | `typer`-based CLI entry. | [Cross-cutting](backend/cross-cutting.md) |
| `__main__.py` | Allows `python -m weftlyflow ...`. | [Cross-cutting](backend/cross-cutting.md) |

## `frontend/` — the Vue 3 editor

Standalone build. Vite + Vue 3 + Pinia + Vue Router + Vue Flow + Tailwind +
TypeScript. Lives outside `src/` because:

- It builds independently (`npm run build` → `frontend/dist/`).
- The API server serves the built assets statically in production.
- Frontend-only dependencies stay out of the Python install.

See [Frontend walkthrough](frontend.md) for component-level coverage.

## `tests/` — four-tier test suite

```
tests/
├── conftest.py          # Shared fixtures (db, app, async loop, fakes).
├── unit/                # Pure unit tests, no external IO.
│   ├── auth/  binary/  credentials/  db/  engine/  expression/
│   ├── nodes/  triggers/  utils/  webhooks/  worker/
│   └── test_smoke.py    # Import-everything smoke test.
├── integration/         # Spin up a real test DB + app.
│   └── test_*.py        # Audit, auth, credentials, metrics, nodes, lifecycle.
├── load/                # Locust scenarios.
└── security/            # Defensive-behaviour probes (auth bypass, SSRF, etc.).
```

The pytest markers (`unit`, `integration`, `node`, `live`, `load`, `security`)
are declared in `pyproject.toml:[tool.pytest.ini_options]`. CI runs unit +
integration + security by default; `live` and `load` are opt-in.

## `docs/` — this site

```
docs/
├── index.md             # Home (hero + cards).
├── architecture.md      # Condensed architecture overview.
├── changelog.md
├── getting-started/     # install, first-workflow, concepts.
├── guide/               # User guides per feature.
├── contributing/        # Plugin authoring, security testing, IP compliance.
├── nodes/               # Auto-generated per-node reference (gen_node_pages.py).
├── design/              # ADR-style design notes.
├── stylesheets/extra.css # Custom theme (gradients, hero, cards).
├── images/
└── walkthrough/         # ← You are here.
```

## `scripts/`

| Script | Purpose |
| ------ | ------- |
| `gen_ref_pages.py` | Walks `src/weftlyflow/`, emits one mkdocstrings page per Python module under `docs/reference/`. Plugged into mkdocs via `mkdocs-gen-files`. |
| `gen_node_pages.py` | Generates per-node reference pages from each `BaseNode` subclass's `spec` and docstring. |

## `docker/` & `deploy/`

```
docker/
├── api.Dockerfile     # Python 3.12-slim, installs weftlyflow[ai,sso], runs uvicorn.
├── worker.Dockerfile  # Same base, runs celery worker.
└── beat.Dockerfile    # Same base, runs celery beat.

deploy/helm/           # Kubernetes Helm chart with values.yaml for HA setups.
```

The three Dockerfiles share most layers — they differ only in the `CMD`. In
practice, you build one image and override the entrypoint in your orchestrator.

!!! tip "Next"
    Continue with the [backend overview](backend/index.md) for the full
    module-level deep dive.
