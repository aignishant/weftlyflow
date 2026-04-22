"""Shared constants for the Slack integration node.

Centralising API endpoint paths, operation slugs, and default timeouts keeps
:mod:`weftlyflow.nodes.integrations.slack.node` declarative and the
operation dispatcher in :mod:`weftlyflow.nodes.integrations.slack.operations`
free of magic strings.

Primary reference: https://api.slack.com/methods.
"""

from __future__ import annotations

from typing import Final

API_BASE_URL: Final[str] = "https://slack.com/api"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_POST_MESSAGE: Final[str] = "post_message"
OP_UPDATE_MESSAGE: Final[str] = "update_message"
OP_DELETE_MESSAGE: Final[str] = "delete_message"
OP_LIST_CHANNELS: Final[str] = "list_channels"
OP_GET_CHANNEL_HISTORY: Final[str] = "get_channel_history"
OP_ADD_REACTION: Final[str] = "add_reaction"
OP_LIST_USERS: Final[str] = "list_users"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_POST_MESSAGE,
    OP_UPDATE_MESSAGE,
    OP_DELETE_MESSAGE,
    OP_LIST_CHANNELS,
    OP_GET_CHANNEL_HISTORY,
    OP_ADD_REACTION,
    OP_LIST_USERS,
)

ENDPOINT_BY_OPERATION: Final[dict[str, str]] = {
    OP_POST_MESSAGE: "chat.postMessage",
    OP_UPDATE_MESSAGE: "chat.update",
    OP_DELETE_MESSAGE: "chat.delete",
    OP_LIST_CHANNELS: "conversations.list",
    OP_GET_CHANNEL_HISTORY: "conversations.history",
    OP_ADD_REACTION: "reactions.add",
    OP_LIST_USERS: "users.list",
}

CHANNEL_TYPE_PUBLIC: Final[str] = "public_channel"
CHANNEL_TYPE_PRIVATE: Final[str] = "private_channel"
CHANNEL_TYPE_DM: Final[str] = "im"
CHANNEL_TYPE_MPIM: Final[str] = "mpim"

DEFAULT_LIST_LIMIT: Final[int] = 100
MAX_LIST_LIMIT: Final[int] = 1000
