"""Klaviyo node — events, profiles, list membership.

Dispatches against ``https://a.klaviyo.com`` with two headers that are
set by the :class:`~weftlyflow.credentials.types.klaviyo_api.KlaviyoApiCredential`:

* ``Authorization: Klaviyo-API-Key <api_key>`` — custom scheme name.
* ``revision: YYYY-MM-DD`` — mandatory date-versioned API contract.

Parameters (all expression-capable):

* ``operation`` — ``create_event`` / ``create_profile`` /
  ``get_profile`` / ``add_profile_to_list``.
* ``metric_name`` / ``profile`` / ``properties`` / ``value`` — event.
* ``attributes`` — profile creation payload.
* ``profile_id`` — profile read.
* ``list_id`` / ``profile_ids`` — add-to-list membership call.

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
from weftlyflow.nodes.integrations.klaviyo.constants import (
    API_BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    OP_ADD_PROFILE_TO_LIST,
    OP_CREATE_EVENT,
    OP_CREATE_PROFILE,
    OP_GET_PROFILE,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.klaviyo.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "klaviyo_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.klaviyo_api",)

log = structlog.get_logger(__name__)


class KlaviyoNode(BaseNode):
    """Dispatch a single Klaviyo API call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.klaviyo",
        version=1,
        display_name="Klaviyo",
        description="Create events, manage profiles, and update list membership in Klaviyo.",
        icon="icons/klaviyo.svg",
        category=NodeCategory.INTEGRATION,
        group=["marketing"],
        documentation_url="https://developers.klaviyo.com/en/reference/api_overview",
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
                default=OP_CREATE_EVENT,
                required=True,
                options=[
                    PropertyOption(value=OP_CREATE_EVENT, label="Create Event"),
                    PropertyOption(value=OP_CREATE_PROFILE, label="Create Profile"),
                    PropertyOption(value=OP_GET_PROFILE, label="Get Profile"),
                    PropertyOption(
                        value=OP_ADD_PROFILE_TO_LIST, label="Add Profiles to List",
                    ),
                ],
            ),
            PropertySchema(
                name="metric_name",
                display_name="Metric Name",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_EVENT]}),
            ),
            PropertySchema(
                name="profile",
                display_name="Profile Attributes",
                type="json",
                description="Profile reference attributes, e.g. {\"email\": \"a@b.c\"}.",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_EVENT]}),
            ),
            PropertySchema(
                name="properties",
                display_name="Event Properties",
                type="json",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_EVENT]}),
            ),
            PropertySchema(
                name="value",
                display_name="Event Value",
                type="number",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_EVENT]}),
            ),
            PropertySchema(
                name="attributes",
                display_name="Profile Attributes",
                type="json",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_PROFILE]}),
            ),
            PropertySchema(
                name="profile_id",
                display_name="Profile ID",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_GET_PROFILE]}),
            ),
            PropertySchema(
                name="list_id",
                display_name="List ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_ADD_PROFILE_TO_LIST]},
                ),
            ),
            PropertySchema(
                name="profile_ids",
                display_name="Profile IDs",
                type="json",
                description="Array of profile IDs to add to the list.",
                display_options=DisplayOptions(
                    show={"operation": [OP_ADD_PROFILE_TO_LIST]},
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Klaviyo call per input item."""
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
        msg = "Klaviyo: a klaviyo_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    injector, payload = credential
    if not str(payload.get("api_key") or "").strip():
        msg = "Klaviyo: credential has an empty 'api_key'"
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
    operation = str(params.get("operation") or OP_CREATE_EVENT).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Klaviyo: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, body, query = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    request = client.build_request(
        method, path, params=query or None, json=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    request = await injector.inject(creds, request)
    try:
        response = await client.send(request)
    except httpx.HTTPError as exc:
        logger.error("klaviyo.request_failed", operation=operation, error=str(exc))
        msg = f"Klaviyo: network error on {operation}: {exc}"
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
            "klaviyo.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Klaviyo {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("klaviyo.ok", operation=operation, status=response.status_code)
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
        for key in ("detail", "message"):
            value = parsed.get(key)
            if isinstance(value, str) and value:
                return value
    return f"HTTP {status_code}"
