"""Okta node — v1 REST API for user and group management.

Dispatches to ``<org>.okta.com/api/v1`` with the custom
``Authorization: SSWS <api_token>`` scheme sourced from
:class:`~weftlyflow.credentials.types.okta_api.OktaApiCredential`.

Parameters (all expression-capable):

* ``operation`` — ``list_users``, ``get_user``, ``create_user``,
  ``update_user``, ``deactivate_user``, ``list_groups``.
* ``user_id`` — target user (get/update/deactivate).
* ``profile`` — JSON object for create_user / update_user.
* ``password`` — optional initial password for create_user.
* ``group_ids`` — comma-separated or list of group IDs to seed.
* ``activate`` — bool flag controlling ``activate`` query on create.
* ``send_email`` — bool flag controlling deactivation notification.
* ``search`` / ``filter`` / ``q`` / ``after`` / ``limit`` — list paging.

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import structlog

from weftlyflow.credentials.types.okta_api import base_url_from, ssws_header
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
from weftlyflow.nodes.integrations.okta.constants import (
    DEFAULT_TIMEOUT_SECONDS,
    OP_CREATE_USER,
    OP_DEACTIVATE_USER,
    OP_GET_USER,
    OP_LIST_GROUPS,
    OP_LIST_USERS,
    OP_UPDATE_USER,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.okta.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "okta_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.okta_api",)
_USER_ID_OPERATIONS: frozenset[str] = frozenset(
    {OP_GET_USER, OP_UPDATE_USER, OP_DEACTIVATE_USER},
)
_PROFILE_OPERATIONS: frozenset[str] = frozenset({OP_CREATE_USER, OP_UPDATE_USER})
_LIST_USER_OPERATIONS: frozenset[str] = frozenset({OP_LIST_USERS})
_LIST_GROUP_OPERATIONS: frozenset[str] = frozenset({OP_LIST_GROUPS})

log = structlog.get_logger(__name__)


class OktaNode(BaseNode):
    """Dispatch a single Okta v1 call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.okta",
        version=1,
        display_name="Okta",
        description="Manage Okta users and groups via the v1 REST API.",
        icon="icons/okta.svg",
        category=NodeCategory.INTEGRATION,
        group=["identity", "iam"],
        documentation_url="https://developer.okta.com/docs/reference/core-okta-api/",
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
                default=OP_LIST_USERS,
                required=True,
                options=[
                    PropertyOption(value=OP_LIST_USERS, label="List Users"),
                    PropertyOption(value=OP_GET_USER, label="Get User"),
                    PropertyOption(value=OP_CREATE_USER, label="Create User"),
                    PropertyOption(value=OP_UPDATE_USER, label="Update User"),
                    PropertyOption(value=OP_DEACTIVATE_USER, label="Deactivate User"),
                    PropertyOption(value=OP_LIST_GROUPS, label="List Groups"),
                ],
            ),
            PropertySchema(
                name="user_id",
                display_name="User ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_USER_ID_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="profile",
                display_name="Profile",
                type="json",
                description="User profile JSON (firstName, lastName, email, login).",
                display_options=DisplayOptions(
                    show={"operation": list(_PROFILE_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="password",
                display_name="Password",
                type="string",
                description="Optional initial password for create_user.",
                type_options={"password": True},
                display_options=DisplayOptions(show={"operation": [OP_CREATE_USER]}),
            ),
            PropertySchema(
                name="group_ids",
                display_name="Group IDs",
                type="string",
                description="Comma-separated group IDs to seed on create.",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_USER]}),
            ),
            PropertySchema(
                name="activate",
                display_name="Activate",
                type="boolean",
                default=True,
                description="Whether Okta should activate the user on create.",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_USER]}),
            ),
            PropertySchema(
                name="send_email",
                display_name="Send Email",
                type="boolean",
                description="Whether Okta should email the user on deactivation.",
                display_options=DisplayOptions(show={"operation": [OP_DEACTIVATE_USER]}),
            ),
            PropertySchema(
                name="search",
                display_name="Search",
                type="string",
                description="Okta expression for list_users (e.g. 'profile.email eq ...').",
                display_options=DisplayOptions(
                    show={"operation": list(_LIST_USER_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="q",
                display_name="Query",
                type="string",
                description="Prefix match for list_groups.",
                display_options=DisplayOptions(
                    show={"operation": list(_LIST_GROUP_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="filter",
                display_name="Filter",
                type="string",
                description="SCIM-style filter expression.",
                display_options=DisplayOptions(
                    show={
                        "operation": [
                            OP_LIST_USERS,
                            OP_LIST_GROUPS,
                        ],
                    },
                ),
            ),
            PropertySchema(
                name="after",
                display_name="After",
                type="string",
                description="Opaque cursor from the previous page.",
                display_options=DisplayOptions(
                    show={
                        "operation": [
                            OP_LIST_USERS,
                            OP_LIST_GROUPS,
                        ],
                    },
                ),
            ),
            PropertySchema(
                name="limit",
                display_name="Limit",
                type="number",
                display_options=DisplayOptions(
                    show={
                        "operation": [
                            OP_LIST_USERS,
                            OP_LIST_GROUPS,
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
        """Issue one Okta REST call per input item."""
        api_token, org_url = await _resolve_credentials(ctx)
        try:
            base_url = base_url_from(org_url)
        except ValueError as exc:
            raise NodeExecutionError(
                str(exc), node_id=ctx.node.id, original=exc,
            ) from exc
        auth_header = ssws_header(api_token)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=base_url, timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(
                        ctx,
                        item,
                        client=client,
                        auth_header=auth_header,
                        logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> tuple[str, str]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Okta: an okta_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    token = str(payload.get("api_token") or "").strip()
    if not token:
        msg = "Okta: credential has an empty 'api_token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    org_url = str(payload.get("org_url") or "").strip()
    if not org_url:
        msg = "Okta: credential has an empty 'org_url'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return token, org_url


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    auth_header: str,
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_LIST_USERS).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Okta: unsupported operation {operation!r}"
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
                "Authorization": auth_header,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
    except httpx.HTTPError as exc:
        logger.error("okta.request_failed", operation=operation, error=str(exc))
        msg = f"Okta: network error on {operation}: {exc}"
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
            "okta.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Okta {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("okta.ok", operation=operation, status=response.status_code)
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
        summary = payload.get("errorSummary")
        causes = payload.get("errorCauses")
        if isinstance(summary, str) and summary:
            if isinstance(causes, list) and causes:
                first = causes[0]
                if isinstance(first, dict):
                    cause = first.get("errorSummary")
                    if isinstance(cause, str) and cause:
                        return f"{summary}: {cause}"
            return summary
        message = payload.get("message")
        if isinstance(message, str) and message:
            return message
    return f"HTTP {status_code}"
