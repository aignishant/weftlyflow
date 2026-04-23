"""Contentful node — Management + Delivery REST APIs with host-split routing.

Dispatches to either ``api.contentful.com`` (Management / CMA: writes
and draft reads) or ``cdn.contentful.com`` (Delivery / CDA: published
reads) based on the operation. Auth is a shared Bearer token handled by
:class:`~weftlyflow.credentials.types.contentful_api.ContentfulApiCredential`.

Distinctive Contentful shapes:

* **Split base URL** — the same token authenticates both hosts but the
  wire format differs slightly; list/get reads go to CDA, writes go to
  CMA.
* **Optimistic concurrency** — updates, publishes, and deletes require
  ``X-Contentful-Version`` carrying the *current* ``sys.version``. A
  stale version returns 409.
* **Management content-type** — writes send
  ``Content-Type: application/vnd.contentful.management.v1+json``.

Parameters (all expression-capable):

* ``operation`` — ``get_entry``, ``list_entries``, ``create_entry``,
  ``update_entry``, ``publish_entry``, ``delete_entry``, ``get_asset``.
* ``entry_id`` / ``asset_id`` — target resource.
* ``content_type`` — required on ``create_entry``; filter on
  ``list_entries``.
* ``fields`` — JSON object carrying the localised field map.
* ``version`` — current ``sys.version`` for concurrency-controlled ops.
* ``space_id`` / ``environment`` — per-call overrides; default to the
  credential's configured values.

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response``.
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
from weftlyflow.nodes.integrations.contentful.constants import (
    CONTENT_TYPE_HEADER_VALUE,
    DEFAULT_ENVIRONMENT,
    DEFAULT_TIMEOUT_SECONDS,
    DELIVERY_HOST,
    DELIVERY_OPERATIONS,
    MANAGEMENT_HOST,
    OP_CREATE_ENTRY,
    OP_DELETE_ENTRY,
    OP_GET_ASSET,
    OP_GET_ENTRY,
    OP_LIST_ENTRIES,
    OP_PUBLISH_ENTRY,
    OP_UPDATE_ENTRY,
    SUPPORTED_OPERATIONS,
    VERSION_HEADER,
)
from weftlyflow.nodes.integrations.contentful.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "contentful_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.contentful_api",)
_ENTRY_ID_OPERATIONS: frozenset[str] = frozenset(
    {OP_GET_ENTRY, OP_UPDATE_ENTRY, OP_PUBLISH_ENTRY, OP_DELETE_ENTRY},
)
_VERSIONED_OPERATIONS: frozenset[str] = frozenset(
    {OP_UPDATE_ENTRY, OP_PUBLISH_ENTRY, OP_DELETE_ENTRY},
)
_FIELDS_OPERATIONS: frozenset[str] = frozenset(
    {OP_CREATE_ENTRY, OP_UPDATE_ENTRY},
)
_CONTENT_TYPE_OPERATIONS: frozenset[str] = frozenset(
    {OP_CREATE_ENTRY, OP_LIST_ENTRIES},
)

log = structlog.get_logger(__name__)


class ContentfulNode(BaseNode):
    """Dispatch a single Contentful REST call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.contentful",
        version=1,
        display_name="Contentful",
        description="Read and write Contentful entries via Management + Delivery APIs.",
        icon="icons/contentful.svg",
        category=NodeCategory.INTEGRATION,
        group=["cms", "content"],
        documentation_url="https://www.contentful.com/developers/docs/references/",
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
                default=OP_LIST_ENTRIES,
                required=True,
                options=[
                    PropertyOption(value=OP_GET_ENTRY, label="Get Entry"),
                    PropertyOption(value=OP_LIST_ENTRIES, label="List Entries"),
                    PropertyOption(value=OP_CREATE_ENTRY, label="Create Entry"),
                    PropertyOption(value=OP_UPDATE_ENTRY, label="Update Entry"),
                    PropertyOption(value=OP_PUBLISH_ENTRY, label="Publish Entry"),
                    PropertyOption(value=OP_DELETE_ENTRY, label="Delete Entry"),
                    PropertyOption(value=OP_GET_ASSET, label="Get Asset"),
                ],
            ),
            PropertySchema(
                name="space_id",
                display_name="Space ID (override)",
                type="string",
                description="Optional per-call override; defaults to credential.",
            ),
            PropertySchema(
                name="environment",
                display_name="Environment (override)",
                type="string",
                description="Optional per-call override; defaults to credential.",
            ),
            PropertySchema(
                name="entry_id",
                display_name="Entry ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_ENTRY_ID_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="asset_id",
                display_name="Asset ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_GET_ASSET]},
                ),
            ),
            PropertySchema(
                name="content_type",
                display_name="Content Type",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_CONTENT_TYPE_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="fields",
                display_name="Fields",
                type="json",
                description='Localised field map, e.g. {"title": {"en-US": "Hi"}}.',
                display_options=DisplayOptions(
                    show={"operation": list(_FIELDS_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="version",
                display_name="Version",
                type="number",
                description="Current sys.version for optimistic concurrency.",
                display_options=DisplayOptions(
                    show={"operation": list(_VERSIONED_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="filters",
                display_name="Filters",
                type="json",
                description='Free-form filter map, e.g. {"fields.slug": "home"}.',
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_ENTRIES]},
                ),
            ),
            PropertySchema(
                name="limit",
                display_name="Limit",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_ENTRIES]},
                ),
            ),
            PropertySchema(
                name="skip",
                display_name="Skip",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_ENTRIES]},
                ),
            ),
            PropertySchema(
                name="order",
                display_name="Order",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_ENTRIES]},
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Contentful REST call per input item."""
        injector, payload = await _resolve_credentials(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        # Contentful splits hosts per operation — create one client per host
        # and dispatch to the right one.
        async with (
            httpx.AsyncClient(base_url=MANAGEMENT_HOST, timeout=DEFAULT_TIMEOUT_SECONDS) as cma,
            httpx.AsyncClient(base_url=DELIVERY_HOST, timeout=DEFAULT_TIMEOUT_SECONDS) as cda,
        ):
            for item in seed:
                results.append(
                    await _dispatch_one(
                        ctx,
                        item,
                        cma=cma,
                        cda=cda,
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
        msg = "Contentful: a contentful_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    injector, payload = credential
    if not str(payload.get("api_token") or "").strip():
        msg = "Contentful: credential has an empty 'api_token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return injector, payload


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    cma: httpx.AsyncClient,
    cda: httpx.AsyncClient,
    injector: Any,
    creds: dict[str, Any],
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_LIST_ENTRIES).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Contentful: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    space_id = (
        str(params.get("space_id") or "").strip()
        or str(creds.get("space_id") or "").strip()
    )
    environment = (
        str(params.get("environment") or "").strip()
        or str(creds.get("environment") or "").strip()
        or DEFAULT_ENVIRONMENT
    )
    try:
        method, path, body, query, version = build_request(
            operation,
            params,
            space_id=space_id,
            environment=environment,
        )
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    client = cda if operation in DELIVERY_OPERATIONS else cma
    request_headers: dict[str, str] = {"Accept": "application/json"}
    if body is not None:
        request_headers["Content-Type"] = CONTENT_TYPE_HEADER_VALUE
    if version is not None:
        request_headers[VERSION_HEADER] = str(version)
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
        logger.error("contentful.request_failed", operation=operation, error=str(exc))
        msg = f"Contentful: network error on {operation}: {exc}"
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
            "contentful.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Contentful {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("contentful.ok", operation=operation, status=response.status_code)
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
        details = payload.get("details")
        if isinstance(details, dict):
            errors = details.get("errors")
            if isinstance(errors, list) and errors:
                first = errors[0]
                if isinstance(first, dict):
                    detail = first.get("details") or first.get("name")
                    if isinstance(detail, str) and detail:
                        return detail
        sys_obj = payload.get("sys")
        if isinstance(sys_obj, dict):
            sys_id = sys_obj.get("id")
            if isinstance(sys_id, str) and sys_id:
                return sys_id
    return f"HTTP {status_code}"
