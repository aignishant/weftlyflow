"""Session-keyed chat-history store backed by workflow static data.

Memory nodes (``memory_buffer``, ``memory_window``) share a single
logical store: both keys under ``static_data["_memory"][session_id]``.
A workflow that alternates between a buffer-writer and a window-reader
for the same ``session_id`` therefore sees one continuous conversation
— which matches the intuition of "memory" as a scalar per-session
resource rather than a per-node resource.

The store is deliberately structure-agnostic. Callers append whatever
dicts make sense for their use case; the most common shape is
``{"role": "user" | "assistant" | "system", "content": "..."}`` so
messages can be fed straight into an LLM node's ``messages`` parameter.

All functions are pure with respect to their arguments: they read and
write the ``static_data`` dict you pass in, so unit tests can exercise
them without constructing an :class:`ExecutionContext`.
"""

from __future__ import annotations

from typing import Any, Final

MEMORY_NAMESPACE: Final[str] = "_memory"
"""Top-level static-data key under which all session histories live.

The underscore prefix keeps this out of user-facing expression reach
(``$workflow.static_data._memory`` is an explicit opt-in rather than
something you stumble into).
"""

MEMORY_SUMMARY_NAMESPACE: Final[str] = "_memory_summary"
"""Top-level static-data key for the ``memory_summary`` node's state.

Separate from :data:`MEMORY_NAMESPACE` because the stored shape is
``{"summary": str, "messages": list[dict]}`` rather than a plain list
— buffer/window and summary therefore do not share a backing store,
which matches the rolling-summary mental model (summary is a distinct
resource from raw chat history).
"""


def _sessions(static_data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Return the mutable session-keyed dict, creating it on first access."""
    bucket = static_data.get(MEMORY_NAMESPACE)
    if not isinstance(bucket, dict):
        bucket = {}
        static_data[MEMORY_NAMESPACE] = bucket
    return bucket


def load_history(
    static_data: dict[str, Any],
    session_id: str,
) -> list[dict[str, Any]]:
    """Return a **copy** of the message list for ``session_id``.

    Returning a copy — rather than the live list — prevents accidental
    mutation of the stored history by a downstream node that receives
    this output.

    Args:
        static_data: The execution's ``ctx.static_data`` dict.
        session_id: User-supplied conversation key.

    Returns:
        Empty list when no history exists; otherwise a shallow copy of
        the stored messages.
    """
    sessions = _sessions(static_data)
    stored = sessions.get(session_id)
    if not isinstance(stored, list):
        return []
    return [dict(msg) if isinstance(msg, dict) else msg for msg in stored]


def append_history(
    static_data: dict[str, Any],
    session_id: str,
    new_messages: list[dict[str, Any]],
    *,
    max_len: int | None = None,
) -> list[dict[str, Any]]:
    """Append ``new_messages`` to ``session_id`` and return the new full history.

    Args:
        static_data: The execution's ``ctx.static_data`` dict.
        session_id: Conversation key.
        new_messages: Dicts to append. An empty list is a no-op that still
            returns the current history — useful when a caller wants to
            conditionally extend without branching.
        max_len: When set, trim to the last ``max_len`` messages after
            append. The :class:`~weftlyflow.nodes.ai.memory_window` node
            uses this to enforce a sliding window.

    Returns:
        A copy of the post-append history (same semantics as
        :func:`load_history`).

    Raises:
        ValueError: when ``max_len`` is non-positive.
    """
    if max_len is not None and max_len < 1:
        msg = f"max_len must be >= 1, got {max_len}"
        raise ValueError(msg)
    sessions = _sessions(static_data)
    stored = sessions.get(session_id)
    current: list[dict[str, Any]] = list(stored) if isinstance(stored, list) else []
    current.extend(new_messages)
    if max_len is not None and len(current) > max_len:
        current = current[-max_len:]
    sessions[session_id] = current
    return [dict(msg) if isinstance(msg, dict) else msg for msg in current]


def clear_history(static_data: dict[str, Any], session_id: str) -> None:
    """Drop the session's history. Missing sessions are silently ignored."""
    sessions = _sessions(static_data)
    sessions.pop(session_id, None)


# --- memory_summary helpers -----------------------------------------------


def _summary_sessions(
    static_data: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Return the mutable summary-session dict, creating it on first access."""
    bucket = static_data.get(MEMORY_SUMMARY_NAMESPACE)
    if not isinstance(bucket, dict):
        bucket = {}
        static_data[MEMORY_SUMMARY_NAMESPACE] = bucket
    return bucket


def _summary_slot(
    sessions: dict[str, dict[str, Any]],
    session_id: str,
) -> dict[str, Any]:
    stored = sessions.get(session_id)
    if not isinstance(stored, dict):
        return {"summary": "", "messages": []}
    summary = stored.get("summary")
    messages = stored.get("messages")
    return {
        "summary": summary if isinstance(summary, str) else "",
        "messages": list(messages) if isinstance(messages, list) else [],
    }


def load_summary(
    static_data: dict[str, Any],
    session_id: str,
) -> tuple[str, list[dict[str, Any]]]:
    """Return ``(summary, messages)`` for ``session_id``.

    Both are returned as defensive copies (summary is a ``str`` so it's
    naturally immutable; the messages list is copied). Missing sessions
    resolve to ``("", [])``.
    """
    slot = _summary_slot(_summary_sessions(static_data), session_id)
    messages = [dict(msg) if isinstance(msg, dict) else msg for msg in slot["messages"]]
    return slot["summary"], messages


def append_summary_messages(
    static_data: dict[str, Any],
    session_id: str,
    new_messages: list[dict[str, Any]],
    *,
    max_messages: int,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    """Append messages; when the total exceeds ``max_messages``, overflow falls off.

    Args:
        static_data: The execution's ``ctx.static_data`` dict.
        session_id: Conversation key.
        new_messages: Messages to append.
        max_messages: Retention cap for the tail. Must be >= 1.

    Returns:
        ``(summary, messages, overflow)``:

        * ``summary`` — current summary string (unchanged by this call).
        * ``messages`` — the retained tail (up to ``max_messages``).
        * ``overflow`` — the oldest messages that fell off, in chronological
          order. Callers typically feed these to an LLM to produce an
          updated summary, then call :func:`replace_summary`.

    Raises:
        ValueError: when ``max_messages`` is non-positive.
    """
    if max_messages < 1:
        msg = f"max_messages must be >= 1, got {max_messages}"
        raise ValueError(msg)
    sessions = _summary_sessions(static_data)
    slot = _summary_slot(sessions, session_id)
    combined = slot["messages"] + list(new_messages)
    overflow: list[dict[str, Any]] = []
    if len(combined) > max_messages:
        cut = len(combined) - max_messages
        overflow = combined[:cut]
        combined = combined[cut:]
    sessions[session_id] = {"summary": slot["summary"], "messages": combined}
    retained = [dict(msg) if isinstance(msg, dict) else msg for msg in combined]
    overflow_copy = [dict(msg) if isinstance(msg, dict) else msg for msg in overflow]
    return slot["summary"], retained, overflow_copy


def replace_summary(
    static_data: dict[str, Any],
    session_id: str,
    summary: str,
) -> tuple[str, list[dict[str, Any]]]:
    """Replace the stored summary text for ``session_id``.

    Leaves the retained messages untouched. Returns the new
    ``(summary, messages)`` so callers can echo the state in their
    output item without a separate read.
    """
    sessions = _summary_sessions(static_data)
    slot = _summary_slot(sessions, session_id)
    sessions[session_id] = {"summary": summary, "messages": slot["messages"]}
    messages = [dict(msg) if isinstance(msg, dict) else msg for msg in slot["messages"]]
    return summary, messages


def clear_summary(static_data: dict[str, Any], session_id: str) -> None:
    """Drop the summary session. Missing sessions are silently ignored."""
    sessions = _summary_sessions(static_data)
    sessions.pop(session_id, None)
