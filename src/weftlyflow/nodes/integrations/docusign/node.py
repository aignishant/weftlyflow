"""DocuSign eSignature node — envelopes and templates.

Dispatches against the account-specific REST host stored on the
credential (``account_base_url``, e.g. ``https://demo.docusign.net/restapi``).

Authentication is the OAuth 2.0 JWT Bearer grant. Before the dispatch
loop begins, the node calls
:func:`~weftlyflow.credentials.types.docusign_jwt.fetch_access_token`
to exchange a freshly-signed RS256 JWT for a Bearer; the same token
is reused for every input item because DocuSign tokens live ~1 hour.

Parameters (all expression-capable):

* ``operation`` — ``list_envelopes`` / ``get_envelope`` /
  ``create_envelope`` / ``list_templates``.
* ``account_id`` — DocuSign account GUID.
* ``envelope_id`` — required for ``get_envelope``.
* ``email_subject`` / ``email_message`` / ``status`` /
  ``template_id`` / ``template_roles`` / ``documents`` /
  ``recipients`` — create envelope inputs.
* ``from_date`` / ``status`` — list envelope filters.

Output: one item per input item with ``operation``, ``status``, and
parsed ``response``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import structlog

from weftlyflow.credentials.types.docusign_jwt import (
    fetch_access_token,
    oauth_host_for,
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
from weftlyflow.nodes.integrations.docusign.constants import (
    DEFAULT_TIMEOUT_SECONDS,
    OP_CREATE_ENVELOPE,
    OP_GET_ENVELOPE,
    OP_LIST_ENVELOPES,
    OP_LIST_TEMPLATES,
    STATUS_CREATED,
    STATUS_SENT,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.docusign.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "docusign_jwt"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.docusign_jwt",)

log = structlog.get_logger(__name__)


class DocuSignNode(BaseNode):
    """Dispatch DocuSign eSignature calls using a JWT-grant Bearer token."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.docusign",
        version=1,
        display_name="DocuSign eSignature",
        description="Envelopes and templates on DocuSign eSignature REST.",
        icon="icons/docusign.svg",
        category=NodeCategory.INTEGRATION,
        group=["documents"],
        documentation_url="https://developers.docusign.com/docs/esign-rest-api/",
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
                default=OP_LIST_ENVELOPES,
                required=True,
                options=[
                    PropertyOption(value=OP_LIST_ENVELOPES, label="List Envelopes"),
                    PropertyOption(value=OP_GET_ENVELOPE, label="Get Envelope"),
                    PropertyOption(value=OP_CREATE_ENVELOPE, label="Create Envelope"),
                    PropertyOption(value=OP_LIST_TEMPLATES, label="List Templates"),
                ],
            ),
            PropertySchema(
                name="account_id",
                display_name="Account ID",
                type="string",
                required=True,
                description="DocuSign account GUID.",
            ),
            PropertySchema(
                name="envelope_id",
                display_name="Envelope ID",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_GET_ENVELOPE]}),
            ),
            PropertySchema(
                name="from_date",
                display_name="From Date",
                type="string",
                description="ISO-8601 timestamp filter for list_envelopes.",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_ENVELOPES]},
                ),
            ),
            PropertySchema(
                name="email_subject",
                display_name="Email Subject",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_ENVELOPE]},
                ),
            ),
            PropertySchema(
                name="email_message",
                display_name="Email Message",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_ENVELOPE]},
                ),
            ),
            PropertySchema(
                name="status",
                display_name="Envelope Status",
                type="options",
                default=STATUS_SENT,
                options=[
                    PropertyOption(value=STATUS_SENT, label="Sent"),
                    PropertyOption(value=STATUS_CREATED, label="Created (Draft)"),
                ],
                display_options=DisplayOptions(
                    show={
                        "operation": [OP_CREATE_ENVELOPE, OP_LIST_ENVELOPES],
                    },
                ),
            ),
            PropertySchema(
                name="template_id",
                display_name="Template ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_ENVELOPE]},
                ),
            ),
            PropertySchema(
                name="template_roles",
                display_name="Template Roles",
                type="json",
                description='List of {"email","name","roleName"} objects.',
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_ENVELOPE]},
                ),
            ),
            PropertySchema(
                name="documents",
                display_name="Documents",
                type="json",
                description="List of DocuSign document objects (no template path).",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_ENVELOPE]},
                ),
            ),
            PropertySchema(
                name="recipients",
                display_name="Recipients",
                type="json",
                description="DocuSign recipients object (signers, carbonCopies, ...).",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_ENVELOPE]},
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Fetch one Bearer, then issue one DocuSign call per input item."""
        injector, payload = await _resolve_credentials(ctx)
        del injector  # JWT grant — token is fetched explicitly below.
        account_base_url = str(payload.get("account_base_url") or "").strip().rstrip("/")
        if not account_base_url:
            msg = "DocuSign: credential has no 'account_base_url'"
            raise NodeExecutionError(msg, node_id=ctx.node.id)
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        token = await _fetch_token(ctx, payload, logger=bound)
        seed = items or [Item()]
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=account_base_url, timeout=DEFAULT_TIMEOUT_SECONDS,
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
        msg = "DocuSign: a docusign_jwt credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    injector, payload = credential
    for key in ("integration_key", "user_id", "private_key", "account_base_url"):
        if not str(payload.get(key) or "").strip():
            msg = f"DocuSign: credential has an empty {key!r}"
            raise NodeExecutionError(msg, node_id=ctx.node.id)
    return injector, payload


async def _fetch_token(
    ctx: ExecutionContext, creds: dict[str, Any], *, logger: Any,
) -> str:
    try:
        async with httpx.AsyncClient(
            base_url=oauth_host_for(creds.get("environment")),
            timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as oauth_client:
            token = await fetch_access_token(oauth_client, creds)
    except (httpx.HTTPError, ValueError) as exc:
        logger.error("docusign.token_failed", error=str(exc))
        msg = f"DocuSign: failed to obtain access token: {exc}"
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
    operation = str(params.get("operation") or OP_LIST_ENVELOPES).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"DocuSign: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    account_id = str(params.get("account_id") or "").strip()
    try:
        method, path, body, query = build_request(operation, account_id, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = client.build_request(
        method, path, params=query or None, json=body, headers=headers,
    )
    try:
        response = await client.send(request)
    except httpx.HTTPError as exc:
        logger.error("docusign.request_failed", operation=operation, error=str(exc))
        msg = f"DocuSign: network error on {operation}: {exc}"
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
            "docusign.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"DocuSign {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("docusign.ok", operation=operation, status=response.status_code)
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
        for key in ("message", "errorCode", "error_description", "error"):
            value = parsed.get(key)
            if isinstance(value, str) and value:
                return value
    return f"HTTP {status_code}"
