"""Apple App Store Connect node — apps, builds, beta testers.

Dispatches against ``api.appstoreconnect.apple.com``. Authentication
is per-request ES256 JWT signing driven by
:class:`~weftlyflow.credentials.types.asc_api.AscApiCredential` — the
credential mints a fresh JWT with a 20-minute lifetime on every call.

Parameters (all expression-capable):

* ``operation`` — ``list_apps`` / ``get_app`` / ``list_builds`` /
  ``list_beta_testers``.
* ``app_id``    — required for ``get_app``; optional filter for
  ``list_builds``.
* ``limit``     — optional page size (1..200).

Output: one item per input item with ``operation``, ``status``, and
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
from weftlyflow.nodes.integrations.asc.constants import (
    API_BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    OP_GET_APP,
    OP_LIST_APPS,
    OP_LIST_BETA_TESTERS,
    OP_LIST_BUILDS,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.asc.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "asc_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.asc_api",)

log = structlog.get_logger(__name__)


class AscNode(BaseNode):
    """Dispatch a single App Store Connect REST call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.asc",
        version=1,
        display_name="Apple App Store Connect",
        description="Apps, builds, and beta-tester reads on App Store Connect.",
        icon="icons/asc.svg",
        category=NodeCategory.INTEGRATION,
        group=["developer", "mobile"],
        documentation_url="https://developer.apple.com/documentation/appstoreconnectapi",
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
                default=OP_LIST_APPS,
                required=True,
                options=[
                    PropertyOption(value=OP_LIST_APPS, label="List Apps"),
                    PropertyOption(value=OP_GET_APP, label="Get App"),
                    PropertyOption(value=OP_LIST_BUILDS, label="List Builds"),
                    PropertyOption(value=OP_LIST_BETA_TESTERS, label="List Beta Testers"),
                ],
            ),
            PropertySchema(
                name="app_id",
                display_name="App ID",
                type="string",
                description="Required for Get App; optional filter for List Builds.",
                display_options=DisplayOptions(
                    show={"operation": [OP_GET_APP, OP_LIST_BUILDS]},
                ),
            ),
            PropertySchema(
                name="limit",
                display_name="Limit",
                type="number",
                description="Page size (1..200).",
                display_options=DisplayOptions(
                    show={
                        "operation": [
                            OP_LIST_APPS,
                            OP_LIST_BUILDS,
                            OP_LIST_BETA_TESTERS,
                        ],
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
        """Issue one App Store Connect call per input item."""
        injector, payload = await _resolve_credentials(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=API_BASE_URL, timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(
                        ctx, item, client=client, injector=injector,
                        creds=payload, logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> tuple[Any, dict[str, Any]]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "ASC: an asc_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    injector, payload = credential
    for key in ("issuer_id", "key_id", "private_key"):
        if not str(payload.get(key) or "").strip():
            msg = f"ASC: credential has an empty {key!r}"
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
    operation = str(params.get("operation") or OP_LIST_APPS).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"ASC: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, query = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    request = client.build_request(
        method, path, params=query or None, headers={"Accept": "application/json"},
    )
    request = await injector.inject(creds, request)
    try:
        response = await client.send(request)
    except httpx.HTTPError as exc:
        logger.error("asc.request_failed", operation=operation, error=str(exc))
        msg = f"ASC: network error on {operation}: {exc}"
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
            "asc.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"ASC {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("asc.ok", operation=operation, status=response.status_code)
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
        errors = parsed.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0]
            if isinstance(first, dict):
                for key in ("detail", "title", "code"):
                    value = first.get(key)
                    if isinstance(value, str) and value:
                        return value
        for key in ("message", "error"):
            value = parsed.get(key)
            if isinstance(value, str) and value:
                return value
    return f"HTTP {status_code}"
