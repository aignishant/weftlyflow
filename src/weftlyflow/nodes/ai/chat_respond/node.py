"""Chat Respond node - emit a standardized chat-response envelope.

The shaper at the tail of a chat workflow. Takes whatever the upstream
nodes produced (an LLM answer, a retrieval-qa summary, an error
message) and wraps it in a stable envelope:

``{"role": str, "content": str, "session_id": str, "response_type":
str, "metadata": dict, "ts": str}``

The envelope is also the contract the future ``trigger_chat`` node
will consume for its streamed/polled response endpoint - nailing it
down now means that trigger can land as a pure plumbing slice later.

Content resolution precedence:

1. ``content`` parameter, if non-empty after expression resolution.
2. Otherwise, the value at ``content_field`` on the input item.
3. Otherwise, the empty string.

This lets users either hard-code a response (``strict`` error paths)
or thread an LLM's answer through by field name, without a branching
Set node.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar

from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.node_spec import (
    NodeCategory,
    NodeSpec,
    PropertyOption,
    PropertySchema,
)
from weftlyflow.nodes.base import BaseNode

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

ROLE_ASSISTANT: str = "assistant"
ROLE_SYSTEM: str = "system"
ROLE_TOOL: str = "tool"
_SUPPORTED_ROLES: frozenset[str] = frozenset(
    {ROLE_ASSISTANT, ROLE_SYSTEM, ROLE_TOOL},
)

TYPE_MESSAGE: str = "message"
TYPE_FINAL: str = "final"
TYPE_ERROR: str = "error"
_SUPPORTED_TYPES: frozenset[str] = frozenset(
    {TYPE_MESSAGE, TYPE_FINAL, TYPE_ERROR},
)

_DEFAULT_CONTENT_FIELD: str = "content"
_DEFAULT_SESSION_FIELD: str = "session_id"


class ChatRespondNode(BaseNode):
    """Terminator for chat workflows - wrap the reply in a stable envelope."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.chat_respond",
        version=1,
        display_name="Chat: Respond",
        description=(
            "Emit a standardised chat-response envelope at the end of "
            "a chat workflow."
        ),
        icon="icons/chat-respond.svg",
        category=NodeCategory.AI,
        group=["ai", "chat"],
        properties=[
            PropertySchema(
                name="content",
                display_name="Content",
                type="string",
                description=(
                    "Literal or expression-resolved response text. "
                    "Leave empty to pull from 'Content Field' instead."
                ),
            ),
            PropertySchema(
                name="content_field",
                display_name="Content Field",
                type="string",
                default=_DEFAULT_CONTENT_FIELD,
                description=(
                    "JSON key used when 'Content' is empty. Default "
                    "pairs with LLM node output shapes."
                ),
            ),
            PropertySchema(
                name="role",
                display_name="Role",
                type="options",
                default=ROLE_ASSISTANT,
                options=[
                    PropertyOption(value=ROLE_ASSISTANT, label="Assistant"),
                    PropertyOption(value=ROLE_SYSTEM, label="System"),
                    PropertyOption(value=ROLE_TOOL, label="Tool"),
                ],
            ),
            PropertySchema(
                name="session_id_field",
                display_name="Session ID Field",
                type="string",
                default=_DEFAULT_SESSION_FIELD,
                description="JSON key used to copy the session id through.",
            ),
            PropertySchema(
                name="response_type",
                display_name="Response Type",
                type="options",
                default=TYPE_MESSAGE,
                options=[
                    PropertyOption(value=TYPE_MESSAGE, label="Message"),
                    PropertyOption(value=TYPE_FINAL, label="Final"),
                    PropertyOption(value=TYPE_ERROR, label="Error"),
                ],
            ),
            PropertySchema(
                name="metadata",
                display_name="Metadata",
                type="json",
                description="Optional JSON object appended to the envelope.",
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Emit one envelope per input item (or a single empty-input envelope)."""
        seed = items or [Item()]
        return [[_respond_one(ctx, item) for item in seed]]


def _respond_one(ctx: ExecutionContext, item: Item) -> Item:
    params = ctx.resolved_params(item=item)
    role = str(params.get("role") or ROLE_ASSISTANT)
    if role not in _SUPPORTED_ROLES:
        msg = f"Chat Respond: unsupported role {role!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    response_type = str(params.get("response_type") or TYPE_MESSAGE)
    if response_type not in _SUPPORTED_TYPES:
        msg = f"Chat Respond: unsupported response_type {response_type!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)

    source = item.json if isinstance(item.json, dict) else {}
    content = _resolve_content(params, source)
    session_id = _resolve_session_id(params, source)
    metadata = _coerce_metadata(params.get("metadata"), ctx)

    return Item(
        json={
            "role": role,
            "content": content,
            "session_id": session_id,
            "response_type": response_type,
            "metadata": metadata,
            "ts": datetime.now(UTC).isoformat(),
        },
        binary=item.binary,
        paired_item=item.paired_item,
        error=item.error,
    )


def _resolve_content(params: dict[str, Any], source: dict[str, Any]) -> str:
    override = params.get("content")
    if isinstance(override, str) and override != "":
        return override
    if override not in (None, ""):
        return str(override)
    field = str(params.get("content_field") or _DEFAULT_CONTENT_FIELD)
    raw = source.get(field, "")
    return raw if isinstance(raw, str) else str(raw)


def _resolve_session_id(
    params: dict[str, Any], source: dict[str, Any],
) -> str:
    field = str(params.get("session_id_field") or _DEFAULT_SESSION_FIELD)
    raw = source.get(field, "")
    return raw if isinstance(raw, str) else str(raw)


def _coerce_metadata(raw: Any, ctx: ExecutionContext) -> dict[str, Any]:
    if raw is None or raw == "":
        return {}
    if not isinstance(raw, dict):
        msg = "Chat Respond: 'metadata' must be a JSON object"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return dict(raw)
