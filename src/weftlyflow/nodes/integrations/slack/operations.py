"""Per-operation request builders for the Slack node.

Each ``build_*`` function takes the resolved parameter dict + (optional)
default channel from the credential payload, validates the inputs, and
returns the HTTP ``method``, endpoint path, and JSON body the Slack node
will send. Keeping the request construction here means
:class:`~weftlyflow.nodes.integrations.slack.node.SlackNode` stays a thin
dispatcher and each operation is unit-testable in isolation.

Every Slack Web API call is a POST to ``https://slack.com/api/<method>``
with a JSON body (we always set ``Content-Type: application/json``). See
https://api.slack.com/web#methods for the authoritative list.
"""

from __future__ import annotations

from typing import Any

from weftlyflow.nodes.integrations.slack.constants import (
    CHANNEL_TYPE_PRIVATE,
    CHANNEL_TYPE_PUBLIC,
    DEFAULT_LIST_LIMIT,
    ENDPOINT_BY_OPERATION,
    MAX_LIST_LIMIT,
    OP_DELETE_MESSAGE,
    OP_LIST_CHANNELS,
    OP_POST_MESSAGE,
    OP_UPDATE_MESSAGE,
)

RequestSpec = tuple[str, str, dict[str, Any]]
"""``(http_method, slack_method, json_body)`` returned by every builder."""


def build_request(
    operation: str,
    params: dict[str, Any],
    *,
    default_channel: str = "",
) -> RequestSpec:
    """Dispatch ``operation`` to its builder and return the request spec.

    Raises:
        ValueError: when the operation slug is unknown or required params
            are missing.
    """
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Slack: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params, default_channel=default_channel)


def _build_post_message(params: dict[str, Any], *, default_channel: str) -> RequestSpec:
    channel = _required_channel(params, default_channel=default_channel)
    text = str(params.get("text") or "").strip()
    blocks = params.get("blocks")
    if not text and not blocks:
        msg = "Slack: post_message requires 'text' or 'blocks'"
        raise ValueError(msg)
    body: dict[str, Any] = {"channel": channel}
    if text:
        body["text"] = text
    if blocks is not None:
        body["blocks"] = _coerce_blocks(blocks)
    thread_ts = str(params.get("thread_ts") or "").strip()
    if thread_ts:
        body["thread_ts"] = thread_ts
    if "as_markdown" in params:
        body["mrkdwn"] = bool(params.get("as_markdown"))
    if "unfurl_links" in params:
        body["unfurl_links"] = bool(params.get("unfurl_links"))
    return "POST", ENDPOINT_BY_OPERATION[OP_POST_MESSAGE], body


def _build_update_message(params: dict[str, Any], *, default_channel: str) -> RequestSpec:
    channel = _required_channel(params, default_channel=default_channel)
    ts = str(params.get("ts") or "").strip()
    if not ts:
        msg = "Slack: update_message requires 'ts' (the message timestamp)"
        raise ValueError(msg)
    text = str(params.get("text") or "").strip()
    blocks = params.get("blocks")
    if not text and not blocks:
        msg = "Slack: update_message requires 'text' or 'blocks'"
        raise ValueError(msg)
    body: dict[str, Any] = {"channel": channel, "ts": ts}
    if text:
        body["text"] = text
    if blocks is not None:
        body["blocks"] = _coerce_blocks(blocks)
    return "POST", ENDPOINT_BY_OPERATION[OP_UPDATE_MESSAGE], body


def _build_delete_message(params: dict[str, Any], *, default_channel: str) -> RequestSpec:
    channel = _required_channel(params, default_channel=default_channel)
    ts = str(params.get("ts") or "").strip()
    if not ts:
        msg = "Slack: delete_message requires 'ts' (the message timestamp)"
        raise ValueError(msg)
    body: dict[str, Any] = {"channel": channel, "ts": ts}
    return "POST", ENDPOINT_BY_OPERATION[OP_DELETE_MESSAGE], body


def _build_list_channels(params: dict[str, Any], *, default_channel: str) -> RequestSpec:
    del default_channel  # unused — list_channels ignores the default-channel hint.
    limit = _coerce_limit(params.get("limit"))
    types_raw = params.get("types")
    types_list = _coerce_channel_types(types_raw)
    body: dict[str, Any] = {"limit": limit, "types": ",".join(types_list)}
    cursor = str(params.get("cursor") or "").strip()
    if cursor:
        body["cursor"] = cursor
    if "exclude_archived" in params:
        body["exclude_archived"] = bool(params.get("exclude_archived"))
    return "POST", ENDPOINT_BY_OPERATION[OP_LIST_CHANNELS], body


def _required_channel(params: dict[str, Any], *, default_channel: str) -> str:
    channel = str(params.get("channel") or "").strip()
    if not channel:
        channel = default_channel.strip()
    if not channel:
        msg = "Slack: 'channel' is required (either on the node or the credential)"
        raise ValueError(msg)
    return channel


def _coerce_blocks(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [dict(b) for b in raw if isinstance(b, dict)]
    if isinstance(raw, dict):
        return [dict(raw)]
    msg = "Slack: 'blocks' must be a list of block objects"
    raise ValueError(msg)


def _coerce_limit(raw: Any) -> int:
    if raw is None or raw == "":
        return DEFAULT_LIST_LIMIT
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Slack: 'limit' must be an integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = "Slack: 'limit' must be >= 1"
        raise ValueError(msg)
    return min(value, MAX_LIST_LIMIT)


def _coerce_channel_types(raw: Any) -> list[str]:
    if raw is None or raw == "":
        return [CHANNEL_TYPE_PUBLIC]
    if isinstance(raw, str):
        items = [part.strip() for part in raw.split(",") if part.strip()]
    elif isinstance(raw, list):
        items = [str(p).strip() for p in raw if str(p).strip()]
    else:
        msg = "Slack: 'types' must be a string or a list of channel type slugs"
        raise ValueError(msg)
    if not items:
        return [CHANNEL_TYPE_PUBLIC]
    allowed = {CHANNEL_TYPE_PUBLIC, CHANNEL_TYPE_PRIVATE, "im", "mpim"}
    bad = [t for t in items if t not in allowed]
    if bad:
        msg = f"Slack: unknown channel types {bad!r}"
        raise ValueError(msg)
    return items


_BUILDERS: dict[str, Any] = {
    OP_POST_MESSAGE: _build_post_message,
    OP_UPDATE_MESSAGE: _build_update_message,
    OP_DELETE_MESSAGE: _build_delete_message,
    OP_LIST_CHANNELS: _build_list_channels,
}
