"""Gmail node — send, list, read, trash, label messages via the Gmail API.

Dispatches to ``https://gmail.googleapis.com/gmail/v1/users/me`` with
``Authorization: Bearer <access_token>`` supplied by
:class:`~weftlyflow.credentials.types.gmail_oauth2.GmailOAuth2Credential`.

Distinctive Gmail semantics:

* **``send_message``** body is ``{"raw": "<base64url(RFC2822 MIME)>"}``.
  The node either accepts a pre-built ``raw`` string or builds the MIME
  on the fly from ``to``/``subject``/``body``/``cc``/``bcc`` fields and
  base64url-encodes the whole envelope.
* **``add_label``** POSTs to the ``/modify`` sub-resource so a single
  call can add and/or remove label IDs atomically.

Parameters (all expression-capable):

* ``operation`` — ``send_message``, ``list_messages``, ``get_message``,
  ``trash_message``, ``add_label``.
* ``to`` / ``subject`` / ``body`` / ``cc`` / ``bcc`` / ``from`` — compose.
* ``raw`` — pre-built base64url MIME (bypasses the composer).
* ``thread_id`` — reply within a thread on send.
* ``message_id`` — target for single-message operations.
* ``q`` / ``labelIds`` / ``maxResults`` / ``pageToken`` / ``includeSpamTrash`` — list filters.
* ``format`` — message projection on get (``full``, ``metadata``, ``minimal``, ``raw``).
* ``add_label_ids`` / ``remove_label_ids`` — label modifications.

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
from weftlyflow.nodes.integrations.gmail.constants import (
    DEFAULT_TIMEOUT_SECONDS,
    GMAIL_API_BASE,
    OP_ADD_LABEL,
    OP_GET_MESSAGE,
    OP_LIST_MESSAGES,
    OP_SEND_MESSAGE,
    OP_TRASH_MESSAGE,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.gmail.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "gmail_oauth2"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.gmail_oauth2",)
_SEND_OPERATIONS: frozenset[str] = frozenset({OP_SEND_MESSAGE})
_MESSAGE_OPERATIONS: frozenset[str] = frozenset(
    {OP_GET_MESSAGE, OP_TRASH_MESSAGE, OP_ADD_LABEL},
)
_LIST_OPERATIONS: frozenset[str] = frozenset({OP_LIST_MESSAGES})

log = structlog.get_logger(__name__)


class GmailNode(BaseNode):
    """Dispatch a single Gmail API call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.gmail",
        version=1,
        display_name="Gmail",
        description="Send, list, read, trash, and label messages via the Gmail API.",
        icon="icons/gmail.svg",
        category=NodeCategory.INTEGRATION,
        group=["communication", "email"],
        documentation_url="https://developers.google.com/gmail/api/reference/rest",
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
                default=OP_SEND_MESSAGE,
                required=True,
                options=[
                    PropertyOption(value=OP_SEND_MESSAGE, label="Send Message"),
                    PropertyOption(value=OP_LIST_MESSAGES, label="List Messages"),
                    PropertyOption(value=OP_GET_MESSAGE, label="Get Message"),
                    PropertyOption(value=OP_TRASH_MESSAGE, label="Trash Message"),
                    PropertyOption(value=OP_ADD_LABEL, label="Modify Labels"),
                ],
            ),
            PropertySchema(
                name="to",
                display_name="To",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_SEND_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="subject",
                display_name="Subject",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_SEND_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="body",
                display_name="Body (plain text)",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_SEND_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="cc",
                display_name="Cc",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_SEND_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="bcc",
                display_name="Bcc",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_SEND_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="from",
                display_name="From (alias)",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_SEND_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="raw",
                display_name="Raw base64url MIME",
                type="string",
                description="If set, bypasses the composer and sends this verbatim.",
                display_options=DisplayOptions(
                    show={"operation": list(_SEND_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="thread_id",
                display_name="Thread ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_SEND_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="message_id",
                display_name="Message ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_MESSAGE_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="q",
                display_name="Search Query (Gmail syntax)",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_LIST_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="labelIds",
                display_name="Label IDs Filter",
                type="json",
                description="Array of label IDs to filter by.",
                display_options=DisplayOptions(
                    show={"operation": list(_LIST_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="maxResults",
                display_name="Max Results",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": list(_LIST_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="pageToken",
                display_name="Page Token",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_LIST_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="includeSpamTrash",
                display_name="Include Spam/Trash",
                type="boolean",
                default=False,
                display_options=DisplayOptions(
                    show={"operation": list(_LIST_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="format",
                display_name="Message Format",
                type="options",
                options=[
                    PropertyOption(value="full", label="Full"),
                    PropertyOption(value="metadata", label="Metadata"),
                    PropertyOption(value="minimal", label="Minimal"),
                    PropertyOption(value="raw", label="Raw"),
                ],
                display_options=DisplayOptions(
                    show={"operation": [OP_GET_MESSAGE]},
                ),
            ),
            PropertySchema(
                name="add_label_ids",
                display_name="Add Label IDs",
                type="json",
                description="Array of label IDs to attach.",
                display_options=DisplayOptions(
                    show={"operation": [OP_ADD_LABEL]},
                ),
            ),
            PropertySchema(
                name="remove_label_ids",
                display_name="Remove Label IDs",
                type="json",
                description="Array of label IDs to detach.",
                display_options=DisplayOptions(
                    show={"operation": [OP_ADD_LABEL]},
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Gmail API call per input item."""
        injector, payload = await _resolve_credentials(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=GMAIL_API_BASE, timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(
                        ctx,
                        item,
                        client=client,
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
        msg = "Gmail: a gmail_oauth2 credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    injector, payload = credential
    if not str(payload.get("access_token") or "").strip():
        msg = "Gmail: credential has an empty 'access_token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return injector, payload


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    injector: Any,
    creds: dict[str, Any],
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_SEND_MESSAGE).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Gmail: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, body, query = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    request_headers: dict[str, str] = {"Accept": "application/json"}
    if body is not None:
        request_headers["Content-Type"] = "application/json"
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
        logger.error("gmail.request_failed", operation=operation, error=str(exc))
        msg = f"Gmail: network error on {operation}: {exc}"
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
            "gmail.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Gmail {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("gmail.ok", operation=operation, status=response.status_code)
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
            message = error.get("message")
            if isinstance(message, str) and message:
                return message
        if isinstance(error, str) and error:
            return error
    return f"HTTP {status_code}"
