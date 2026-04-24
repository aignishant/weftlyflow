"""Google GenAI node — Gemini generateContent, countTokens, and model lookup.

Dispatches to ``https://generativelanguage.googleapis.com`` with the
``x-goog-api-key`` header injected by
:class:`~weftlyflow.credentials.types.google_genai_api.GoogleGenAIApiCredential`.

Parameters (all expression-capable):

* ``operation`` — ``generate_content``, ``count_tokens``, ``list_models``,
  ``get_model``.
* ``model`` — model id (default ``gemini-1.5-flash``). Accepts both the
  bare form and the ``models/<id>`` fully-qualified form.
* ``contents`` — list of ``{"role": ..., "parts": [...]}`` objects.
* ``system`` — optional system instruction (wrapped into the
  ``systemInstruction`` field automatically).
* ``temperature`` / ``top_p`` / ``top_k`` / ``max_output_tokens`` —
  sampling controls, bundled into ``generationConfig`` on the wire.
* ``safety_settings`` — optional list passed through verbatim.
* ``model_id`` — target for ``get_model``.

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
from weftlyflow.nodes.integrations.google_genai.constants import (
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT_SECONDS,
    OP_COUNT_TOKENS,
    OP_GENERATE_CONTENT,
    OP_GET_MODEL,
    OP_LIST_MODELS,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.google_genai.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_API_HOST: str = "https://generativelanguage.googleapis.com"
_CREDENTIAL_SLOT: str = "google_genai_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.google_genai_api",)
_CONTENT_OPERATIONS: frozenset[str] = frozenset(
    {OP_GENERATE_CONTENT, OP_COUNT_TOKENS},
)

log = structlog.get_logger(__name__)


class GoogleGenAINode(BaseNode):
    """Dispatch a single Gemini v1beta call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.google_genai",
        version=1,
        display_name="Google GenAI",
        description="Call the Google Generative Language (Gemini) API.",
        icon="icons/google-genai.svg",
        category=NodeCategory.INTEGRATION,
        group=["ai", "llm"],
        documentation_url="https://ai.google.dev/api/rest",
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
                default=OP_GENERATE_CONTENT,
                required=True,
                options=[
                    PropertyOption(value=OP_GENERATE_CONTENT, label="Generate Content"),
                    PropertyOption(value=OP_COUNT_TOKENS, label="Count Tokens"),
                    PropertyOption(value=OP_LIST_MODELS, label="List Models"),
                    PropertyOption(value=OP_GET_MODEL, label="Get Model"),
                ],
            ),
            PropertySchema(
                name="model",
                display_name="Model",
                type="string",
                default=DEFAULT_MODEL,
                display_options=DisplayOptions(
                    show={"operation": list(_CONTENT_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="contents",
                display_name="Contents",
                type="json",
                description=(
                    '[{"role": "user", "parts": [{"text": "Hello"}]}, ...]'
                ),
                display_options=DisplayOptions(
                    show={"operation": list(_CONTENT_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="system",
                display_name="System Instruction",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_GENERATE_CONTENT]},
                ),
            ),
            PropertySchema(
                name="temperature",
                display_name="Temperature",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": [OP_GENERATE_CONTENT]},
                ),
            ),
            PropertySchema(
                name="max_output_tokens",
                display_name="Max Output Tokens",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": [OP_GENERATE_CONTENT]},
                ),
            ),
            PropertySchema(
                name="top_p",
                display_name="Top P",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": [OP_GENERATE_CONTENT]},
                ),
            ),
            PropertySchema(
                name="top_k",
                display_name="Top K",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": [OP_GENERATE_CONTENT]},
                ),
            ),
            PropertySchema(
                name="safety_settings",
                display_name="Safety Settings",
                type="json",
                description="Optional list passed through as 'safetySettings'.",
                display_options=DisplayOptions(
                    show={"operation": [OP_GENERATE_CONTENT]},
                ),
            ),
            PropertySchema(
                name="model_id",
                display_name="Model ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_GET_MODEL]},
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Gemini v1beta call per input item."""
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
        msg = "Google GenAI: a google_genai_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    injector, payload = credential
    api_key = str(payload.get("api_key") or "").strip()
    if not api_key:
        msg = "Google GenAI: credential has an empty 'api_key'"
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
    operation = str(params.get("operation") or OP_GENERATE_CONTENT).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Google GenAI: unsupported operation {operation!r}"
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
        logger.error("google_genai.request_failed", operation=operation, error=str(exc))
        msg = f"Google GenAI: network error on {operation}: {exc}"
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
            "google_genai.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = (
            f"Google GenAI {operation} failed "
            f"(HTTP {response.status_code}): {error}"
        )
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("google_genai.ok", operation=operation, status=response.status_code)
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
            status = error.get("status")
            if isinstance(status, str) and status:
                return status
        message = payload.get("message")
        if isinstance(message, str) and message:
            return message
    return f"HTTP {status_code}"
