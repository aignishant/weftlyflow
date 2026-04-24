"""Ollama node — chat, completion, embeddings, model listing for self-hosted LLMs.

Dispatches to ``<credential base_url>/api/...`` with optional
``Authorization: Bearer <api_key>`` sourced from
:class:`~weftlyflow.credentials.types.ollama_api.OllamaApiCredential`.
The base URL is part of the credential because Ollama is self-hosted —
every deployment lives at its own host, and a fresh install needs no
auth at all. When no credential is attached the node targets
``http://localhost:11434`` directly, which is the out-of-box Ollama
developer experience.

Parameters (all expression-capable):

* ``operation`` — ``generate``, ``chat``, ``embeddings``, ``list_models``.
* ``model`` — model id (default ``llama3.2``).
* ``prompt`` — single string for ``generate`` / ``embeddings``.
* ``messages`` — list of ``{"role": ..., "content": ...}`` for ``chat``.
* ``system`` — optional system prompt for ``generate``.
* ``format`` — optional ``"json"`` for JSON-mode output.
* ``options`` — optional JSON map of Ollama sampling options
  (``temperature``, ``num_predict``, ``top_p``, ...).

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import structlog

from weftlyflow.credentials.types.ollama_api import base_url_from
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
from weftlyflow.nodes.integrations.ollama.constants import (
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT_SECONDS,
    OP_CHAT,
    OP_EMBEDDINGS,
    OP_GENERATE,
    OP_LIST_MODELS,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.ollama.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "ollama_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.ollama_api",)
_DEFAULT_BASE_URL: str = "http://localhost:11434"
_MODEL_OPERATIONS: frozenset[str] = frozenset({OP_GENERATE, OP_CHAT, OP_EMBEDDINGS})
_PROMPT_OPERATIONS: frozenset[str] = frozenset({OP_GENERATE, OP_EMBEDDINGS})
_BODY_OPTION_OPERATIONS: frozenset[str] = _MODEL_OPERATIONS

log = structlog.get_logger(__name__)


class OllamaNode(BaseNode):
    """Dispatch a single Ollama REST call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.ollama",
        version=1,
        display_name="Ollama",
        description=(
            "Run chat, completion, embeddings, or model listing "
            "on a self-hosted Ollama server."
        ),
        icon="icons/ollama.svg",
        category=NodeCategory.INTEGRATION,
        group=["ai", "llm"],
        documentation_url="https://github.com/ollama/ollama/blob/main/docs/api.md",
        credentials=[
            CredentialSlot(
                name=_CREDENTIAL_SLOT,
                required=False,
                credential_types=list(_CREDENTIAL_SLUGS),
            ),
        ],
        properties=[
            PropertySchema(
                name="operation",
                display_name="Operation",
                type="options",
                default=OP_CHAT,
                required=True,
                options=[
                    PropertyOption(value=OP_CHAT, label="Chat"),
                    PropertyOption(value=OP_GENERATE, label="Generate"),
                    PropertyOption(value=OP_EMBEDDINGS, label="Embeddings"),
                    PropertyOption(value=OP_LIST_MODELS, label="List Models"),
                ],
            ),
            PropertySchema(
                name="model",
                display_name="Model",
                type="string",
                default=DEFAULT_MODEL,
                display_options=DisplayOptions(
                    show={"operation": list(_MODEL_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="messages",
                display_name="Messages",
                type="json",
                description='[{"role": "user", "content": "Hello"}, ...]',
                display_options=DisplayOptions(show={"operation": [OP_CHAT]}),
            ),
            PropertySchema(
                name="prompt",
                display_name="Prompt",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_PROMPT_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="system",
                display_name="System Prompt",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_GENERATE]}),
            ),
            PropertySchema(
                name="format",
                display_name="Output Format",
                type="string",
                description="Set to 'json' to force JSON-mode output.",
                display_options=DisplayOptions(
                    show={"operation": [OP_GENERATE, OP_CHAT]},
                ),
            ),
            PropertySchema(
                name="options",
                display_name="Options",
                type="json",
                description='Sampling options, e.g. {"temperature": 0.2, "num_predict": 256}.',
                display_options=DisplayOptions(
                    show={"operation": list(_BODY_OPTION_OPERATIONS)},
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Ollama REST call per input item."""
        injector, creds, base_url = await _resolve_credentials(ctx)
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
                        creds=creds,
                        logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(
    ctx: ExecutionContext,
) -> tuple[Any | None, dict[str, Any], str]:
    """Return ``(injector, payload, base_url)`` — all three defaulted when no credential."""
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        return None, {}, _DEFAULT_BASE_URL
    injector, payload = credential
    base_url = base_url_from(str(payload.get("base_url") or ""))
    return injector, payload, base_url


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    injector: Any | None,
    creds: dict[str, Any],
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_CHAT).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Ollama: unsupported operation {operation!r}"
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
    if injector is not None:
        request = await injector.inject(creds, request)
    try:
        response = await client.send(request)
    except httpx.HTTPError as exc:
        logger.error("ollama.request_failed", operation=operation, error=str(exc))
        msg = f"Ollama: network error on {operation}: {exc}"
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
            "ollama.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Ollama {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("ollama.ok", operation=operation, status=response.status_code)
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
        if isinstance(error, str) and error:
            return error
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message:
                return message
    return f"HTTP {status_code}"
