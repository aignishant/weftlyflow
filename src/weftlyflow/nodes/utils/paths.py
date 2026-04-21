"""Dotted-path access helpers over JSON-like ``dict[str, Any]`` payloads.

Used by the Set node for add/remove operations and by any future node that
wants to address nested fields with a user-supplied path like
``"user.address.city"``.

Behavioural contract:

* Paths are split on ``.``; empty components are rejected.
* Missing intermediate keys cause reads to return a caller-supplied default and
  writes to lazily create dict segments.
* Integer-looking segments are treated as list indices **only** if the current
  level is already a list; this avoids surprising dict-vs-list ambiguity on
  writes.
"""

from __future__ import annotations

from typing import Any

_MISSING: object = object()


def get_path(data: dict[str, Any], path: str, default: Any = None) -> Any:
    """Return the value at ``path`` inside ``data`` or ``default`` if absent.

    Example:
        >>> get_path({"user": {"name": "Ada"}}, "user.name")
        'Ada'
        >>> get_path({}, "missing", default="fallback")
        'fallback'
    """
    segments = _split(path)
    current: Any = data
    for segment in segments:
        current = _descend(current, segment, default=_MISSING)
        if current is _MISSING:
            return default
    return current


def set_path(data: dict[str, Any], path: str, value: Any) -> None:
    """Write ``value`` at ``path`` inside ``data``, creating dicts as needed.

    Only dicts are auto-created along the way; writing into a pre-existing list
    requires a valid integer index.

    Example:
        >>> d: dict[str, Any] = {}
        >>> set_path(d, "a.b.c", 1)
        >>> d
        {'a': {'b': {'c': 1}}}
    """
    segments = _split(path)
    current: Any = data
    for segment in segments[:-1]:
        nxt = _descend(current, segment, default=_MISSING)
        if nxt is _MISSING or not isinstance(nxt, dict):
            nxt = {}
            _assign(current, segment, nxt)
        current = nxt
    _assign(current, segments[-1], value)


def del_path(data: dict[str, Any], path: str) -> bool:
    """Remove ``path`` from ``data``; returns True if anything was deleted."""
    segments = _split(path)
    current: Any = data
    for segment in segments[:-1]:
        nxt = _descend(current, segment, default=_MISSING)
        if nxt is _MISSING:
            return False
        current = nxt
    return _delete(current, segments[-1])


def _split(path: str) -> list[str]:
    if not path:
        msg = "path must be a non-empty string"
        raise ValueError(msg)
    segments = path.split(".")
    if any(not s for s in segments):
        msg = f"path contains empty segment: {path!r}"
        raise ValueError(msg)
    return segments


def _descend(container: Any, segment: str, *, default: Any) -> Any:
    if isinstance(container, dict):
        return container.get(segment, default)
    if isinstance(container, list) and segment.lstrip("-").isdigit():
        idx = int(segment)
        if -len(container) <= idx < len(container):
            return container[idx]
        return default
    return default


def _assign(container: Any, segment: str, value: Any) -> None:
    if isinstance(container, dict):
        container[segment] = value
        return
    if isinstance(container, list) and segment.lstrip("-").isdigit():
        idx = int(segment)
        if -len(container) <= idx < len(container):
            container[idx] = value
            return
    msg = f"cannot assign into {type(container).__name__} at segment {segment!r}"
    raise TypeError(msg)


def _delete(container: Any, segment: str) -> bool:
    if isinstance(container, dict) and segment in container:
        del container[segment]
        return True
    if isinstance(container, list) and segment.lstrip("-").isdigit():
        idx = int(segment)
        if -len(container) <= idx < len(container):
            del container[idx]
            return True
    return False
