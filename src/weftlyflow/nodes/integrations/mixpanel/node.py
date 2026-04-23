"""Mixpanel node — track, engage, groups, and import via the HTTP API.

Dispatches against ``https://api.mixpanel.com``. Authentication mode
depends on the operation:

* **Ingestion** (``track_event``, ``engage_user``, ``update_group``)
  carries the event payload as ``?data=<base64(JSON)>`` on a bodyless
  POST. The project_token is merged into each event *before* encoding
  so a single credential row serves all ingestion paths; the
  :class:`~weftlyflow.credentials.types.mixpanel_api.MixpanelApiCredential`
  ``inject`` is intentionally a no-op.
* **``import_events``** POSTs a real JSON-array body to ``/import``
  and authenticates via HTTP Basic with the ``api_secret`` as the
  username and an empty password (the Mixpanel service-account
  convention).

Parameters (all expression-capable):

* ``operation`` — one of four.
* ``distinct_id`` — required for track/engage.
* ``event`` — required for ``track_event``.
* ``properties`` — optional map; merged with ``token``/``distinct_id``.
* ``set_verb`` — ``$set``/``$set_once``/``$add``/etc. for engage/group.
* ``group_key`` / ``group_id`` — required for ``update_group``.
* ``events`` — required list for ``import_events``.
* ``project_id`` — optional ``projectId`` query param on ``/import``.

Output: one item per input item with ``operation``, ``status``, and
the parsed ``response`` (``"1"``/``"0"`` text for ingestion, JSON for
``/import``).
"""

from __future__ import annotations

import base64
import json
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
from weftlyflow.nodes.integrations.mixpanel.constants import (
    API_BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    OP_ENGAGE_USER,
    OP_IMPORT_EVENTS,
    OP_TRACK_EVENT,
    OP_UPDATE_GROUP,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.mixpanel.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "mixpanel_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.mixpanel_api",)
_INGESTION_OPERATIONS: frozenset[str] = frozenset(
    {OP_TRACK_EVENT, OP_ENGAGE_USER, OP_UPDATE_GROUP},
)

log = structlog.get_logger(__name__)


class MixpanelNode(BaseNode):
    """Dispatch a single Mixpanel HTTP API call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.mixpanel",
        version=1,
        display_name="Mixpanel",
        description="Track events, update profiles/groups, and bulk-import via Mixpanel.",
        icon="icons/mixpanel.svg",
        category=NodeCategory.INTEGRATION,
        group=["analytics"],
        documentation_url="https://developer.mixpanel.com/reference/overview",
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
                default=OP_TRACK_EVENT,
                required=True,
                options=[
                    PropertyOption(value=OP_TRACK_EVENT, label="Track Event"),
                    PropertyOption(value=OP_ENGAGE_USER, label="Update User Profile"),
                    PropertyOption(value=OP_UPDATE_GROUP, label="Update Group"),
                    PropertyOption(value=OP_IMPORT_EVENTS, label="Import Events"),
                ],
            ),
            PropertySchema(
                name="distinct_id",
                display_name="Distinct ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_TRACK_EVENT, OP_ENGAGE_USER]},
                ),
            ),
            PropertySchema(
                name="event",
                display_name="Event Name",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_TRACK_EVENT]}),
            ),
            PropertySchema(
                name="properties",
                display_name="Properties",
                type="json",
                display_options=DisplayOptions(
                    show={
                        "operation": [
                            OP_TRACK_EVENT, OP_ENGAGE_USER, OP_UPDATE_GROUP,
                        ],
                    },
                ),
            ),
            PropertySchema(
                name="set_verb",
                display_name="Set Verb",
                type="options",
                default="$set",
                options=[
                    PropertyOption(value="$set", label="$set"),
                    PropertyOption(value="$set_once", label="$set_once"),
                    PropertyOption(value="$add", label="$add"),
                    PropertyOption(value="$append", label="$append"),
                    PropertyOption(value="$union", label="$union"),
                    PropertyOption(value="$remove", label="$remove"),
                    PropertyOption(value="$unset", label="$unset"),
                ],
                display_options=DisplayOptions(
                    show={"operation": [OP_ENGAGE_USER, OP_UPDATE_GROUP]},
                ),
            ),
            PropertySchema(
                name="group_key",
                display_name="Group Key",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_UPDATE_GROUP]}),
            ),
            PropertySchema(
                name="group_id",
                display_name="Group ID",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_UPDATE_GROUP]}),
            ),
            PropertySchema(
                name="events",
                display_name="Events (array)",
                type="json",
                description="Array of {event, properties} for bulk /import.",
                display_options=DisplayOptions(show={"operation": [OP_IMPORT_EVENTS]}),
            ),
            PropertySchema(
                name="project_id",
                display_name="Project ID",
                type="string",
                description="Required on newer /import variants.",
                display_options=DisplayOptions(show={"operation": [OP_IMPORT_EVENTS]}),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Mixpanel call per input item."""
        payload = await _resolve_credentials(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=API_BASE_URL, timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(
                        ctx, item, client=client, creds=payload, logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> dict[str, Any]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Mixpanel: a mixpanel_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _injector, payload = credential
    if not str(payload.get("project_token") or "").strip():
        msg = "Mixpanel: credential has an empty 'project_token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return payload


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    creds: dict[str, Any],
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_TRACK_EVENT).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Mixpanel: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    token = str(creds.get("project_token") or "").strip()
    try:
        method, path, body, query = build_request(
            operation, params, project_token=token,
        )
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    if operation in _INGESTION_OPERATIONS:
        request = _build_ingestion_request(
            client, method=method, path=path, body=body, query=query,
        )
    else:
        request = _build_import_request(
            client,
            method=method,
            path=path,
            body=body,
            query=query,
            api_secret=str(creds.get("api_secret") or "").strip(),
            ctx=ctx,
        )
    try:
        response = await client.send(request)
    except httpx.HTTPError as exc:
        logger.error("mixpanel.request_failed", operation=operation, error=str(exc))
        msg = f"Mixpanel: network error on {operation}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    parsed = _parse_response(response, operation)
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "response": parsed,
    }
    if not _is_success(response, operation, parsed):
        error = _error_message(parsed, response.status_code)
        logger.warning(
            "mixpanel.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Mixpanel {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("mixpanel.ok", operation=operation, status=response.status_code)
    return Item(json=result)


def _build_ingestion_request(
    client: httpx.AsyncClient,
    *,
    method: str,
    path: str,
    body: Any,
    query: dict[str, Any],
) -> httpx.Request:
    encoded = base64.b64encode(
        json.dumps(body, separators=(",", ":")).encode("utf-8"),
    ).decode("ascii")
    params = dict(query)
    params["data"] = encoded
    return client.build_request(
        method, path, params=params,
        headers={"Accept": "text/plain"},
    )


def _build_import_request(
    client: httpx.AsyncClient,
    *,
    method: str,
    path: str,
    body: Any,
    query: dict[str, Any],
    api_secret: str,
    ctx: ExecutionContext,
) -> httpx.Request:
    if not api_secret:
        msg = "Mixpanel: 'api_secret' is required for import_events"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    encoded = base64.b64encode(f"{api_secret}:".encode()).decode("ascii")
    return client.build_request(
        method, path, params=query or None, json=body,
        headers={
            "Authorization": f"Basic {encoded}",
            "Accept": "application/json",
        },
    )


def _parse_response(response: httpx.Response, operation: str) -> Any:
    if operation in _INGESTION_OPERATIONS:
        return response.text.strip()
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text, "status_code": response.status_code}


def _is_success(response: httpx.Response, operation: str, parsed: Any) -> bool:
    if response.status_code >= httpx.codes.BAD_REQUEST:
        return False
    if operation in _INGESTION_OPERATIONS:
        return bool(parsed == "1")
    return True


def _error_message(parsed: Any, status_code: int) -> str:
    if isinstance(parsed, str) and parsed:
        return f"mixpanel returned {parsed!r}"
    if isinstance(parsed, dict):
        for key in ("error", "message"):
            value = parsed.get(key)
            if isinstance(value, str) and value:
                return value
    return f"HTTP {status_code}"
