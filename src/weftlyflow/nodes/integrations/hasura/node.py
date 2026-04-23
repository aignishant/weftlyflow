"""Hasura node — GraphQL queries, mutations, and introspection.

Dispatches to a credential-owned ``base_url`` (self-hosted GraphQL
Engine instances) via POST ``/v1/graphql``. Auth is a single
``X-Hasura-Admin-Secret`` header (+ optional ``X-Hasura-Role``) handled
by :class:`~weftlyflow.credentials.types.hasura_api.HasuraApiCredential`.

Distinctive Hasura semantics:

* **HTTP 200 + ``errors`` envelope** — GraphQL-level failures come back
  with HTTP 200 and an ``errors`` array; the node must inspect the body
  to surface a :class:`NodeExecutionError`.
* **Per-call role override** — a node-level ``role`` param overrides
  the credential's default role header for admin-bypass scenarios.

Parameters (all expression-capable):

* ``operation`` — ``run_query``, ``run_mutation``, ``introspect``.
* ``query`` — the GraphQL document (required for query/mutation).
* ``variables`` — JSON object of variables.
* ``operation_name`` — selects a named op within a multi-op document.
* ``role`` — per-call ``X-Hasura-Role`` override.

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response`` (``{"data": ..., "errors": ...}``).
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
from weftlyflow.nodes.integrations.hasura.constants import (
    DEFAULT_TIMEOUT_SECONDS,
    GRAPHQL_PATH,
    OP_INTROSPECT,
    OP_RUN_MUTATION,
    OP_RUN_QUERY,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.hasura.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "hasura_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.hasura_api",)
_ROLE_HEADER: str = "X-Hasura-Role"
_DOCUMENT_OPERATIONS: frozenset[str] = frozenset(
    {OP_RUN_QUERY, OP_RUN_MUTATION},
)

log = structlog.get_logger(__name__)


class HasuraNode(BaseNode):
    """Dispatch a single Hasura GraphQL call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.hasura",
        version=1,
        display_name="Hasura",
        description="Run GraphQL queries, mutations, and introspection on Hasura Engine.",
        icon="icons/hasura.svg",
        category=NodeCategory.INTEGRATION,
        group=["database", "graphql"],
        documentation_url=(
            "https://hasura.io/docs/latest/api-reference/graphql-api/overview/"
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
                default=OP_RUN_QUERY,
                required=True,
                options=[
                    PropertyOption(value=OP_RUN_QUERY, label="Run Query"),
                    PropertyOption(value=OP_RUN_MUTATION, label="Run Mutation"),
                    PropertyOption(value=OP_INTROSPECT, label="Introspect Schema"),
                ],
            ),
            PropertySchema(
                name="query",
                display_name="GraphQL Document",
                type="string",
                description="Full GraphQL query or mutation text.",
                display_options=DisplayOptions(
                    show={"operation": list(_DOCUMENT_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="variables",
                display_name="Variables",
                type="json",
                description="Variables object bound to the document.",
                display_options=DisplayOptions(
                    show={"operation": list(_DOCUMENT_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="operation_name",
                display_name="Operation Name",
                type="string",
                description="Name of the op to run when the document has multiple.",
                display_options=DisplayOptions(
                    show={"operation": list(_DOCUMENT_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="role",
                display_name="Role (override)",
                type="string",
                description="Per-call 'X-Hasura-Role' override.",
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Hasura GraphQL POST per input item."""
        injector, payload = await _resolve_credentials(ctx)
        base_url = str(payload.get("base_url") or "").strip().rstrip("/")
        if not base_url:
            msg = "Hasura: credential has an empty 'base_url'"
            raise NodeExecutionError(msg, node_id=ctx.node.id)
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
        msg = "Hasura: a hasura_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    injector, payload = credential
    if not str(payload.get("admin_secret") or "").strip():
        msg = "Hasura: credential has an empty 'admin_secret'"
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
    operation = str(params.get("operation") or OP_RUN_QUERY).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Hasura: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        body = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    request_headers: dict[str, str] = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    request = client.build_request(
        "POST",
        GRAPHQL_PATH,
        json=body,
        headers=request_headers,
    )
    request = await injector.inject(creds, request)
    role_override = str(params.get("role") or "").strip()
    if role_override:
        request.headers[_ROLE_HEADER] = role_override
    try:
        response = await client.send(request)
    except httpx.HTTPError as exc:
        logger.error("hasura.request_failed", operation=operation, error=str(exc))
        msg = f"Hasura: network error on {operation}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    payload = _safe_json(response)
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "response": payload,
    }
    graphql_errors = _graphql_errors(payload)
    if response.status_code >= httpx.codes.BAD_REQUEST or graphql_errors:
        error = graphql_errors or _error_message(payload, response.status_code)
        logger.warning(
            "hasura.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Hasura {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("hasura.ok", operation=operation, status=response.status_code)
    return Item(json=result)


def _safe_json(response: httpx.Response) -> Any:
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text, "status_code": response.status_code}


def _graphql_errors(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    errors = payload.get("errors")
    if not isinstance(errors, list) or not errors:
        return None
    first = errors[0]
    if isinstance(first, dict):
        message = first.get("message")
        if isinstance(message, str) and message:
            return message
    return "GraphQL errors"


def _error_message(payload: Any, status_code: int) -> str:
    if isinstance(payload, dict):
        message = payload.get("error") or payload.get("message")
        if isinstance(message, str) and message:
            return message
    return f"HTTP {status_code}"
