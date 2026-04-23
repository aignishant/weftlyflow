"""Elasticsearch node — search, index, bulk operations.

Dispatches to the per-cluster base URL sourced from
:class:`~weftlyflow.credentials.types.elasticsearch_api.ElasticsearchApiCredential`
with the distinctive ``Authorization: ApiKey <b64(id:key)>`` scheme.

Parameters (all expression-capable):

* ``operation`` — ``search``, ``index``, ``get``, ``update``,
  ``delete``, ``bulk``.
* ``index`` — target index name (required for everything except
  cluster-wide bulk).
* ``id`` — document identifier (required for get/update/delete;
  optional for index).
* ``document`` — JSON body for index / update.
* ``script`` — alternative JSON script object for update.
* ``query`` / ``size`` / ``from_`` / ``sort`` — search inputs.
* ``actions`` — list of ``{action: {...}, doc: {...}}`` objects for
  bulk.
* ``refresh`` — ``true``, ``false``, or ``wait_for`` (write ops).

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import structlog

from weftlyflow.credentials.types.elasticsearch_api import (
    api_key_header,
    base_url_from,
)
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
from weftlyflow.nodes.integrations.elasticsearch.constants import (
    DEFAULT_TIMEOUT_SECONDS,
    OP_BULK,
    OP_DELETE,
    OP_GET,
    OP_INDEX,
    OP_SEARCH,
    OP_UPDATE,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.elasticsearch.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "elasticsearch_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.elasticsearch_api",)
_DOC_ID_OPERATIONS: frozenset[str] = frozenset({OP_GET, OP_UPDATE, OP_DELETE})
_WRITE_OPERATIONS: frozenset[str] = frozenset(
    {OP_INDEX, OP_UPDATE, OP_DELETE, OP_BULK},
)

log = structlog.get_logger(__name__)


class ElasticsearchNode(BaseNode):
    """Dispatch a single Elasticsearch REST call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.elasticsearch",
        version=1,
        display_name="Elasticsearch",
        description="Search and mutate Elasticsearch indices.",
        icon="icons/elasticsearch.svg",
        category=NodeCategory.INTEGRATION,
        group=["database", "search"],
        documentation_url=(
            "https://www.elastic.co/guide/en/elasticsearch/reference/current/"
            "rest-apis.html"
        ),
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
                    PropertyOption(value=OP_INDEX, label="Index Document"),
                    PropertyOption(value=OP_GET, label="Get Document"),
                    PropertyOption(value=OP_UPDATE, label="Update Document"),
                    PropertyOption(value=OP_DELETE, label="Delete Document"),
                    PropertyOption(value=OP_BULK, label="Bulk"),
                ],
            ),
            PropertySchema(
                name="index",
                display_name="Index",
                type="string",
                required=False,
                description="Target index (required for all but cluster-wide bulk).",
            ),
            PropertySchema(
                name="id",
                display_name="Document ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [*_DOC_ID_OPERATIONS, OP_INDEX]},
                ),
            ),
            PropertySchema(
                name="document",
                display_name="Document",
                type="json",
                description="Document body for index / update.",
                display_options=DisplayOptions(
                    show={"operation": [OP_INDEX, OP_UPDATE]},
                ),
            ),
            PropertySchema(
                name="script",
                display_name="Script",
                type="json",
                description="Alternative update script object.",
                display_options=DisplayOptions(show={"operation": [OP_UPDATE]}),
            ),
            PropertySchema(
                name="query",
                display_name="Query",
                type="json",
                description="Elasticsearch query DSL object.",
                display_options=DisplayOptions(show={"operation": [OP_SEARCH]}),
            ),
            PropertySchema(
                name="size",
                display_name="Size",
                type="number",
                default=10,
                display_options=DisplayOptions(show={"operation": [OP_SEARCH]}),
            ),
            PropertySchema(
                name="from_",
                display_name="From",
                type="number",
                description="Offset for paginated search.",
                display_options=DisplayOptions(show={"operation": [OP_SEARCH]}),
            ),
            PropertySchema(
                name="sort",
                display_name="Sort",
                type="json",
                description="Sort spec (list or object).",
                display_options=DisplayOptions(show={"operation": [OP_SEARCH]}),
            ),
            PropertySchema(
                name="actions",
                display_name="Actions",
                type="json",
                description="Bulk actions: list of {action, doc}.",
                display_options=DisplayOptions(show={"operation": [OP_BULK]}),
            ),
            PropertySchema(
                name="refresh",
                display_name="Refresh",
                type="string",
                description="'true', 'false', or 'wait_for'.",
                display_options=DisplayOptions(
                    show={"operation": list(_WRITE_OPERATIONS)},
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Elasticsearch REST call per input item."""
        key_id, api_key, raw_base_url = await _resolve_credentials(ctx)
        try:
            base_url = base_url_from(raw_base_url)
        except ValueError as exc:
            raise NodeExecutionError(
                str(exc), node_id=ctx.node.id, original=exc,
            ) from exc
        auth_header = api_key_header(key_id, api_key)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=base_url, timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(
                        ctx,
                        item,
                        client=client,
                        auth_header=auth_header,
                        logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> tuple[str, str, str]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Elasticsearch: an elasticsearch_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    key_id = str(payload.get("api_key_id") or "").strip()
    if not key_id:
        msg = "Elasticsearch: credential has an empty 'api_key_id'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    api_key = str(payload.get("api_key") or "").strip()
    if not api_key:
        msg = "Elasticsearch: credential has an empty 'api_key'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    base_url = str(payload.get("base_url") or "").strip()
    if not base_url:
        msg = "Elasticsearch: credential has an empty 'base_url'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return key_id, api_key, base_url


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    auth_header: str,
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_SEARCH).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Elasticsearch: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, body, query, content_type = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    request_kwargs: dict[str, Any] = {
        "params": query or None,
        "headers": {
            "Authorization": auth_header,
            "Accept": "application/json",
            "Content-Type": content_type,
        },
    }
    if content_type == "application/x-ndjson":
        request_kwargs["content"] = body
    elif body is not None:
        request_kwargs["json"] = body
    try:
        response = await client.request(method, path, **request_kwargs)
    except httpx.HTTPError as exc:
        logger.error(
            "elasticsearch.request_failed", operation=operation, error=str(exc),
        )
        msg = f"Elasticsearch: network error on {operation}: {exc}"
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
            "elasticsearch.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Elasticsearch {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("elasticsearch.ok", operation=operation, status=response.status_code)
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
        error = payload.get("error")
        if isinstance(error, dict):
            reason = error.get("reason")
            type_name = error.get("type")
            if isinstance(reason, str) and reason:
                if isinstance(type_name, str) and type_name:
                    return f"{type_name}: {reason}"
                return reason
            if isinstance(type_name, str) and type_name:
                return type_name
        if isinstance(error, str) and error:
            return error
    return f"HTTP {status_code}"
