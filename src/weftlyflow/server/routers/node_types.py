"""Node-type catalog endpoints — public metadata for the editor palette."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, status

from weftlyflow.auth.constants import SCOPE_WORKFLOW_READ
from weftlyflow.nodes.registry import NodeRegistryError
from weftlyflow.server.deps import get_registry, require_scope
from weftlyflow.server.mappers.node_types import node_spec_to_response
from weftlyflow.server.schemas.node_types import NodeTypeResponse

if TYPE_CHECKING:
    from weftlyflow.nodes.registry import NodeRegistry

router = APIRouter(prefix="/api/v1/node-types", tags=["node-types"])


@router.get(
    "",
    response_model=list[NodeTypeResponse],
    dependencies=[Depends(require_scope(SCOPE_WORKFLOW_READ))],
    summary="Return every registered node type",
)
async def list_node_types(
    registry: NodeRegistry = Depends(get_registry),
) -> list[NodeTypeResponse]:
    """Return the full catalog — cached by clients via response ETag in Phase 3."""
    return [node_spec_to_response(spec) for spec in registry.catalog()]


@router.get(
    "/{node_type}",
    response_model=NodeTypeResponse,
    dependencies=[Depends(require_scope(SCOPE_WORKFLOW_READ))],
    summary="Return the latest version of one node type",
)
async def get_node_type(
    node_type: str,
    registry: NodeRegistry = Depends(get_registry),
) -> NodeTypeResponse:
    """Return the latest-version spec for ``node_type``."""
    try:
        node_cls = registry.latest(node_type)
    except NodeRegistryError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return node_spec_to_response(node_cls.spec)
