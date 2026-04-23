"""Mapbox node — geocoding, directions, matrix, and isochrone dispatchers.

Dispatches to ``https://api.mapbox.com`` with the distinctive
``?access_token=<token>`` query-param auth (no ``Authorization`` header
is accepted). Auth is handled by the credential
:class:`~weftlyflow.credentials.types.mapbox_api.MapboxApiCredential`
which mutates the outgoing URL's query string.

Parameters (all expression-capable):

* ``operation`` — ``forward_geocode``, ``reverse_geocode``,
  ``directions``, ``matrix``, ``isochrone``.
* ``search_text`` — place query for forward geocoding.
* ``longitude`` / ``latitude`` — inputs for reverse geocoding.
* ``coordinates`` — ``lon,lat;lon,lat;...`` for routing operations.
* ``profile`` — routing profile (default ``mapbox/driving``).
* ``contours_minutes`` / ``contours_meters`` — isochrone inputs.

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
from weftlyflow.nodes.integrations.mapbox.constants import (
    DEFAULT_DIRECTIONS_PROFILE,
    DEFAULT_GEOCODING_ENDPOINT,
    DEFAULT_TIMEOUT_SECONDS,
    OP_DIRECTIONS,
    OP_FORWARD_GEOCODE,
    OP_ISOCHRONE,
    OP_MATRIX,
    OP_REVERSE_GEOCODE,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.mapbox.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_API_HOST: str = "https://api.mapbox.com"
_CREDENTIAL_SLOT: str = "mapbox_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.mapbox_api",)
_GEOCODING_OPERATIONS: frozenset[str] = frozenset(
    {OP_FORWARD_GEOCODE, OP_REVERSE_GEOCODE},
)
_ROUTING_OPERATIONS: frozenset[str] = frozenset(
    {OP_DIRECTIONS, OP_MATRIX, OP_ISOCHRONE},
)

log = structlog.get_logger(__name__)


class MapboxNode(BaseNode):
    """Dispatch a single Mapbox API call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.mapbox",
        version=1,
        display_name="Mapbox",
        description="Call Mapbox geocoding, directions, matrix, and isochrone APIs.",
        icon="icons/mapbox.svg",
        category=NodeCategory.INTEGRATION,
        group=["geo", "maps"],
        documentation_url="https://docs.mapbox.com/api/overview/",
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
                default=OP_FORWARD_GEOCODE,
                required=True,
                options=[
                    PropertyOption(value=OP_FORWARD_GEOCODE, label="Forward Geocode"),
                    PropertyOption(value=OP_REVERSE_GEOCODE, label="Reverse Geocode"),
                    PropertyOption(value=OP_DIRECTIONS, label="Directions"),
                    PropertyOption(value=OP_MATRIX, label="Matrix"),
                    PropertyOption(value=OP_ISOCHRONE, label="Isochrone"),
                ],
            ),
            PropertySchema(
                name="endpoint",
                display_name="Geocoding Endpoint",
                type="string",
                default=DEFAULT_GEOCODING_ENDPOINT,
                display_options=DisplayOptions(
                    show={"operation": list(_GEOCODING_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="search_text",
                display_name="Search Text",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_FORWARD_GEOCODE]},
                ),
            ),
            PropertySchema(
                name="longitude",
                display_name="Longitude",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_REVERSE_GEOCODE]},
                ),
            ),
            PropertySchema(
                name="latitude",
                display_name="Latitude",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_REVERSE_GEOCODE]},
                ),
            ),
            PropertySchema(
                name="profile",
                display_name="Routing Profile",
                type="string",
                default=DEFAULT_DIRECTIONS_PROFILE,
                display_options=DisplayOptions(
                    show={"operation": list(_ROUTING_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="coordinates",
                display_name="Coordinates",
                type="string",
                description="`lon,lat;lon,lat;...` (semicolon separated).",
                display_options=DisplayOptions(
                    show={"operation": list(_ROUTING_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="contours_minutes",
                display_name="Contours (minutes)",
                type="string",
                description="Comma-separated isochrone intervals in minutes.",
                display_options=DisplayOptions(
                    show={"operation": [OP_ISOCHRONE]},
                ),
            ),
            PropertySchema(
                name="contours_meters",
                display_name="Contours (meters)",
                type="string",
                description="Comma-separated isochrone intervals in meters.",
                display_options=DisplayOptions(
                    show={"operation": [OP_ISOCHRONE]},
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Mapbox API call per input item."""
        injector, payload = await _resolve_credentials(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=_API_HOST, timeout=DEFAULT_TIMEOUT_SECONDS,
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
        msg = "Mapbox: a mapbox_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    injector, payload = credential
    token = str(payload.get("access_token") or "").strip()
    if not token:
        msg = "Mapbox: credential has an empty 'access_token'"
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
    operation = str(params.get("operation") or OP_FORWARD_GEOCODE).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Mapbox: unsupported operation {operation!r}"
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
        logger.error("mapbox.request_failed", operation=operation, error=str(exc))
        msg = f"Mapbox: network error on {operation}: {exc}"
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
            "mapbox.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Mapbox {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("mapbox.ok", operation=operation, status=response.status_code)
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
            return message
        error = payload.get("error")
        if isinstance(error, str) and error:
            return error
    return f"HTTP {status_code}"
