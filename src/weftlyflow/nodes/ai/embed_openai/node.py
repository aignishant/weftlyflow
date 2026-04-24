"""Embed OpenAI node - batch embeddings via ``POST /v1/embeddings``.

Drop-in API-backed counterpart to
:mod:`weftlyflow.nodes.ai.embed_local`: same output envelope
(``<output_field>``, ``embedding_dimensions``, ``embedding_model``) so
``text_splitter -> embed_openai -> vector_memory`` interoperates with
``embed_local`` without a schema change.

All input items are sent in a single batched request (OpenAI's
``input`` field accepts up to 2 048 entries). Vectors are mapped back
to their source item by the ``index`` field in the response, which
matches the order of the batched input.

Parameters (all expression-capable):

* ``text_field`` - JSON key holding the text (default ``"chunk"``).
* ``output_field`` - key the vector is written to (default
  ``"embedding"``).
* ``model`` - OpenAI embedding model (default
  ``"text-embedding-3-small"``).
* ``dimensions`` - optional vector truncation; only ``text-embedding-3-*``
  models honor this.
* ``user`` - optional end-user identifier forwarded to OpenAI for
  abuse monitoring.

Credentials: ``weftlyflow.openai_api`` (shared with the main OpenAI
node; no new credential type is introduced).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import structlog

from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.node_spec import (
    CredentialSlot,
    NodeCategory,
    NodeSpec,
    PropertySchema,
)
from weftlyflow.nodes.base import BaseNode
from weftlyflow.nodes.integrations.openai.constants import (
    API_BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
)

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "openai_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.openai_api",)
_ORG_HEADER: str = "OpenAI-Organization"
_PROJECT_HEADER: str = "OpenAI-Project"
_EMBEDDINGS_PATH: str = "/v1/embeddings"

_DEFAULT_TEXT_FIELD: str = "chunk"
_DEFAULT_OUTPUT_FIELD: str = "embedding"
_DEFAULT_MODEL: str = "text-embedding-3-small"

log = structlog.get_logger(__name__)


class EmbedOpenAINode(BaseNode):
    """Batch-embed every input item in a single OpenAI API call."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.embed_openai",
        version=1,
        display_name="Embed (OpenAI)",
        description=(
            "Call OpenAI /v1/embeddings and attach the vector to each "
            "input item. Shares the weftlyflow.openai_api credential "
            "with the main OpenAI node."
        ),
        icon="icons/embed-openai.svg",
        category=NodeCategory.AI,
        group=["ai", "retrieval"],
        documentation_url=(
            "https://platform.openai.com/docs/api-reference/embeddings"
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
                name="text_field",
                display_name="Text Field",
                type="string",
                default=_DEFAULT_TEXT_FIELD,
                description="JSON key whose value is embedded.",
            ),
            PropertySchema(
                name="output_field",
                display_name="Output Field",
                type="string",
                default=_DEFAULT_OUTPUT_FIELD,
                description="JSON key the embedding vector is written to.",
            ),
            PropertySchema(
                name="model",
                display_name="Model",
                type="string",
                default=_DEFAULT_MODEL,
                description=(
                    "Embedding model ID (e.g. text-embedding-3-small, "
                    "text-embedding-3-large)."
                ),
            ),
            PropertySchema(
                name="dimensions",
                display_name="Dimensions",
                type="number",
                description=(
                    "Optional truncated vector size. Only honored by "
                    "text-embedding-3-* models."
                ),
            ),
            PropertySchema(
                name="user",
                display_name="User",
                type="string",
                description=(
                    "Optional end-user identifier forwarded to OpenAI "
                    "for abuse monitoring."
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Embed every input item in one batched request."""
        if not items:
            return [[]]
        api_key, org_id, project_id = await _resolve_credentials(ctx)

        # First item's resolved params drive batch-wide settings. Per-item
        # expression evaluation would force per-request calls and defeat
        # the batching; text_field/model/dimensions are rarely per-item.
        params = ctx.resolved_params(item=items[0])
        text_field = str(params.get("text_field") or _DEFAULT_TEXT_FIELD)
        output_field = str(params.get("output_field") or _DEFAULT_OUTPUT_FIELD)
        model = str(params.get("model") or _DEFAULT_MODEL).strip() or _DEFAULT_MODEL
        dimensions = _coerce_optional_positive_int(
            params.get("dimensions"), ctx, field="dimensions",
        )
        user = str(params.get("user") or "").strip()

        inputs = [_extract_text(item, text_field) for item in items]

        body: dict[str, Any] = {"model": model, "input": inputs}
        if dimensions is not None:
            body["dimensions"] = dimensions
        if user:
            body["user"] = user

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if org_id:
            headers[_ORG_HEADER] = org_id
        if project_id:
            headers[_PROJECT_HEADER] = project_id

        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        try:
            async with httpx.AsyncClient(
                base_url=API_BASE_URL, timeout=DEFAULT_TIMEOUT_SECONDS,
            ) as client:
                response = await client.post(
                    _EMBEDDINGS_PATH, json=body, headers=headers,
                )
        except httpx.HTTPError as exc:
            bound.error("embed_openai.request_failed", error=str(exc))
            msg = f"Embed OpenAI: network error: {exc}"
            raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc

        payload = _safe_json(response)
        if response.status_code >= httpx.codes.BAD_REQUEST:
            error = _error_message(payload, response.status_code)
            bound.warning(
                "embed_openai.api_error",
                status=response.status_code,
                error=error,
            )
            msg = (
                f"Embed OpenAI failed (HTTP {response.status_code}): {error}"
            )
            raise NodeExecutionError(msg, node_id=ctx.node.id)

        vectors = _extract_vectors(payload, expected=len(items), ctx=ctx)
        bound.info("embed_openai.ok", count=len(items), model=model)

        emitted = [
            _merge(item, vector, output_field=output_field, model=model)
            for item, vector in zip(items, vectors, strict=True)
        ]
        return [emitted]


async def _resolve_credentials(ctx: ExecutionContext) -> tuple[str, str, str]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Embed OpenAI: an openai_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    api_key = str(payload.get("api_key") or "").strip()
    if not api_key:
        msg = "Embed OpenAI: credential has an empty 'api_key'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    org_id = str(payload.get("organization_id") or "").strip()
    project_id = str(payload.get("project_id") or "").strip()
    return api_key, org_id, project_id


def _extract_text(item: Item, text_field: str) -> str:
    source = item.json if isinstance(item.json, dict) else {}
    raw = source.get(text_field, "")
    return raw if isinstance(raw, str) else str(raw)


def _extract_vectors(
    payload: Any,
    *,
    expected: int,
    ctx: ExecutionContext,
) -> list[list[float]]:
    if not isinstance(payload, dict):
        msg = "Embed OpenAI: malformed response (expected JSON object)"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    data = payload.get("data")
    if not isinstance(data, list) or len(data) != expected:
        msg = (
            f"Embed OpenAI: expected {expected} embeddings, "
            f"got {len(data) if isinstance(data, list) else 0}"
        )
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    # OpenAI returns entries in submission order but includes ``index``
    # as the authoritative position marker; sort by it to be safe.
    ordered: list[list[float]] = [[] for _ in range(expected)]
    seen: set[int] = set()
    for entry in data:
        if not isinstance(entry, dict):
            msg = "Embed OpenAI: malformed embedding entry"
            raise NodeExecutionError(msg, node_id=ctx.node.id)
        index = entry.get("index")
        if not isinstance(index, int) or index < 0 or index >= expected:
            msg = "Embed OpenAI: embedding entry is missing a valid 'index'"
            raise NodeExecutionError(msg, node_id=ctx.node.id)
        if index in seen:
            msg = f"Embed OpenAI: duplicate embedding index {index}"
            raise NodeExecutionError(msg, node_id=ctx.node.id)
        vector = entry.get("embedding")
        if not isinstance(vector, list):
            msg = "Embed OpenAI: embedding entry is missing 'embedding' list"
            raise NodeExecutionError(msg, node_id=ctx.node.id)
        ordered[index] = [float(x) for x in vector]
        seen.add(index)
    return ordered


def _merge(item: Item, vector: list[float], *, output_field: str, model: str) -> Item:
    source = item.json if isinstance(item.json, dict) else {}
    return Item(
        json={
            **source,
            output_field: vector,
            "embedding_dimensions": len(vector),
            "embedding_model": model,
        },
        binary=item.binary,
        paired_item=item.paired_item,
        error=item.error,
    )


def _coerce_optional_positive_int(
    raw: Any,
    ctx: ExecutionContext,
    *,
    field: str,
) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = f"Embed OpenAI: {field!r} must be an integer"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    if value < 1:
        msg = f"Embed OpenAI: {field!r} must be >= 1"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return value


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
