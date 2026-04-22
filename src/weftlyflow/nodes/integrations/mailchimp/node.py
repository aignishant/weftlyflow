"""Mailchimp node — Marketing v3 REST API for lists and members.

Dispatches to ``https://<datacenter>.api.mailchimp.com/3.0/...`` with
HTTP Basic auth (``Authorization: Basic <base64("weftlyflow:<key>")>``)
sourced from
:class:`~weftlyflow.credentials.types.mailchimp_api.MailchimpApiCredential`.
The datacenter segment is parsed out of the API key's ``abc-us6`` suffix
via :func:`weftlyflow.credentials.types.mailchimp_api.datacenter_for`.

Parameters (all expression-capable):

* ``operation`` — ``list_lists``, ``get_list``, ``add_member``,
  ``update_member``, ``get_member``, ``tag_member``.
* ``list_id`` — audience/list identifier (all ops except
  ``list_lists``).
* ``email`` — target member address; Mailchimp identifies members by
  MD5 of the lowercased email.
* ``status`` — subscription status for ``add_member``.
* ``merge_fields`` — JSON of merge fields for ``add_member``.
* ``fields`` — JSON patch for ``update_member``.
* ``tags`` / ``add_tags`` / ``remove_tags`` — tag lists.
* ``count`` / ``offset`` — ``list_lists`` paging.

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response``; ``list_lists`` surfaces a convenience ``lists`` list.
"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import structlog

from weftlyflow.credentials.types.mailchimp_api import datacenter_for
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
from weftlyflow.nodes.integrations.mailchimp.constants import (
    DEFAULT_TIMEOUT_SECONDS,
    MEMBER_STATUSES,
    OP_ADD_MEMBER,
    OP_GET_LIST,
    OP_GET_MEMBER,
    OP_LIST_LISTS,
    OP_TAG_MEMBER,
    OP_UPDATE_MEMBER,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.mailchimp.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "mailchimp_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.mailchimp_api",)
_PLACEHOLDER_USER: str = "weftlyflow"
_LIST_ID_OPERATIONS: frozenset[str] = frozenset(
    {OP_GET_LIST, OP_ADD_MEMBER, OP_UPDATE_MEMBER, OP_GET_MEMBER, OP_TAG_MEMBER},
)
_EMAIL_OPERATIONS: frozenset[str] = frozenset(
    {OP_ADD_MEMBER, OP_UPDATE_MEMBER, OP_GET_MEMBER, OP_TAG_MEMBER},
)

log = structlog.get_logger(__name__)


class MailchimpNode(BaseNode):
    """Dispatch a single Mailchimp Marketing REST call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.mailchimp",
        version=1,
        display_name="Mailchimp",
        description="Manage Mailchimp audiences, members, and tags.",
        icon="icons/mailchimp.svg",
        category=NodeCategory.INTEGRATION,
        group=["communication", "marketing"],
        documentation_url="https://mailchimp.com/developer/marketing/api/",
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
                default=OP_LIST_LISTS,
                required=True,
                options=[
                    PropertyOption(value=OP_LIST_LISTS, label="List Lists"),
                    PropertyOption(value=OP_GET_LIST, label="Get List"),
                    PropertyOption(value=OP_ADD_MEMBER, label="Add Member"),
                    PropertyOption(value=OP_UPDATE_MEMBER, label="Update Member"),
                    PropertyOption(value=OP_GET_MEMBER, label="Get Member"),
                    PropertyOption(value=OP_TAG_MEMBER, label="Tag Member"),
                ],
            ),
            PropertySchema(
                name="list_id",
                display_name="List ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_LIST_ID_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="email",
                display_name="Email",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_EMAIL_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="status",
                display_name="Status",
                type="options",
                default="subscribed",
                options=[
                    PropertyOption(value=value, label=value.title())
                    for value in sorted(MEMBER_STATUSES)
                ],
                display_options=DisplayOptions(show={"operation": [OP_ADD_MEMBER]}),
            ),
            PropertySchema(
                name="merge_fields",
                display_name="Merge Fields",
                type="json",
                description="JSON of merge fields (e.g. FNAME, LNAME).",
                display_options=DisplayOptions(show={"operation": [OP_ADD_MEMBER]}),
            ),
            PropertySchema(
                name="tags",
                display_name="Tags",
                type="string",
                description="Comma-separated tag names applied on add.",
                display_options=DisplayOptions(show={"operation": [OP_ADD_MEMBER]}),
            ),
            PropertySchema(
                name="fields",
                display_name="Fields",
                type="json",
                description="JSON patch body for update_member.",
                display_options=DisplayOptions(show={"operation": [OP_UPDATE_MEMBER]}),
            ),
            PropertySchema(
                name="add_tags",
                display_name="Add Tags",
                type="string",
                description="Comma-separated tags to activate.",
                display_options=DisplayOptions(show={"operation": [OP_TAG_MEMBER]}),
            ),
            PropertySchema(
                name="remove_tags",
                display_name="Remove Tags",
                type="string",
                description="Comma-separated tags to deactivate.",
                display_options=DisplayOptions(show={"operation": [OP_TAG_MEMBER]}),
            ),
            PropertySchema(
                name="count",
                display_name="Count",
                type="number",
                description="Page size for list_lists (capped at 1000).",
                display_options=DisplayOptions(show={"operation": [OP_LIST_LISTS]}),
            ),
            PropertySchema(
                name="offset",
                display_name="Offset",
                type="number",
                display_options=DisplayOptions(show={"operation": [OP_LIST_LISTS]}),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Mailchimp REST call per input item."""
        key = await _resolve_credentials(ctx)
        try:
            datacenter = datacenter_for(key)
        except ValueError as exc:
            raise NodeExecutionError(
                str(exc), node_id=ctx.node.id, original=exc,
            ) from exc
        base_url = f"https://{datacenter}.api.mailchimp.com"
        auth_header = _basic_auth_header(key)
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


async def _resolve_credentials(ctx: ExecutionContext) -> str:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Mailchimp: a mailchimp_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    key = str(payload.get("api_key") or "").strip()
    if not key:
        msg = "Mailchimp: credential has an empty 'api_key'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return key


def _basic_auth_header(key: str) -> str:
    encoded = base64.b64encode(f"{_PLACEHOLDER_USER}:{key}".encode()).decode("ascii")
    return f"Basic {encoded}"


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    auth_header: str,
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_LIST_LISTS).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Mailchimp: unsupported operation {operation!r}"
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
                "Authorization": auth_header,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
    except httpx.HTTPError as exc:
        logger.error("mailchimp.request_failed", operation=operation, error=str(exc))
        msg = f"Mailchimp: network error on {operation}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    payload = _safe_json(response)
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "response": payload,
    }
    if operation == OP_LIST_LISTS and isinstance(payload, dict):
        lists = payload.get("lists", [])
        result["lists"] = lists if isinstance(lists, list) else []
    if response.status_code >= httpx.codes.BAD_REQUEST:
        error = _error_message(payload, response.status_code)
        logger.warning(
            "mailchimp.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Mailchimp {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("mailchimp.ok", operation=operation, status=response.status_code)
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
        detail = payload.get("detail")
        if isinstance(detail, str) and detail:
            return detail
        title = payload.get("title")
        if isinstance(title, str) and title:
            return title
    return f"HTTP {status_code}"
