"""Chat-trigger node — emits an inbound chat message as the workflow's seed item.

Partner to :class:`weftlyflow.nodes.ai.chat_respond.ChatRespondNode`. Where
``chat_respond`` terminates a chat workflow with a stable envelope,
``trigger_chat`` starts one: it accepts an inbound HTTP request that carries a
chat payload (``{"message": ..., "session_id": ..., "user_id": ...,
"history": ...}``) and flattens it into that same shape so downstream
expressions can read ``$json.message`` without traversing the raw request.

Transport-level registration (adding a row to the ``webhooks`` table,
installing the HTTP route) is delegated to
:class:`weftlyflow.triggers.manager.ActiveTriggerManager` — the chat trigger
reuses the standard webhook-registration machinery. The node itself only
unwraps the seed item at execution time.

The resolved shape on the wire matches the envelope consumed by
``chat_respond`` on the outbound side:

    ``{"message": str, "session_id": str, "user_id": str,
       "history": list[dict], "raw": dict}``

Fields missing from the inbound request are filled with empty defaults rather
than dropped, so downstream expression authors can rely on every key being
present.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from weftlyflow.domain.execution import Item
from weftlyflow.domain.node_spec import NodeCategory, NodeSpec, PropertySchema
from weftlyflow.domain.workflow import Port
from weftlyflow.nodes.base import BaseNode

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_REQUEST_KEY: str = "request"
_DEFAULT_MESSAGE_FIELD: str = "message"
_DEFAULT_SESSION_FIELD: str = "session_id"
_DEFAULT_USER_FIELD: str = "user_id"
_DEFAULT_HISTORY_FIELD: str = "history"


class ChatTriggerNode(BaseNode):
    """Start a workflow from an inbound chat request; forward the message as an item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.trigger_chat",
        version=1,
        display_name="Chat Trigger",
        description=(
            "Start the workflow when a chat message arrives at the "
            "registered path. Pairs with the Chat Respond node."
        ),
        icon="icons/chat-trigger.svg",
        category=NodeCategory.TRIGGER,
        group=["trigger", "ai", "chat"],
        inputs=[],
        outputs=[Port(name="main")],
        properties=[
            PropertySchema(
                name="path",
                display_name="Path",
                type="string",
                default="",
                description=(
                    "Path suffix this chat endpoint listens on. Leave "
                    "empty to use the workflow/node id."
                ),
            ),
            PropertySchema(
                name="message_field",
                display_name="Message Field",
                type="string",
                default=_DEFAULT_MESSAGE_FIELD,
                description="Key in the request body that carries the user's message.",
            ),
            PropertySchema(
                name="session_id_field",
                display_name="Session ID Field",
                type="string",
                default=_DEFAULT_SESSION_FIELD,
                description="Key in the request body carrying the chat session id.",
            ),
            PropertySchema(
                name="user_id_field",
                display_name="User ID Field",
                type="string",
                default=_DEFAULT_USER_FIELD,
                description="Key in the request body identifying the end user.",
            ),
            PropertySchema(
                name="history_field",
                display_name="History Field",
                type="string",
                default=_DEFAULT_HISTORY_FIELD,
                description=(
                    "Key in the request body carrying prior turns (a list "
                    "of ``{role, content}`` dicts). Optional."
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Unwrap the seeded chat request into an ergonomic ``{message, session_id, ...}`` shape."""
        params = ctx.resolved_params()
        message_field = str(params.get("message_field") or _DEFAULT_MESSAGE_FIELD)
        session_field = str(params.get("session_id_field") or _DEFAULT_SESSION_FIELD)
        user_field = str(params.get("user_id_field") or _DEFAULT_USER_FIELD)
        history_field = str(params.get("history_field") or _DEFAULT_HISTORY_FIELD)
        outputs: list[Item] = [
            _flatten_chat_item(
                item,
                message_field=message_field,
                session_field=session_field,
                user_field=user_field,
                history_field=history_field,
            )
            for item in items
        ]
        return [outputs]


def _flatten_chat_item(
    item: Item,
    *,
    message_field: str,
    session_field: str,
    user_field: str,
    history_field: str,
) -> Item:
    body = _extract_body(item.json)
    flattened = {
        "message": _coerce_str(body.get(message_field, "")),
        "session_id": _coerce_str(body.get(session_field, "")),
        "user_id": _coerce_str(body.get(user_field, "")),
        "history": _coerce_history(body.get(history_field)),
        "raw": body,
    }
    return Item(
        json=flattened,
        binary=item.binary,
        paired_item=item.paired_item,
        error=item.error,
    )


def _extract_body(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    request = payload.get(_REQUEST_KEY)
    if isinstance(request, dict):
        body = request.get("body")
        return body if isinstance(body, dict) else {}
    return payload


def _coerce_str(value: Any) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def _coerce_history(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [turn for turn in value if isinstance(turn, dict)]
