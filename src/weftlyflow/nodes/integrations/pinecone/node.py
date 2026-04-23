"""Pinecone node — vector and index operations via Pinecone REST.

Dispatches to the Pinecone API with a distinctive split between two
hosts:

* **Control plane** (``https://api.pinecone.io``) — ``list_indexes``
  and ``describe_index`` hit the global control-plane host.
* **Data plane** — ``query_vectors``, ``upsert_vectors``,
  ``fetch_vectors``, and ``delete_vectors`` require a per-index
  ``host`` parameter (returned by ``describe_index`` as ``host``)
  because each Pinecone index lives on its own svc subdomain.

Auth is a flat ``Api-Key: <key>`` header handled by
:class:`~weftlyflow.credentials.types.pinecone_api.PineconeApiCredential`.

Parameters (all expression-capable):

* ``operation`` — one of ``list_indexes``, ``describe_index``,
  ``query_vectors``, ``upsert_vectors``, ``fetch_vectors``,
  ``delete_vectors``.
* ``index_name`` — required for ``describe_index``.
* ``host`` — required for any data-plane op.
* ``top_k`` / ``vector`` / ``id`` / ``filter`` — ``query_vectors``.
* ``vectors`` — ``upsert_vectors``.
* ``ids`` / ``delete_all`` — ``fetch_vectors`` / ``delete_vectors``.
* ``namespace`` — common to all data-plane ops.

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response`` body.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import structlog

from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.node_spec import (
    CredentialSlot,
    DisplayOptions,
    NodeCategory,
    NodeSpec,
    PropertyOption,
    PropertySchema,
)
from weftlyflow.nodes.base import BaseNode
from weftlyflow.nodes.integrations.pinecone.constants import (
    CONTROL_PLANE_HOST,
    CONTROL_PLANE_OPERATIONS,
    DATA_PLANE_OPERATIONS,
    DEFAULT_TIMEOUT_SECONDS,
    OP_DELETE_VECTORS,
    OP_DESCRIBE_INDEX,
    OP_FETCH_VECTORS,
    OP_LIST_INDEXES,
    OP_QUERY_VECTORS,
    OP_UPSERT_VECTORS,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.pinecone.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "pinecone_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.pinecone_api",)
_DESCRIBE_OPERATIONS: frozenset[str] = frozenset({OP_DESCRIBE_INDEX})
_QUERY_OPERATIONS: frozenset[str] = frozenset({OP_QUERY_VECTORS})
_UPSERT_OPERATIONS: frozenset[str] = frozenset({OP_UPSERT_VECTORS})
_FETCH_OPERATIONS: frozenset[str] = frozenset({OP_FETCH_VECTORS})
_DELETE_OPERATIONS: frozenset[str] = frozenset({OP_DELETE_VECTORS})

log = structlog.get_logger(__name__)


class PineconeNode(BaseNode):
    """Dispatch a single Pinecone API call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.pinecone",
        version=1,
        display_name="Pinecone",
        description="Manage indexes and vectors on Pinecone via the REST API.",
        icon="icons/pinecone.svg",
        category=NodeCategory.INTEGRATION,
        group=["ai", "vector-db"],
        documentation_url="https://docs.pinecone.io/reference/api/introduction",
        credentials=[
            CredentialSlot(
                name=_CREDENTIAL_SLOT,
                required=True,
                credential_types=list(_CREDENTIAL_SLUGS),
            ),
        ],
        properties=[
            PropertySchema(
                name="operation",
                display_name="Operation",
                type="options",
                default=OP_LIST_INDEXES,
                required=True,
                options=[
                    PropertyOption(value=OP_LIST_INDEXES, label="List Indexes"),
                    PropertyOption(value=OP_DESCRIBE_INDEX, label="Describe Index"),
                    PropertyOption(value=OP_QUERY_VECTORS, label="Query Vectors"),
                    PropertyOption(value=OP_UPSERT_VECTORS, label="Upsert Vectors"),
                    PropertyOption(value=OP_FETCH_VECTORS, label="Fetch Vectors"),
                    PropertyOption(value=OP_DELETE_VECTORS, label="Delete Vectors"),
                ],
            ),
            PropertySchema(
                name="index_name",
                display_name="Index Name",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_DESCRIBE_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="host",
                display_name="Data-Plane Host",
                type="string",
                description="Per-index host, e.g. 'my-index-proj.svc.us-east-1-aws.pinecone.io'.",
                display_options=DisplayOptions(
                    show={"operation": list(DATA_PLANE_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="namespace",
                display_name="Namespace",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(DATA_PLANE_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="top_k",
                display_name="Top K",
                type="number",
                default=10,
                display_options=DisplayOptions(
                    show={"operation": list(_QUERY_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="vector",
                display_name="Query Vector",
                type="json",
                description="Array of floats representing the query embedding.",
                display_options=DisplayOptions(
                    show={"operation": list(_QUERY_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="id",
                display_name="Query by ID",
                type="string",
                description="Use a stored vector's id instead of an explicit vector.",
                display_options=DisplayOptions(
                    show={"operation": list(_QUERY_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="filter",
                display_name="Metadata Filter",
                type="json",
                description="Pinecone metadata filter expression.",
                display_options=DisplayOptions(
                    show={"operation": [OP_QUERY_VECTORS, OP_DELETE_VECTORS]},
                ),
            ),
            PropertySchema(
                name="include_values",
                display_name="Include Values",
                type="boolean",
                default=False,
                display_options=DisplayOptions(
                    show={"operation": list(_QUERY_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="include_metadata",
                display_name="Include Metadata",
                type="boolean",
                default=True,
                display_options=DisplayOptions(
                    show={"operation": list(_QUERY_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="vectors",
                display_name="Vectors",
                type="json",
                description="Array of {id, values, metadata?} objects to upsert.",
                display_options=DisplayOptions(
                    show={"operation": list(_UPSERT_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="ids",
                display_name="Vector IDs",
                type="json",
                description="Array of vector ids.",
                display_options=DisplayOptions(
                    show={"operation": [OP_FETCH_VECTORS, OP_DELETE_VECTORS]},
                ),
            ),
            PropertySchema(
                name="delete_all",
                display_name="Delete All in Namespace",
                type="boolean",
                default=False,
                display_options=DisplayOptions(
                    show={"operation": list(_DELETE_OPERATIONS)},
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Pinecone REST call per input item."""
        injector, payload = await _resolve_credentials(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        for item in seed:
            results.append(
                await _dispatch_one(
                    ctx,
                    item,
                    injector=injector,
                    creds=payload,
                    logger=bound,
                ),
            )
        return [results]


async def _resolve_credentials(
    ctx: ExecutionContext,
) -> tuple[Any, dict[str, Any]]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Pinecone: a pinecone_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    injector, payload = credential
    if not str(payload.get("api_key") or "").strip():
        msg = "Pinecone: credential has an empty 'api_key'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return injector, payload


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    injector: Any,
    creds: dict[str, Any],
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_LIST_INDEXES).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Pinecone: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    base_url = _resolve_base_url(ctx, operation, params)
    try:
        method, path, body, query = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    request_headers: dict[str, str] = {"Accept": "application/json"}
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    async with httpx.AsyncClient(
        base_url=base_url, timeout=DEFAULT_TIMEOUT_SECONDS,
    ) as client:
        request = client.build_request(
            method,
            path,
            params=query or None,
            json=body,
            headers=request_headers,
        )
        request = await injector.inject(creds, request)
        try:
            response = await client.send(request)
        except httpx.HTTPError as exc:
            logger.error("pinecone.request_failed", operation=operation, error=str(exc))
            msg = f"Pinecone: network error on {operation}: {exc}"
            raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    payload = _safe_json(response)
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "response": payload,
    }
    if response.status_code >= httpx.codes.BAD_REQUEST:
        error = _error_message(payload, response.status_code)
        logger.warning(
            "pinecone.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Pinecone {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("pinecone.ok", operation=operation, status=response.status_code)
    return Item(json=result)


def _resolve_base_url(
    ctx: ExecutionContext,
    operation: str,
    params: dict[str, Any],
) -> str:
    if operation in CONTROL_PLANE_OPERATIONS:
        return CONTROL_PLANE_HOST
    host = str(params.get("host") or "").strip()
    if not host:
        msg = f"Pinecone: {operation!r} requires the data-plane 'host' parameter"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    if not host.startswith(("http://", "https://")):
        host = f"https://{host}"
    return host.rstrip("/")


def _safe_json(response: httpx.Response) -> Any:
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text, "status_code": response.status_code}


def _error_message(payload: Any, status_code: int) -> str:
    if isinstance(payload, dict):
        message = payload.get("message") or payload.get("error")
        if isinstance(message, str) and message:
            return message
        if isinstance(message, dict):
            inner = message.get("message")
            if isinstance(inner, str) and inner:
                return inner
    return f"HTTP {status_code}"
