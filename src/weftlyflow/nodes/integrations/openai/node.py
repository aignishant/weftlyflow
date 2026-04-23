"""OpenAI node — chat completions, embeddings, moderation, and images.

Dispatches to the OpenAI REST API with the distinctive *pair* of tenant
scoping headers (``OpenAI-Organization`` + ``OpenAI-Project``) sourced
from
:class:`~weftlyflow.credentials.types.openai_api.OpenAIApiCredential`.

Parameters (all expression-capable):

* ``operation`` — ``chat_completion``, ``create_embedding``,
  ``list_models``, ``get_model``, ``create_moderation``,
  ``create_image``.
* ``model`` — target model (required for most operations).
* ``messages`` — chat message list (role/content dicts).
* ``temperature`` / ``top_p`` / ``max_tokens`` — sampling controls.
* ``response_format`` — ``text`` or ``json_object`` for chat; ``url``
  or ``b64_json`` for images.
* ``tools`` — optional tool-call spec (JSON array).
* ``input`` — embedding / moderation payload (string or list).
* ``dimensions`` — optional embedding dimensionality.
* ``prompt`` / ``size`` / ``n`` — image generation.

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
from weftlyflow.nodes.integrations.openai.constants import (
    API_BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    OP_CHAT_COMPLETION,
    OP_CREATE_EMBEDDING,
    OP_CREATE_IMAGE,
    OP_CREATE_MODERATION,
    OP_GET_MODEL,
    OP_LIST_MODELS,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.openai.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "openai_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.openai_api",)
_ORG_HEADER: str = "OpenAI-Organization"
_PROJECT_HEADER: str = "OpenAI-Project"
_MODEL_OPERATIONS: frozenset[str] = frozenset(
    {
        OP_CHAT_COMPLETION,
        OP_CREATE_EMBEDDING,
        OP_GET_MODEL,
        OP_CREATE_MODERATION,
    },
)
_INPUT_OPERATIONS: frozenset[str] = frozenset(
    {OP_CREATE_EMBEDDING, OP_CREATE_MODERATION},
)

log = structlog.get_logger(__name__)


class OpenAINode(BaseNode):
    """Dispatch a single OpenAI API call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.openai",
        version=1,
        display_name="OpenAI",
        description="Chat completions, embeddings, moderation, and images.",
        icon="icons/openai.svg",
        category=NodeCategory.INTEGRATION,
        group=["ai", "llm"],
        documentation_url="https://platform.openai.com/docs/api-reference",
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
                default=OP_CHAT_COMPLETION,
                required=True,
                options=[
                    PropertyOption(
                        value=OP_CHAT_COMPLETION, label="Chat Completion",
                    ),
                    PropertyOption(
                        value=OP_CREATE_EMBEDDING, label="Create Embedding",
                    ),
                    PropertyOption(value=OP_LIST_MODELS, label="List Models"),
                    PropertyOption(value=OP_GET_MODEL, label="Get Model"),
                    PropertyOption(
                        value=OP_CREATE_MODERATION, label="Create Moderation",
                    ),
                    PropertyOption(
                        value=OP_CREATE_IMAGE, label="Create Image",
                    ),
                ],
            ),
            PropertySchema(
                name="model",
                display_name="Model",
                type="string",
                description="Model ID (e.g. gpt-4o-mini, text-embedding-3-small).",
                display_options=DisplayOptions(
                    show={"operation": list(_MODEL_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="messages",
                display_name="Messages",
                type="json",
                description='[{"role": "user", "content": "..."}]',
                display_options=DisplayOptions(
                    show={"operation": [OP_CHAT_COMPLETION]},
                ),
            ),
            PropertySchema(
                name="temperature",
                display_name="Temperature",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": [OP_CHAT_COMPLETION]},
                ),
            ),
            PropertySchema(
                name="top_p",
                display_name="Top P",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": [OP_CHAT_COMPLETION]},
                ),
            ),
            PropertySchema(
                name="max_tokens",
                display_name="Max Tokens",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": [OP_CHAT_COMPLETION]},
                ),
            ),
            PropertySchema(
                name="response_format",
                display_name="Response Format",
                type="string",
                description=(
                    "Chat: 'text' or 'json_object'. "
                    "Image: 'url' or 'b64_json'."
                ),
                display_options=DisplayOptions(
                    show={
                        "operation": [OP_CHAT_COMPLETION, OP_CREATE_IMAGE],
                    },
                ),
            ),
            PropertySchema(
                name="tools",
                display_name="Tools",
                type="json",
                description="Optional tool-call spec array.",
                display_options=DisplayOptions(
                    show={"operation": [OP_CHAT_COMPLETION]},
                ),
            ),
            PropertySchema(
                name="input",
                display_name="Input",
                type="string",
                description="String or JSON list of strings.",
                display_options=DisplayOptions(
                    show={"operation": list(_INPUT_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="dimensions",
                display_name="Dimensions",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_EMBEDDING]},
                ),
            ),
            PropertySchema(
                name="prompt",
                display_name="Prompt",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_IMAGE]},
                ),
            ),
            PropertySchema(
                name="size",
                display_name="Size",
                type="string",
                description="e.g. 1024x1024.",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_IMAGE]},
                ),
            ),
            PropertySchema(
                name="n",
                display_name="Count",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_IMAGE]},
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one OpenAI API call per input item."""
        api_key, org_id, project_id = await _resolve_credentials(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        }
        if org_id:
            headers[_ORG_HEADER] = org_id
        if project_id:
            headers[_PROJECT_HEADER] = project_id
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=API_BASE_URL, timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(
                        ctx,
                        item,
                        client=client,
                        headers=headers,
                        logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> tuple[str, str, str]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "OpenAI: an openai_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    api_key = str(payload.get("api_key") or "").strip()
    if not api_key:
        msg = "OpenAI: credential has an empty 'api_key'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    org_id = str(payload.get("organization_id") or "").strip()
    project_id = str(payload.get("project_id") or "").strip()
    return api_key, org_id, project_id


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    headers: dict[str, str],
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_CHAT_COMPLETION).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"OpenAI: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, body, query = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    request_headers = dict(headers)
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    try:
        response = await client.request(
            method,
            path,
            params=query or None,
            json=body,
            headers=request_headers,
        )
    except httpx.HTTPError as exc:
        logger.error("openai.request_failed", operation=operation, error=str(exc))
        msg = f"OpenAI: network error on {operation}: {exc}"
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
            "openai.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"OpenAI {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("openai.ok", operation=operation, status=response.status_code)
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
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message:
                return message
            code = error.get("code")
            if isinstance(code, str) and code:
                return code
        message = payload.get("message")
        if isinstance(message, str) and message:
            return message
    return f"HTTP {status_code}"
