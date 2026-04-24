"""Mistral node — La Plateforme chat, FIM, embeddings, and model lookup.

Dispatches to ``https://api.mistral.ai`` with a standard
``Authorization: Bearer`` header injected by
:class:`~weftlyflow.credentials.types.mistral_api.MistralApiCredential`.

Parameters (all expression-capable):

* ``operation`` — ``chat_completion``, ``fim_completion``,
  ``create_embedding``, ``list_models``.
* ``model`` — model id. Defaults differ per operation:
  ``mistral-large-latest`` for chat, ``codestral-latest`` for FIM,
  ``mistral-embed`` for embeddings.
* ``messages`` — list of ``{"role", "content"}`` objects
  (chat_completion).
* ``prompt`` / ``suffix`` — fill-in-the-middle inputs
  (fim_completion; ``suffix`` is optional).
* ``input`` — string or list of strings (create_embedding).
* ``temperature``, ``top_p``, ``max_tokens`` — sampling controls.
* ``response_format`` — ``text`` or ``json_object`` (chat only).
* ``tools`` — optional OpenAI-style tool schema list (chat only).
* ``safe_prompt`` — optional boolean guardrail toggle (chat only).

Output: one item per input item with ``operation``, ``status``, and
the parsed ``response``.
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
from weftlyflow.nodes.integrations.mistral.constants import (
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT_SECONDS,
    OP_CHAT_COMPLETION,
    OP_CREATE_EMBEDDING,
    OP_FIM_COMPLETION,
    OP_LIST_MODELS,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.mistral.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_API_HOST: str = "https://api.mistral.ai"
_CREDENTIAL_SLOT: str = "mistral_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.mistral_api",)
_SAMPLE_OPERATIONS: frozenset[str] = frozenset(
    {OP_CHAT_COMPLETION, OP_FIM_COMPLETION},
)

log = structlog.get_logger(__name__)


class MistralNode(BaseNode):
    """Dispatch a single Mistral La Plateforme call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.mistral",
        version=1,
        display_name="Mistral",
        description="Call the Mistral La Plateforme API (chat, FIM, embeddings).",
        icon="icons/mistral.svg",
        category=NodeCategory.INTEGRATION,
        group=["ai", "llm"],
        documentation_url="https://docs.mistral.ai/api/",
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
                    PropertyOption(value=OP_CHAT_COMPLETION, label="Chat Completion"),
                    PropertyOption(value=OP_FIM_COMPLETION, label="FIM Completion"),
                    PropertyOption(value=OP_CREATE_EMBEDDING, label="Create Embedding"),
                    PropertyOption(value=OP_LIST_MODELS, label="List Models"),
                ],
            ),
            PropertySchema(
                name="model",
                display_name="Model",
                type="string",
                default=DEFAULT_MODEL,
                display_options=DisplayOptions(
                    show={"operation": [
                        OP_CHAT_COMPLETION, OP_FIM_COMPLETION, OP_CREATE_EMBEDDING,
                    ]},
                ),
            ),
            PropertySchema(
                name="messages",
                display_name="Messages",
                type="json",
                description='[{"role": "user", "content": "Hello"}, ...]',
                display_options=DisplayOptions(
                    show={"operation": [OP_CHAT_COMPLETION]},
                ),
            ),
            PropertySchema(
                name="prompt",
                display_name="Prompt",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_FIM_COMPLETION]},
                ),
            ),
            PropertySchema(
                name="suffix",
                display_name="Suffix",
                type="string",
                description="Optional code after the FIM insertion point.",
                display_options=DisplayOptions(
                    show={"operation": [OP_FIM_COMPLETION]},
                ),
            ),
            PropertySchema(
                name="input",
                display_name="Input",
                type="string",
                description="Text or JSON-array of texts to embed.",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_EMBEDDING]},
                ),
            ),
            PropertySchema(
                name="temperature",
                display_name="Temperature",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": list(_SAMPLE_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="top_p",
                display_name="Top P",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": list(_SAMPLE_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="max_tokens",
                display_name="Max Tokens",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": list(_SAMPLE_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="response_format",
                display_name="Response Format",
                type="options",
                default="",
                options=[
                    PropertyOption(value="", label="Default (text)"),
                    PropertyOption(value="text", label="Text"),
                    PropertyOption(value="json_object", label="JSON Object"),
                ],
                display_options=DisplayOptions(
                    show={"operation": [OP_CHAT_COMPLETION]},
                ),
            ),
            PropertySchema(
                name="tools",
                display_name="Tools",
                type="json",
                description="Optional OpenAI-style tool schema list.",
                display_options=DisplayOptions(
                    show={"operation": [OP_CHAT_COMPLETION]},
                ),
            ),
            PropertySchema(
                name="safe_prompt",
                display_name="Safe Prompt",
                type="boolean",
                description="Opt into Mistral's built-in guardrails prefix.",
                display_options=DisplayOptions(
                    show={"operation": [OP_CHAT_COMPLETION]},
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Mistral La Plateforme call per input item."""
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
        msg = "Mistral: a mistral_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    injector, payload = credential
    api_key = str(payload.get("api_key") or "").strip()
    if not api_key:
        msg = "Mistral: credential has an empty 'api_key'"
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
    operation = str(params.get("operation") or OP_CHAT_COMPLETION).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Mistral: unsupported operation {operation!r}"
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
        logger.error("mistral.request_failed", operation=operation, error=str(exc))
        msg = f"Mistral: network error on {operation}: {exc}"
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
            "mistral.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Mistral {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("mistral.ok", operation=operation, status=response.status_code)
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
        if isinstance(error, dict):
            inner = error.get("message")
            if isinstance(inner, str) and inner:
                return inner
            err_type = error.get("type")
            if isinstance(err_type, str) and err_type:
                return err_type
        detail = payload.get("detail")
        if isinstance(detail, str) and detail:
            return detail
    return f"HTTP {status_code}"
