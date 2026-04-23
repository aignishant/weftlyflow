"""Google Cloud Storage node — buckets and objects via JSON API.

Dispatches against ``storage.googleapis.com`` after exchanging the
service-account JWT for a Bearer. The token is fetched exactly once
per execution and threaded through the dispatch loop because Google's
tokens live one hour — re-signing per item would waste CPU.

Parameters (all expression-capable):

* ``operation``   — ``list_buckets`` / ``list_objects`` /
  ``get_object`` / ``delete_object``.
* ``project``     — GCP project ID (required for list_buckets).
* ``bucket``      — bucket name (required for object operations).
* ``object_name`` — object path (required for get_object /
  delete_object). Forward slashes are preserved by GCS but the
  node URL-quotes them to survive the JSON API path format.
* ``prefix`` / ``delimiter`` / ``page_token`` — listing pagination.
* ``alt``         — ``json`` (default) or ``media`` for raw content.

Output: one item per input item with ``operation``, ``status``, and
parsed ``response``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import structlog

from weftlyflow.credentials.types.gcp_service_account import (
    fetch_access_token,
    token_host,
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
from weftlyflow.nodes.integrations.gcs.constants import (
    API_HOST,
    DEFAULT_TIMEOUT_SECONDS,
    OP_DELETE_OBJECT,
    OP_GET_OBJECT,
    OP_LIST_BUCKETS,
    OP_LIST_OBJECTS,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.gcs.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "gcp_service_account"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.gcp_service_account",)

log = structlog.get_logger(__name__)


class GcsNode(BaseNode):
    """Dispatch a single Google Cloud Storage REST call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.gcs",
        version=1,
        display_name="Google Cloud Storage",
        description="Buckets and objects on Google Cloud Storage.",
        icon="icons/gcs.svg",
        category=NodeCategory.INTEGRATION,
        group=["storage"],
        documentation_url="https://cloud.google.com/storage/docs/json_api",
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
                    PropertyOption(value=OP_GET_OBJECT, label="Get Object Metadata"),
                    PropertyOption(value=OP_DELETE_OBJECT, label="Delete Object"),
                ],
            ),
            PropertySchema(
                name="project",
                display_name="Project ID",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_LIST_BUCKETS]}),
            ),
            PropertySchema(
                name="bucket",
                display_name="Bucket",
                type="string",
                display_options=DisplayOptions(
                    show={
                        "operation": [
                            OP_LIST_OBJECTS,
                            OP_GET_OBJECT,
                            OP_DELETE_OBJECT,
                        ],
                    },
                ),
            ),
            PropertySchema(
                name="object_name",
                display_name="Object Name",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_GET_OBJECT, OP_DELETE_OBJECT]},
                ),
            ),
            PropertySchema(
                name="prefix",
                display_name="Prefix",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_BUCKETS, OP_LIST_OBJECTS]},
                ),
            ),
            PropertySchema(
                name="delimiter",
                display_name="Delimiter",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_LIST_OBJECTS]}),
            ),
            PropertySchema(
                name="page_token",
                display_name="Page Token",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_BUCKETS, OP_LIST_OBJECTS]},
                ),
            ),
            PropertySchema(
                name="alt",
                display_name="Alt",
                type="string",
                description='Set to "media" to return raw object bytes.',
                display_options=DisplayOptions(show={"operation": [OP_GET_OBJECT]}),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Fetch one Bearer, then issue one GCS call per input item."""
        injector, payload = await _resolve_credentials(ctx)
        del injector  # service-account grant — token is fetched explicitly.
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        token = await _fetch_token(ctx, payload, logger=bound)
        seed = items or [Item()]
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=API_HOST, timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(
                        ctx, item, client=client, token=token, logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> tuple[Any, dict[str, Any]]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "GCS: a gcp_service_account credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    injector, payload = credential
    for key in ("client_email", "private_key"):
        if not str(payload.get(key) or "").strip():
            msg = f"GCS: credential has an empty {key!r}"
            raise NodeExecutionError(msg, node_id=ctx.node.id)
    return injector, payload


async def _fetch_token(
    ctx: ExecutionContext, creds: dict[str, Any], *, logger: Any,
) -> str:
    try:
        async with httpx.AsyncClient(
            base_url=token_host(), timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as oauth_client:
            token = await fetch_access_token(oauth_client, creds)
    except (httpx.HTTPError, ValueError) as exc:
        logger.error("gcs.token_failed", error=str(exc))
        msg = f"GCS: failed to obtain access token: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    return token


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    token: str,
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_LIST_OBJECTS).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"GCS: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, query = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    request = client.build_request(
        method, path,
        params=query or None,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
    )
    try:
        response = await client.send(request)
    except httpx.HTTPError as exc:
        logger.error("gcs.request_failed", operation=operation, error=str(exc))
        msg = f"GCS: network error on {operation}: {exc}"
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
            "gcs.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"GCS {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("gcs.ok", operation=operation, status=response.status_code)
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
        error = parsed.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message:
                return message
        for key in ("message", "error_description"):
            value = parsed.get(key)
            if isinstance(value, str) and value:
                return value
    return f"HTTP {status_code}"
