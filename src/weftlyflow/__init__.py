"""Weftlyflow — self-hosted workflow automation platform.

This is the top-level package. It deliberately keeps the public surface small:
anything the API/worker/cli needs should be imported from one of the submodules
(`weftlyflow.domain`, `weftlyflow.engine`, `weftlyflow.server`, `weftlyflow.worker`).

Subpackages:
    config: Pydantic settings + structlog configuration (side-effect free until called).
    domain: Pure, framework-free dataclasses — the conceptual model.
    db: SQLAlchemy entities, repositories, Alembic migrations.
    engine: Workflow execution engine (the main loop, graph, hooks).
    expression: `{{ ... }}` tokenizer, sandbox, proxies (`$json`, `$now`, ...).
    nodes: Built-in node plugins and the registry.
    credentials: Credential plugin system + Fernet encryption.
    server: FastAPI app, routers, schemas, middleware.
    webhooks: Webhook registry, routing, request handler.
    triggers: Cron, poll, and event-based trigger management.
    worker: Celery app + tasks.
    auth: Passwords, JWT, RBAC, MFA.
    observability: structlog, Prometheus, OpenTelemetry.
    utils: Small, leaf-level helpers.

The canonical design document is `/IMPLEMENTATION_BIBLE.md` at the repo root.
"""

from __future__ import annotations

__version__ = "0.1.0a0"
__all__ = ["__version__"]
