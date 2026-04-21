"""DTO ↔ domain mappers used by the routers.

Distinct from :mod:`weftlyflow.db.mappers` — these live at the HTTP boundary
and translate the wire format (Pydantic DTOs) to/from domain dataclasses.
Keeping this translation in a dedicated module means the routers stay thin
and the Pydantic shapes can evolve independently of the domain model.
"""

from __future__ import annotations

from weftlyflow.server.mappers.execution import execution_to_response
from weftlyflow.server.mappers.node_types import node_spec_to_response
from weftlyflow.server.mappers.workflow import (
    workflow_create_to_domain,
    workflow_to_response,
    workflow_update_to_domain,
)

__all__ = [
    "execution_to_response",
    "node_spec_to_response",
    "workflow_create_to_domain",
    "workflow_to_response",
    "workflow_update_to_domain",
]
