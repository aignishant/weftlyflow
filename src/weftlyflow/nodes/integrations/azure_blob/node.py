"""Azure Blob Storage node — container/blob ops with SharedKey signing.

Like :class:`AwsS3Node` in spirit but the signature algorithm is
Microsoft's SharedKey scheme (12-slot StringToSign + canonical
``x-ms-*`` header block + canonical resource) rather than SigV4. The
credential exposes :func:`authorize_request` which mutates the
request in place to stamp ``x-ms-date``, ``x-ms-version``, and the
``Authorization: SharedKey <account>:<sig>`` header — the node just
builds the unsigned request and defers signing until dispatch time.

Parameters (all expression-capable):

* ``operation``    — ``list_containers`` / ``list_blobs`` /
  ``get_blob`` / ``put_blob`` / ``delete_blob``.
* ``container``    — container name (required for non-service ops).
* ``blob``         — blob name (required for ``get_blob`` /
  ``put_blob`` / ``delete_blob``).
* ``prefix`` / ``delimiter`` / ``marker`` — listing pagination.
* ``body`` / ``content_type`` — only read on ``put_blob``.

Output: one item per input item with ``operation``, ``status``, and
the response body under ``response.raw`` (Azure replies are XML).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import structlog

from weftlyflow.credentials.types.azure_storage_shared_key import (
    authorize_request,
    blob_host_for,
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
from weftlyflow.nodes.integrations.azure_blob.constants import (
    DEFAULT_TIMEOUT_SECONDS,
    OP_DELETE_BLOB,
    OP_GET_BLOB,
    OP_LIST_BLOBS,
    OP_LIST_CONTAINERS,
    OP_PUT_BLOB,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.azure_blob.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "azure_storage_shared_key"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.azure_storage_shared_key",)
_BLOB_OPERATIONS: frozenset[str] = frozenset(
    {OP_GET_BLOB, OP_PUT_BLOB, OP_DELETE_BLOB},
)
_CONTAINER_SCOPED: frozenset[str] = frozenset({OP_LIST_BLOBS}) | _BLOB_OPERATIONS

log = structlog.get_logger(__name__)


class AzureBlobNode(BaseNode):
    """Dispatch a single SharedKey-signed Azure Blob call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.azure_blob",
        version=1,
        display_name="Azure Blob Storage",
        description="Manage containers and blobs on Azure Storage.",
        icon="icons/azure-blob.svg",
        category=NodeCategory.INTEGRATION,
        group=["storage", "azure"],
        documentation_url=(
            "https://learn.microsoft.com/rest/api/storageservices/blob-service-rest-api"
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
                default=OP_LIST_BLOBS,
                required=True,
                options=[
                    PropertyOption(
                        value=OP_LIST_CONTAINERS, label="List Containers",
                    ),
                    PropertyOption(value=OP_LIST_BLOBS, label="List Blobs"),
                    PropertyOption(value=OP_GET_BLOB, label="Get Blob"),
                    PropertyOption(value=OP_PUT_BLOB, label="Put Blob"),
                    PropertyOption(value=OP_DELETE_BLOB, label="Delete Blob"),
                ],
            ),
            PropertySchema(
                name="container",
                display_name="Container",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_CONTAINER_SCOPED)},
                ),
            ),
            PropertySchema(
                name="blob",
                display_name="Blob Name",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_BLOB_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="body",
                display_name="Body",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_PUT_BLOB]}),
                description="Request body — strings are UTF-8 encoded.",
            ),
            PropertySchema(
                name="content_type",
                display_name="Content Type",
                type="string",
                default="application/octet-stream",
                display_options=DisplayOptions(show={"operation": [OP_PUT_BLOB]}),
            ),
            PropertySchema(
                name="prefix",
                display_name="Prefix",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_CONTAINERS, OP_LIST_BLOBS]},
                ),
            ),
            PropertySchema(
                name="delimiter",
                display_name="Delimiter",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_LIST_BLOBS]}),
            ),
            PropertySchema(
                name="marker",
                display_name="Marker",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_CONTAINERS, OP_LIST_BLOBS]},
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one SharedKey-signed Blob call per input item."""
        account_name, account_key, api_version = await _resolve_credentials(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        host = blob_host_for(account_name)
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=host, timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(
                        ctx,
                        item,
                        client=client,
                        account_name=account_name,
                        account_key=account_key,
                        api_version=api_version,
                        logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> tuple[str, str, str]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Azure Blob: an azure_storage_shared_key credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    account_name = str(payload.get("account_name") or "").strip()
    account_key = str(payload.get("account_key") or "").strip()
    if not account_name or not account_key:
        msg = "Azure Blob: credential is missing account_name or account_key"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    api_version = str(payload.get("api_version") or "").strip() or "2023-11-03"
    return account_name, account_key, api_version


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    account_name: str,
    account_key: str,
    api_version: str,
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_LIST_BLOBS).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Azure Blob: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, query, extra_headers, body = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    request = client.build_request(
        method, path,
        params=query or None,
        headers=extra_headers or None,
        content=body or None,
    )
    try:
        signed = authorize_request(
            request,
            account_name=account_name,
            account_key=account_key,
            api_version=api_version,
        )
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    try:
        response = await client.send(signed)
    except httpx.HTTPError as exc:
        logger.error("azure_blob.request_failed", operation=operation, error=str(exc))
        msg = f"Azure Blob: network error on {operation}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    parsed = _safe_body(response)
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "response": parsed,
    }
    if response.status_code >= httpx.codes.BAD_REQUEST:
        error = _error_message(response)
        logger.warning(
            "azure_blob.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = (
            f"Azure Blob {operation} failed (HTTP {response.status_code}): {error}"
        )
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("azure_blob.ok", operation=operation, status=response.status_code)
    return Item(json=result)


def _safe_body(response: httpx.Response) -> dict[str, Any]:
    if not response.content:
        return {"headers": dict(response.headers)}
    return {"raw": response.text, "headers": dict(response.headers)}


def _error_message(response: httpx.Response) -> str:
    text = response.text or ""
    lower = text.lower()
    code_start = lower.find("<code>")
    message_start = lower.find("<message>")
    if code_start >= 0 and message_start >= 0:
        code_end = lower.find("</code>", code_start)
        message_end = lower.find("</message>", message_start)
        if code_end > code_start and message_end > message_start:
            code = text[code_start + len("<Code>"):code_end]
            message = text[message_start + len("<Message>"):message_end]
            return f"{code}: {message}"
    if text:
        return text.strip().splitlines()[0][:200]
    return f"HTTP {response.status_code}"
