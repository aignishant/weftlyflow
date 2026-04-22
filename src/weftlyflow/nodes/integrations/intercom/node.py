"""Intercom node — REST API for contacts and conversations.

Dispatches to ``https://api.intercom.io/...`` with both
``Authorization: Bearer <token>`` **and** ``Intercom-Version: <version>``
from a
:class:`~weftlyflow.credentials.types.intercom_api.IntercomApiCredential`.
The version lives on the credential so a workflow targeting one account
always hits a consistent API surface.

Parameters (all expression-capable):

* ``operation`` — ``create_contact``, ``update_contact``, ``get_contact``,
  ``search_contacts``, ``create_conversation``, ``reply_conversation``.
* ``role`` — ``user`` or ``lead`` on ``create_contact``.
* ``email`` / ``external_id`` / ``phone`` / ``name`` / ``custom_attributes``
  — ``create_contact`` (one identifier is required).
* ``contact_id`` — for get/update/create_conversation.
* ``fields`` — JSON of updates for ``update_contact``.
* ``query`` — JSON search query for ``search_contacts``.
* ``per_page`` — search page size (capped at 150).
* ``contact_type`` — ``user`` or ``lead`` for ``create_conversation``.
* ``conversation_id`` — for ``reply_conversation``.
* ``reply_type`` — ``user`` or ``admin`` on ``reply_conversation``.
* ``message_type`` — ``comment``, ``note``, ``quick_reply``, ``close``.
* ``admin_id`` / ``user_id`` — identity for ``reply_conversation``.
* ``body`` — message text for create/reply conversation.

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response``. ``search_contacts`` surfaces a convenience
``data`` list.
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
from weftlyflow.nodes.integrations.intercom.constants import (
    API_BASE_URL,
    DEFAULT_SEARCH_LIMIT,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_VERSION,
    OP_CREATE_CONTACT,
    OP_CREATE_CONVERSATION,
    OP_GET_CONTACT,
    OP_REPLY_CONVERSATION,
    OP_SEARCH_CONTACTS,
    OP_UPDATE_CONTACT,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.intercom.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "intercom_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.intercom_api",)
_CONTACT_ID_OPERATIONS: frozenset[str] = frozenset(
    {OP_GET_CONTACT, OP_UPDATE_CONTACT, OP_CREATE_CONVERSATION},
)

log = structlog.get_logger(__name__)


class IntercomNode(BaseNode):
    """Dispatch a single Intercom REST call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.intercom",
        version=1,
        display_name="Intercom",
        description="Manage Intercom contacts and conversations.",
        icon="icons/intercom.svg",
        category=NodeCategory.INTEGRATION,
        group=["crm", "support"],
        documentation_url="https://developers.intercom.com/docs/references/rest-api/",
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
                default=OP_GET_CONTACT,
                required=True,
                options=[
                    PropertyOption(value=OP_CREATE_CONTACT, label="Create Contact"),
                    PropertyOption(value=OP_UPDATE_CONTACT, label="Update Contact"),
                    PropertyOption(value=OP_GET_CONTACT, label="Get Contact"),
                    PropertyOption(value=OP_SEARCH_CONTACTS, label="Search Contacts"),
                    PropertyOption(
                        value=OP_CREATE_CONVERSATION, label="Create Conversation",
                    ),
                    PropertyOption(
                        value=OP_REPLY_CONVERSATION, label="Reply to Conversation",
                    ),
                ],
            ),
            PropertySchema(
                name="contact_id",
                display_name="Contact ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_CONTACT_ID_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="role",
                display_name="Role",
                type="options",
                default="user",
                options=[
                    PropertyOption(value="user", label="User"),
                    PropertyOption(value="lead", label="Lead"),
                ],
                display_options=DisplayOptions(show={"operation": [OP_CREATE_CONTACT]}),
            ),
            PropertySchema(
                name="email",
                display_name="Email",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_CONTACT]}),
            ),
            PropertySchema(
                name="external_id",
                display_name="External ID",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_CONTACT]}),
            ),
            PropertySchema(
                name="phone",
                display_name="Phone",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_CONTACT]}),
            ),
            PropertySchema(
                name="name",
                display_name="Name",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_CONTACT]}),
            ),
            PropertySchema(
                name="custom_attributes",
                display_name="Custom Attributes",
                type="json",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_CONTACT]}),
            ),
            PropertySchema(
                name="fields",
                display_name="Fields",
                type="json",
                display_options=DisplayOptions(show={"operation": [OP_UPDATE_CONTACT]}),
            ),
            PropertySchema(
                name="query",
                display_name="Query",
                type="json",
                description="Intercom search query object.",
                display_options=DisplayOptions(show={"operation": [OP_SEARCH_CONTACTS]}),
            ),
            PropertySchema(
                name="per_page",
                display_name="Per Page",
                type="number",
                default=DEFAULT_SEARCH_LIMIT,
                display_options=DisplayOptions(show={"operation": [OP_SEARCH_CONTACTS]}),
            ),
            PropertySchema(
                name="contact_type",
                display_name="Contact Type",
                type="options",
                default="user",
                options=[
                    PropertyOption(value="user", label="User"),
                    PropertyOption(value="lead", label="Lead"),
                ],
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_CONVERSATION]},
                ),
            ),
            PropertySchema(
                name="conversation_id",
                display_name="Conversation ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_REPLY_CONVERSATION]},
                ),
            ),
            PropertySchema(
                name="reply_type",
                display_name="Reply Type",
                type="options",
                default="user",
                options=[
                    PropertyOption(value="user", label="User"),
                    PropertyOption(value="admin", label="Admin"),
                ],
                display_options=DisplayOptions(
                    show={"operation": [OP_REPLY_CONVERSATION]},
                ),
            ),
            PropertySchema(
                name="message_type",
                display_name="Message Type",
                type="options",
                default="comment",
                options=[
                    PropertyOption(value="comment", label="Comment"),
                    PropertyOption(value="note", label="Note"),
                    PropertyOption(value="quick_reply", label="Quick Reply"),
                    PropertyOption(value="close", label="Close"),
                ],
                display_options=DisplayOptions(
                    show={"operation": [OP_REPLY_CONVERSATION]},
                ),
            ),
            PropertySchema(
                name="admin_id",
                display_name="Admin ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_REPLY_CONVERSATION]},
                ),
            ),
            PropertySchema(
                name="user_id",
                display_name="User ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_REPLY_CONVERSATION]},
                ),
            ),
            PropertySchema(
                name="body",
                display_name="Body",
                type="string",
                display_options=DisplayOptions(
                    show={
                        "operation": [OP_CREATE_CONVERSATION, OP_REPLY_CONVERSATION],
                    },
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Intercom REST call per input item."""
        token, version = await _resolve_credentials(ctx)
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
                        token=token,
                        version=version,
                        logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> tuple[str, str]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Intercom: an intercom_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    token = str(payload.get("access_token") or "").strip()
    if not token:
        msg = "Intercom: credential has an empty 'access_token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    version = str(payload.get("api_version") or DEFAULT_VERSION).strip() or DEFAULT_VERSION
    return token, version


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    token: str,
    version: str,
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_GET_CONTACT).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Intercom: unsupported operation {operation!r}"
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
                "Authorization": f"Bearer {token}",
                "Intercom-Version": version,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
    except httpx.HTTPError as exc:
        logger.error("intercom.request_failed", operation=operation, error=str(exc))
        msg = f"Intercom: network error on {operation}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    payload = _safe_json(response)
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "response": payload,
    }
    if operation == OP_SEARCH_CONTACTS and isinstance(payload, dict):
        data = payload.get("data", [])
        result["data"] = data if isinstance(data, list) else []
    if response.status_code >= httpx.codes.BAD_REQUEST:
        error = _error_message(payload, response.status_code)
        logger.warning(
            "intercom.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Intercom {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("intercom.ok", operation=operation, status=response.status_code)
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
            parts: list[str] = []
            for err in errors:
                if isinstance(err, dict):
                    code = err.get("code")
                    message = err.get("message")
                    if message:
                        parts.append(f"{code}: {message}" if code else str(message))
            if parts:
                return "; ".join(parts)
        message = payload.get("message")
        if isinstance(message, str) and message:
            return message
    return f"HTTP {status_code}"
