"""Brevo node — v3 REST API for transactional email and contact management.

Dispatches to ``https://api.brevo.com/v3/...`` with a lowercase
``api-key`` header sourced from
:class:`~weftlyflow.credentials.types.brevo_api.BrevoApiCredential`.

Parameters (all expression-capable):

* ``operation`` — ``send_email``, ``create_contact``, ``update_contact``,
  ``get_contact``, ``add_contact_to_list``, ``get_account``.
* ``sender`` — string email or ``{email, name?}`` object
  (``send_email``).
* ``to`` / ``cc`` / ``bcc`` / ``reply_to`` — recipient specs
  (``send_email``).
* ``subject`` / ``html_content`` / ``text_content`` / ``tags`` —
  content (``send_email``).
* ``email`` — target contact address (``create/update/get_contact``).
* ``attributes`` — JSON of contact attributes (create/update).
* ``list_ids`` / ``unlink_list_ids`` — contact-list membership.
* ``update_enabled`` — upsert switch on ``create_contact``.
* ``list_id`` / ``emails`` — targets for ``add_contact_to_list``.

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
from weftlyflow.nodes.integrations.brevo.constants import (
    API_BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    OP_ADD_CONTACT_TO_LIST,
    OP_CREATE_CONTACT,
    OP_GET_ACCOUNT,
    OP_GET_CONTACT,
    OP_SEND_EMAIL,
    OP_UPDATE_CONTACT,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.brevo.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "brevo_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.brevo_api",)
_EMAIL_ID_OPERATIONS: frozenset[str] = frozenset(
    {OP_CREATE_CONTACT, OP_UPDATE_CONTACT, OP_GET_CONTACT},
)
_ATTRIBUTES_OPERATIONS: frozenset[str] = frozenset(
    {OP_CREATE_CONTACT, OP_UPDATE_CONTACT},
)

log = structlog.get_logger(__name__)


class BrevoNode(BaseNode):
    """Dispatch a single Brevo REST call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.brevo",
        version=1,
        display_name="Brevo",
        description="Send transactional email and manage Brevo contacts.",
        icon="icons/brevo.svg",
        category=NodeCategory.INTEGRATION,
        group=["communication", "email"],
        documentation_url="https://developers.brevo.com/reference/",
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
                default=OP_SEND_EMAIL,
                required=True,
                options=[
                    PropertyOption(value=OP_SEND_EMAIL, label="Send Email"),
                    PropertyOption(value=OP_CREATE_CONTACT, label="Create Contact"),
                    PropertyOption(value=OP_UPDATE_CONTACT, label="Update Contact"),
                    PropertyOption(value=OP_GET_CONTACT, label="Get Contact"),
                    PropertyOption(
                        value=OP_ADD_CONTACT_TO_LIST, label="Add Contact to List",
                    ),
                    PropertyOption(value=OP_GET_ACCOUNT, label="Get Account"),
                ],
            ),
            PropertySchema(
                name="sender",
                display_name="Sender",
                type="json",
                description="Email string or {email, name} object.",
                display_options=DisplayOptions(show={"operation": [OP_SEND_EMAIL]}),
            ),
            PropertySchema(
                name="to",
                display_name="To",
                type="json",
                description="Recipient(s) — CSV string, list, or objects.",
                display_options=DisplayOptions(show={"operation": [OP_SEND_EMAIL]}),
            ),
            PropertySchema(
                name="cc",
                display_name="CC",
                type="json",
                display_options=DisplayOptions(show={"operation": [OP_SEND_EMAIL]}),
            ),
            PropertySchema(
                name="bcc",
                display_name="BCC",
                type="json",
                display_options=DisplayOptions(show={"operation": [OP_SEND_EMAIL]}),
            ),
            PropertySchema(
                name="reply_to",
                display_name="Reply To",
                type="json",
                display_options=DisplayOptions(show={"operation": [OP_SEND_EMAIL]}),
            ),
            PropertySchema(
                name="subject",
                display_name="Subject",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_SEND_EMAIL]}),
            ),
            PropertySchema(
                name="html_content",
                display_name="HTML Content",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_SEND_EMAIL]}),
            ),
            PropertySchema(
                name="text_content",
                display_name="Text Content",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_SEND_EMAIL]}),
            ),
            PropertySchema(
                name="tags",
                display_name="Tags",
                type="string",
                description="Comma-separated list of tracking tags.",
                display_options=DisplayOptions(show={"operation": [OP_SEND_EMAIL]}),
            ),
            PropertySchema(
                name="email",
                display_name="Contact Email",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_EMAIL_ID_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="attributes",
                display_name="Attributes",
                type="json",
                display_options=DisplayOptions(
                    show={"operation": list(_ATTRIBUTES_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="list_ids",
                display_name="List IDs",
                type="string",
                description="Comma-separated list IDs.",
                display_options=DisplayOptions(
                    show={"operation": list(_ATTRIBUTES_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="unlink_list_ids",
                display_name="Unlink List IDs",
                type="string",
                description="Comma-separated list IDs to remove.",
                display_options=DisplayOptions(show={"operation": [OP_UPDATE_CONTACT]}),
            ),
            PropertySchema(
                name="update_enabled",
                display_name="Update If Exists",
                type="boolean",
                default=False,
                display_options=DisplayOptions(show={"operation": [OP_CREATE_CONTACT]}),
            ),
            PropertySchema(
                name="list_id",
                display_name="List ID",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": [OP_ADD_CONTACT_TO_LIST]},
                ),
            ),
            PropertySchema(
                name="emails",
                display_name="Emails",
                type="string",
                description="Comma-separated list of contact emails.",
                display_options=DisplayOptions(
                    show={"operation": [OP_ADD_CONTACT_TO_LIST]},
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Brevo REST call per input item."""
        key = await _resolve_credentials(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=API_BASE_URL, timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(
                        ctx, item, client=client, key=key, logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> str:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Brevo: a brevo_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    key = str(payload.get("api_key") or "").strip()
    if not key:
        msg = "Brevo: credential has an empty 'api_key'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return key


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    key: str,
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_SEND_EMAIL).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Brevo: unsupported operation {operation!r}"
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
                "api-key": key,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
    except httpx.HTTPError as exc:
        logger.error("brevo.request_failed", operation=operation, error=str(exc))
        msg = f"Brevo: network error on {operation}: {exc}"
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
            "brevo.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Brevo {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("brevo.ok", operation=operation, status=response.status_code)
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
            code = payload.get("code")
            return f"{code}: {message}" if code else message
        code = payload.get("code")
        if isinstance(code, str) and code:
            return code
    return f"HTTP {status_code}"
