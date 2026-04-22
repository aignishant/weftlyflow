"""Algolia node — Search v1 REST API for indices and records.

Dispatches to either ``https://<app>-dsn.algolia.net/...`` (reads) or
``https://<app>.algolia.net/...`` (writes) with the dual
``X-Algolia-Application-Id`` + ``X-Algolia-API-Key`` headers sourced
from
:class:`~weftlyflow.credentials.types.algolia_api.AlgoliaApiCredential`.

Parameters (all expression-capable):

* ``operation`` — ``search``, ``add_object``, ``update_object``,
  ``get_object``, ``delete_object``, ``list_indices``.
* ``index_name`` — target index (all ops except ``list_indices``).
* ``object_id`` — record key (get/update/delete).
* ``object`` — JSON record body (add/update).
* ``query`` / ``filters`` / ``page`` / ``hits_per_page`` / ``extra_params``
  — search controls.

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response``; ``search`` surfaces a convenience ``hits`` list.
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
from weftlyflow.nodes.integrations.algolia.constants import (
    DEFAULT_HITS_PER_PAGE,
    DEFAULT_TIMEOUT_SECONDS,
    OP_ADD_OBJECT,
    OP_DELETE_OBJECT,
    OP_GET_OBJECT,
    OP_LIST_INDICES,
    OP_SEARCH,
    OP_UPDATE_OBJECT,
    SUPPORTED_OPERATIONS,
    search_host_for,
    write_host_for,
)
from weftlyflow.nodes.integrations.algolia.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "algolia_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.algolia_api",)
_INDEX_OPERATIONS: frozenset[str] = frozenset(
    {OP_SEARCH, OP_ADD_OBJECT, OP_UPDATE_OBJECT, OP_GET_OBJECT, OP_DELETE_OBJECT},
)
_OBJECT_ID_OPERATIONS: frozenset[str] = frozenset(
    {OP_UPDATE_OBJECT, OP_GET_OBJECT, OP_DELETE_OBJECT},
)
_OBJECT_BODY_OPERATIONS: frozenset[str] = frozenset(
    {OP_ADD_OBJECT, OP_UPDATE_OBJECT},
)

log = structlog.get_logger(__name__)


class AlgoliaNode(BaseNode):
    """Dispatch a single Algolia Search v1 call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.algolia",
        version=1,
        display_name="Algolia",
        description="Query and manage Algolia search indices.",
        icon="icons/algolia.svg",
        category=NodeCategory.INTEGRATION,
        group=["search", "data"],
        documentation_url="https://www.algolia.com/doc/rest-api/search/",
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
                default=OP_SEARCH,
                required=True,
                options=[
                    PropertyOption(value=OP_SEARCH, label="Search"),
                    PropertyOption(value=OP_ADD_OBJECT, label="Add Object"),
                    PropertyOption(value=OP_UPDATE_OBJECT, label="Update Object"),
                    PropertyOption(value=OP_GET_OBJECT, label="Get Object"),
                    PropertyOption(value=OP_DELETE_OBJECT, label="Delete Object"),
                    PropertyOption(value=OP_LIST_INDICES, label="List Indices"),
                ],
            ),
            PropertySchema(
                name="index_name",
                display_name="Index Name",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_INDEX_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="object_id",
                display_name="Object ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_OBJECT_ID_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="object",
                display_name="Object",
                type="json",
                description="Record body for add/update operations.",
                display_options=DisplayOptions(
                    show={"operation": list(_OBJECT_BODY_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="query",
                display_name="Query",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_SEARCH]}),
            ),
            PropertySchema(
                name="filters",
                display_name="Filters",
                type="string",
                description="Algolia filter expression.",
                display_options=DisplayOptions(show={"operation": [OP_SEARCH]}),
            ),
            PropertySchema(
                name="page",
                display_name="Page",
                type="number",
                display_options=DisplayOptions(show={"operation": [OP_SEARCH]}),
            ),
            PropertySchema(
                name="hits_per_page",
                display_name="Hits per Page",
                type="number",
                default=DEFAULT_HITS_PER_PAGE,
                display_options=DisplayOptions(show={"operation": [OP_SEARCH]}),
            ),
            PropertySchema(
                name="extra_params",
                display_name="Extra Params",
                type="json",
                description="Merged into the JSON search body.",
                display_options=DisplayOptions(show={"operation": [OP_SEARCH]}),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Algolia REST call per input item."""
        app_id, key = await _resolve_credentials(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(
                        ctx,
                        item,
                        client=client,
                        app_id=app_id,
                        key=key,
                        logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> tuple[str, str]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Algolia: an algolia_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    app_id = str(payload.get("application_id") or "").strip()
    key = str(payload.get("api_key") or "").strip()
    if not app_id or not key:
        msg = "Algolia: credential must have 'application_id' and 'api_key'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return app_id, key


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    app_id: str,
    key: str,
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_SEARCH).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Algolia: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, body, query, use_write_host = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    host = write_host_for(app_id) if use_write_host else search_host_for(app_id)
    url = f"https://{host}{path}"
    try:
        response = await client.request(
            method,
            url,
            params=query or None,
            json=body,
            headers={
                "X-Algolia-Application-Id": app_id,
                "X-Algolia-API-Key": key,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
    except httpx.HTTPError as exc:
        logger.error("algolia.request_failed", operation=operation, error=str(exc))
        msg = f"Algolia: network error on {operation}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    payload = _safe_json(response)
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "response": payload,
    }
    if operation == OP_SEARCH and isinstance(payload, dict):
        hits = payload.get("hits", [])
        result["hits"] = hits if isinstance(hits, list) else []
    if response.status_code >= httpx.codes.BAD_REQUEST:
        error = _error_message(payload, response.status_code)
        logger.warning(
            "algolia.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Algolia {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("algolia.ok", operation=operation, status=response.status_code)
    return Item(json=result)


def _safe_json(response: httpx.Response) -> Any:
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text, "status_code": response.status_code}


def _error_message(payload: Any, status_code: int) -> str:
    if isinstance(payload, dict):
        message = payload.get("message")
        if isinstance(message, str) and message:
            return message
    return f"HTTP {status_code}"
