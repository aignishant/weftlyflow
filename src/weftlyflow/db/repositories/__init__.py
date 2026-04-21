"""Repositories — typed query wrappers over entity classes.

A repository is a plain class (no DI container required) that takes a
``Session`` or ``AsyncSession`` in its constructor and exposes high-level
methods returning domain objects (or dataclasses), not ORM instances.

This pattern keeps SQL/ORM concerns out of the execution engine and the server
routers. Callers that need fine-grained control over a query can still drop to
``session.execute(select(Entity)...)`` directly — repositories are a
convenience, not a restriction.

Implementation plan (Phase 2):
    - workflow_repo.py, execution_repo.py, credential_repo.py
    - user_repo.py, webhook_repo.py, project_repo.py
"""

from __future__ import annotations
