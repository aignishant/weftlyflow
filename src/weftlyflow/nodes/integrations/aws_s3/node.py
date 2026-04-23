"""AWS S3 node — bucket/object ops with per-request SigV4 signing.

Unlike every other integration node in the catalog, the AWS S3 node
signs each outbound request at send-time rather than leaning on a
static header the credential pre-computed. The
:func:`~weftlyflow.credentials.types.aws_s3.sign_request` helper
derives a fresh signature from the canonical HTTP method, path,
query, host, body hash, and an ISO-8601 timestamp — recomputed per
call so the signature remains valid within the AWS 15-minute skew
window.

Parameters (all expression-capable):

* ``operation`` — ``list_buckets``, ``list_objects``, ``head_object``,
  ``get_object``, ``delete_object``, ``copy_object``.
* ``bucket`` / ``key`` — target resource (virtual-host addressing).
* ``prefix`` / ``delimiter`` / ``continuation_token`` / ``max_keys``
  — list paging + filtering.
* ``source_bucket`` / ``source_key`` — copy source.

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response``. XML responses are returned as the raw body under
``response.raw`` for downstream nodes to parse (the node intentionally
avoids importing ``xml`` to keep the surface small).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import structlog

from weftlyflow.credentials.types.aws_s3 import regional_host, sign_request
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
from weftlyflow.nodes.integrations.aws_s3.constants import (
    DEFAULT_TIMEOUT_SECONDS,
    OP_COPY_OBJECT,
    OP_DELETE_OBJECT,
    OP_GET_OBJECT,
    OP_HEAD_OBJECT,
    OP_LIST_BUCKETS,
    OP_LIST_OBJECTS,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.aws_s3.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "aws_s3"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.aws_s3",)
_KEY_OPERATIONS: frozenset[str] = frozenset(
    {OP_HEAD_OBJECT, OP_GET_OBJECT, OP_DELETE_OBJECT, OP_COPY_OBJECT},
)
_BUCKET_OPERATIONS: frozenset[str] = frozenset(
    {OP_LIST_OBJECTS} | _KEY_OPERATIONS,
)

log = structlog.get_logger(__name__)


class AwsS3Node(BaseNode):
    """Dispatch a single SigV4-signed S3 call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.aws_s3",
        version=1,
        display_name="AWS S3",
        description="Manage AWS S3 buckets and objects with SigV4 signing.",
        icon="icons/aws-s3.svg",
        category=NodeCategory.INTEGRATION,
        group=["storage", "aws"],
        documentation_url=(
            "https://docs.aws.amazon.com/AmazonS3/latest/API/Welcome.html"
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
                default=OP_LIST_OBJECTS,
                required=True,
                options=[
                    PropertyOption(value=OP_LIST_BUCKETS, label="List Buckets"),
                    PropertyOption(value=OP_LIST_OBJECTS, label="List Objects"),
                    PropertyOption(value=OP_HEAD_OBJECT, label="Head Object"),
                    PropertyOption(value=OP_GET_OBJECT, label="Get Object"),
                    PropertyOption(value=OP_DELETE_OBJECT, label="Delete Object"),
                    PropertyOption(value=OP_COPY_OBJECT, label="Copy Object"),
                ],
            ),
            PropertySchema(
                name="bucket",
                display_name="Bucket",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_BUCKET_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="key",
                display_name="Object Key",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_KEY_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="prefix",
                display_name="Prefix",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_LIST_OBJECTS]}),
            ),
            PropertySchema(
                name="delimiter",
                display_name="Delimiter",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_LIST_OBJECTS]}),
            ),
            PropertySchema(
                name="continuation_token",
                display_name="Continuation Token",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_LIST_OBJECTS]}),
            ),
            PropertySchema(
                name="max_keys",
                display_name="Max Keys",
                type="number",
                display_options=DisplayOptions(show={"operation": [OP_LIST_OBJECTS]}),
            ),
            PropertySchema(
                name="source_bucket",
                display_name="Source Bucket",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_COPY_OBJECT]}),
            ),
            PropertySchema(
                name="source_key",
                display_name="Source Key",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_COPY_OBJECT]}),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one SigV4-signed S3 call per input item."""
        access_key, secret_key, region, session_token = await _resolve_credentials(ctx)
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
                        access_key=access_key,
                        secret_key=secret_key,
                        region=region,
                        session_token=session_token,
                        logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(
    ctx: ExecutionContext,
) -> tuple[str, str, str, str]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "AWS S3: an aws_s3 credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    access_key = str(payload.get("access_key_id") or "").strip()
    secret_key = str(payload.get("secret_access_key") or "").strip()
    region = str(payload.get("region") or "").strip()
    if not access_key or not secret_key:
        msg = "AWS S3: credential is missing access_key_id or secret_access_key"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    if not region:
        msg = "AWS S3: credential has an empty 'region'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    session_token = str(payload.get("session_token") or "").strip()
    return access_key, secret_key, region, session_token


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    access_key: str,
    secret_key: str,
    region: str,
    session_token: str,
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_LIST_OBJECTS).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"AWS S3: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, query, extra_headers, bucket = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    host = regional_host(region, bucket=bucket or None)
    signed_headers = sign_request(
        method=method,
        host=host,
        path=path,
        query=query,
        headers=extra_headers,
        body=b"",
        access_key_id=access_key,
        secret_access_key=secret_key,
        region=region,
        session_token=session_token,
    )
    request_headers: dict[str, str] = {
        "Host": host,
        "Accept": "application/xml",
    }
    request_headers.update(extra_headers)
    request_headers.update(signed_headers)
    url = f"https://{host}{path}"
    try:
        response = await client.request(
            method,
            url,
            params=query or None,
            headers=request_headers,
        )
    except httpx.HTTPError as exc:
        logger.error("aws_s3.request_failed", operation=operation, error=str(exc))
        msg = f"AWS S3: network error on {operation}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    payload = _safe_body(response)
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "response": payload,
    }
    if response.status_code >= httpx.codes.BAD_REQUEST:
        error = _error_message(response, payload)
        logger.warning(
            "aws_s3.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"AWS S3 {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("aws_s3.ok", operation=operation, status=response.status_code)
    return Item(json=result)


def _safe_body(response: httpx.Response) -> dict[str, Any]:
    if not response.content:
        return {"headers": dict(response.headers)}
    return {"raw": response.text, "headers": dict(response.headers)}


def _error_message(response: httpx.Response, payload: dict[str, Any]) -> str:
    del payload
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
        snippet = text.strip().splitlines()[0][:200]
        return snippet
    return f"HTTP {response.status_code}"
