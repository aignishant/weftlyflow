"""Mapper functions — translate between SQLAlchemy entities and domain dataclasses.

Entity classes belong to the ORM layer and should never leak into callers
outside :mod:`weftlyflow.db`. Domain dataclasses belong to the pure-Python
model layer and know nothing about databases. Mappers are the bridge.

Rules of thumb:

* A mapper never calls the session (no lazy loads, no fresh queries). It
  takes a fully-populated entity + ancillary rows and returns a dataclass.
* A "to_entity" mapper returns **kwargs** rather than an entity instance —
  that way the caller (a repository) picks whether to ``add`` a new row or
  ``update`` an existing one.
"""

from __future__ import annotations

from weftlyflow.db.mappers.execution import (
    execution_to_data_payload,
    execution_to_domain,
    execution_to_entity_kwargs,
)
from weftlyflow.db.mappers.project import project_to_domain
from weftlyflow.db.mappers.user import user_to_domain
from weftlyflow.db.mappers.workflow import (
    workflow_to_domain,
    workflow_to_entity_kwargs,
)

__all__ = [
    "execution_to_data_payload",
    "execution_to_domain",
    "execution_to_entity_kwargs",
    "project_to_domain",
    "user_to_domain",
    "workflow_to_domain",
    "workflow_to_entity_kwargs",
]
