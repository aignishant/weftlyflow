"""Backblaze B2 node — bucket/file ops against the Native API.

Unique among storage nodes in the catalog: B2 requires a
``b2_authorize_account`` exchange before any other call to discover
the per-tenant ``apiUrl``. The node performs that exchange exactly
once per execution, caches the resulting :class:`B2Session`, and
threads the Bearer + ``apiUrl`` into each dispatched request.

Parameters (all expression-capable):

* ``operation``        — ``list_buckets`` / ``list_file_names`` /
  ``get_upload_url`` / ``delete_file_version``.
* ``bucket_id``        — B2 bucket ID (required for object ops).
* ``bucket``           — bucket name filter for ``list_buckets``.
* ``prefix`` / ``start_file_name`` / ``delimiter`` / ``max_file_count``
  — ``list_file_names`` paging.
* ``file_id`` / ``file_name`` — target for ``delete_file_version``.

Output: one item per input item with ``operation``, ``status``, and
the parsed ``response`` JSON.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import structlog

from weftlyflow.credentials.types.backblaze_b2 import (
    B2Session,
    authorize_host,
    fetch_session,
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
from weftlyflow.nodes.integrations.backblaze_b2.constants import (
    DEFAULT_TIMEOUT_SECONDS,
    OP_DELETE_FILE_VERSION,
    OP_GET_UPLOAD_URL,
    OP_LIST_BUCKETS,
    OP_LIST_FILE_NAMES,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.backblaze_b2.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "backblaze_b2"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.backblaze_b2",)
_BUCKET_OPERATIONS: frozenset[str] = frozenset(
    {OP_LIST_FILE_NAMES, OP_GET_UPLOAD_URL},
)
_FILE_OPERATIONS: frozenset[str] = frozenset({OP_DELETE_FILE_VERSION})

log = structlog.get_logger(__name__)


class BackblazeB2Node(BaseNode):
    """Dispatch a single B2 Native API call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.backblaze_b2",
        version=1,
        display_name="Backblaze B2",
        description="Buckets and files on Backblaze B2 Native.",
        icon="icons/backblaze.svg",
        category=NodeCategory.INTEGRATION,
        group=["storage"],
        documentation_url="https://www.backblaze.com/apidocs",
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
                default=OP_LIST_BUCKETS,
                required=True,
                options=[
                    PropertyOption(value=OP_LIST_BUCKETS, label="List Buckets"),
                    PropertyOption(
                        value=OP_LIST_FILE_NAMES, label="List File Names",
                    ),
                    PropertyOption(value=OP_GET_UPLOAD_URL, label="Get Upload URL"),
                    PropertyOption(
                        value=OP_DELETE_FILE_VERSION, label="Delete File Version",
                    ),
                ],
            ),
            PropertySchema(
                name="bucket",
                display_name="Bucket Name",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_LIST_BUCKETS]}),
                description="Filter list_buckets to a single bucket name.",
            ),
            PropertySchema(
                name="bucket_id",
                display_name="Bucket ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_BUCKET_OPERATIONS | {OP_LIST_BUCKETS})},
                ),
            ),
            PropertySchema(
                name="prefix",
                display_name="Prefix",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_FILE_NAMES]},
                ),
            ),
            PropertySchema(
                name="delimiter",
                display_name="Delimiter",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_FILE_NAMES]},
                ),
            ),
            PropertySchema(
                name="start_file_name",
                display_name="Start File Name",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_FILE_NAMES]},
                ),
            ),
            PropertySchema(
                name="max_file_count",
                display_name="Max File Count",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_FILE_NAMES]},
                ),
            ),
            PropertySchema(
                name="file_id",
                display_name="File ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_FILE_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="file_name",
                display_name="File Name",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_FILE_OPERATIONS)},
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Authorize once, then issue one B2 call per input item."""
        creds = await _resolve_credentials(ctx)
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        session = await _authorize(ctx, creds, logger=bound)
        seed = items or [Item()]
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=session.api_url, timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(
                        ctx, item, client=client, session=session, logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> dict[str, Any]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Backblaze B2: a backblaze_b2 credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    for key in ("key_id", "application_key"):
        if not str(payload.get(key) or "").strip():
            msg = f"Backblaze B2: credential has an empty {key!r}"
            raise NodeExecutionError(msg, node_id=ctx.node.id)
    return payload


async def _authorize(
    ctx: ExecutionContext, creds: dict[str, Any], *, logger: Any,
) -> B2Session:
    try:
        async with httpx.AsyncClient(
            base_url=authorize_host(), timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            return await fetch_session(client, creds)
    except (httpx.HTTPError, ValueError) as exc:
        logger.error("backblaze_b2.authorize_failed", error=str(exc))
        msg = f"Backblaze B2: authorize failed: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    session: B2Session,
    logger: Any,
) -> Item:
    params = dict(ctx.resolved_params(item=item))
    operation = str(params.get("operation") or OP_LIST_BUCKETS).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Backblaze B2: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    if operation == OP_LIST_BUCKETS:
        params.setdefault("account_id", session.account_id)
    try:
        path, body = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    try:
        response = await client.post(
            path,
            headers={
                "Authorization": session.authorization_token,
                "Accept": "application/json",
            },
            json=body,
        )
    except httpx.HTTPError as exc:
        logger.error(
            "backblaze_b2.request_failed", operation=operation, error=str(exc),
        )
        msg = f"Backblaze B2: network error on {operation}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    parsed = _safe_json(response)
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "response": parsed,
    }
    if response.status_code >= httpx.codes.BAD_REQUEST:
        error = _error_message(parsed, response.status_code)
        logger.warning(
            "backblaze_b2.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = (
            f"Backblaze B2 {operation} failed (HTTP {response.status_code}): {error}"
        )
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("backblaze_b2.ok", operation=operation, status=response.status_code)
    return Item(json=result)


def _safe_json(response: httpx.Response) -> Any:
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text, "status_code": response.status_code}


def _error_message(parsed: Any, status_code: int) -> str:
    if isinstance(parsed, dict):
        for key in ("message", "code"):
            value = parsed.get(key)
            if isinstance(value, str) and value:
                return value
    return f"HTTP {status_code}"
