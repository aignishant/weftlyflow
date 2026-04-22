"""Cloudflare node — client/v4 REST API for zones and DNS records.

Dispatches to ``https://api.cloudflare.com/client/v4`` with the
distinctive dual-header scheme ``X-Auth-Email`` + ``X-Auth-Key``
sourced from
:class:`~weftlyflow.credentials.types.cloudflare_api.CloudflareApiCredential`.
The Global-API-Key auth path is explicitly *not* Bearer — both headers
must be present for Cloudflare to accept the request.

Parameters (all expression-capable):

* ``operation`` — ``list_zones``, ``get_zone``, ``list_dns_records``,
  ``create_dns_record``, ``update_dns_record``, ``delete_dns_record``.
* ``zone_id`` — target zone (all DNS operations + ``get_zone``).
* ``record_id`` — target DNS record (update/delete).
* ``type`` / ``name`` / ``content`` — record identity for create.
* ``ttl`` / ``proxied`` / ``priority`` — optional record attributes.
* ``fields`` — JSON patch body for ``update_dns_record``.
* ``per_page`` / ``page`` — pagination.
* ``status`` — filter for list_zones (active, pending, ...).

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
from weftlyflow.nodes.integrations.cloudflare.constants import (
    API_BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    OP_CREATE_DNS_RECORD,
    OP_DELETE_DNS_RECORD,
    OP_GET_ZONE,
    OP_LIST_DNS_RECORDS,
    OP_LIST_ZONES,
    OP_UPDATE_DNS_RECORD,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.cloudflare.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "cloudflare_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.cloudflare_api",)
_ZONE_ID_OPERATIONS: frozenset[str] = frozenset(
    {
        OP_GET_ZONE,
        OP_LIST_DNS_RECORDS,
        OP_CREATE_DNS_RECORD,
        OP_UPDATE_DNS_RECORD,
        OP_DELETE_DNS_RECORD,
    },
)
_RECORD_ID_OPERATIONS: frozenset[str] = frozenset(
    {OP_UPDATE_DNS_RECORD, OP_DELETE_DNS_RECORD},
)
_CREATE_FIELD_OPERATIONS: frozenset[str] = frozenset({OP_CREATE_DNS_RECORD})
_UPDATE_FIELD_OPERATIONS: frozenset[str] = frozenset({OP_UPDATE_DNS_RECORD})

log = structlog.get_logger(__name__)


class CloudflareNode(BaseNode):
    """Dispatch a single Cloudflare client/v4 call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.cloudflare",
        version=1,
        display_name="Cloudflare",
        description="Manage Cloudflare zones and DNS records.",
        icon="icons/cloudflare.svg",
        category=NodeCategory.INTEGRATION,
        group=["infrastructure", "dns"],
        documentation_url="https://developers.cloudflare.com/api/",
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
                default=OP_LIST_ZONES,
                required=True,
                options=[
                    PropertyOption(value=OP_LIST_ZONES, label="List Zones"),
                    PropertyOption(value=OP_GET_ZONE, label="Get Zone"),
                    PropertyOption(
                        value=OP_LIST_DNS_RECORDS, label="List DNS Records",
                    ),
                    PropertyOption(
                        value=OP_CREATE_DNS_RECORD, label="Create DNS Record",
                    ),
                    PropertyOption(
                        value=OP_UPDATE_DNS_RECORD, label="Update DNS Record",
                    ),
                    PropertyOption(
                        value=OP_DELETE_DNS_RECORD, label="Delete DNS Record",
                    ),
                ],
            ),
            PropertySchema(
                name="zone_id",
                display_name="Zone ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_ZONE_ID_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="record_id",
                display_name="Record ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_RECORD_ID_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="type",
                display_name="Record Type",
                type="options",
                description="DNS record type (A, CNAME, MX, ...).",
                options=[
                    PropertyOption(value="A", label="A"),
                    PropertyOption(value="AAAA", label="AAAA"),
                    PropertyOption(value="CNAME", label="CNAME"),
                    PropertyOption(value="MX", label="MX"),
                    PropertyOption(value="TXT", label="TXT"),
                    PropertyOption(value="NS", label="NS"),
                    PropertyOption(value="SRV", label="SRV"),
                    PropertyOption(value="CAA", label="CAA"),
                    PropertyOption(value="PTR", label="PTR"),
                ],
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_DNS_RECORDS, OP_CREATE_DNS_RECORD]},
                ),
            ),
            PropertySchema(
                name="name",
                display_name="Record Name",
                type="string",
                display_options=DisplayOptions(
                    show={
                        "operation": [
                            OP_LIST_ZONES,
                            OP_LIST_DNS_RECORDS,
                            OP_CREATE_DNS_RECORD,
                        ],
                    },
                ),
            ),
            PropertySchema(
                name="content",
                display_name="Content",
                type="string",
                description="Record value (e.g. IP address for A records).",
                display_options=DisplayOptions(
                    show={"operation": list(_CREATE_FIELD_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="ttl",
                display_name="TTL",
                type="number",
                description="Seconds (or 1 for Cloudflare auto).",
                display_options=DisplayOptions(
                    show={"operation": list(_CREATE_FIELD_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="proxied",
                display_name="Proxied",
                type="boolean",
                default=False,
                display_options=DisplayOptions(
                    show={"operation": list(_CREATE_FIELD_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="priority",
                display_name="Priority",
                type="number",
                description="MX / SRV priority.",
                display_options=DisplayOptions(
                    show={"operation": list(_CREATE_FIELD_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="fields",
                display_name="Fields",
                type="json",
                description="JSON patch body for update_dns_record.",
                display_options=DisplayOptions(
                    show={"operation": list(_UPDATE_FIELD_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="status",
                display_name="Zone Status",
                type="string",
                description="Filter for list_zones (active, pending, ...).",
                display_options=DisplayOptions(show={"operation": [OP_LIST_ZONES]}),
            ),
            PropertySchema(
                name="per_page",
                display_name="Per Page",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_ZONES, OP_LIST_DNS_RECORDS]},
                ),
            ),
            PropertySchema(
                name="page",
                display_name="Page",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_ZONES, OP_LIST_DNS_RECORDS]},
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Cloudflare client/v4 call per input item."""
        email, key = await _resolve_credentials(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=API_BASE_URL, timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(
                        ctx,
                        item,
                        client=client,
                        email=email,
                        key=key,
                        logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> tuple[str, str]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Cloudflare: a cloudflare_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    email = str(payload.get("api_email") or "").strip()
    if not email:
        msg = "Cloudflare: credential has an empty 'api_email'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    key = str(payload.get("api_key") or "").strip()
    if not key:
        msg = "Cloudflare: credential has an empty 'api_key'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return email, key


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    email: str,
    key: str,
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_LIST_ZONES).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Cloudflare: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, body, query = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    try:
        response = await client.request(
            method,
            path,
            params=query or None,
            json=body,
            headers={
                "X-Auth-Email": email,
                "X-Auth-Key": key,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
    except httpx.HTTPError as exc:
        logger.error("cloudflare.request_failed", operation=operation, error=str(exc))
        msg = f"Cloudflare: network error on {operation}: {exc}"
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
            "cloudflare.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Cloudflare {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("cloudflare.ok", operation=operation, status=response.status_code)
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
        errors = payload.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0]
            if isinstance(first, dict):
                code = first.get("code")
                message = first.get("message")
                if isinstance(message, str) and message:
                    return f"{code}: {message}" if code else message
    return f"HTTP {status_code}"
