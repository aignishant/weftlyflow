"""``$``-prefixed proxy objects exposed inside expressions.

The proxies are deliberately small data wrappers — they return plain Python
values so users can treat them exactly like the underlying structures. We
do not expose full :class:`~weftlyflow.domain.execution.Item` instances
because:

* item fields like ``binary`` / ``paired_item`` shouldn't be part of the
  public expression surface until we have a hardened API for them;
* keeping the surface small makes the allow-list easier to audit.

Dicts exposed to expressions are wrapped in :class:`AttrDict` so
``$json.name`` works in addition to ``$json['name']`` — this matches the
intuition users bring from other automation tools.

Proxies live in this module so the :func:`build_proxies` factory is the
single place that decides what goes into the evaluator's globals dict.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from weftlyflow.domain.execution import Item


class AttrDict(dict):  # type: ignore[type-arg]
    """Dict subclass that exposes keys as attributes.

    Missing attributes raise ``AttributeError`` (not ``KeyError``) so the
    evaluator's error message is consistent with how users write templates.
    Nested dicts encountered during access are wrapped on the fly.
    """

    __slots__ = ()

    def __getattr__(self, name: str) -> Any:
        """Return ``self[name]``; wrap nested dicts/lists before returning."""
        try:
            value = self[name]
        except KeyError as exc:
            msg = f"{name!r}"
            raise AttributeError(msg) from exc
        return _wrap(value)

    def __setattr__(self, name: str, value: Any) -> None:
        """Write through to ``self[name]``."""
        self[name] = value

    def __delattr__(self, name: str) -> None:
        """Delete ``self[name]`` — raises AttributeError when missing."""
        try:
            del self[name]
        except KeyError as exc:
            msg = f"{name!r}"
            raise AttributeError(msg) from exc


def _wrap(value: Any) -> Any:
    if isinstance(value, AttrDict):
        return value
    if isinstance(value, dict):
        return AttrDict(value)
    if isinstance(value, list):
        return [_wrap(item) for item in value]
    return value


@dataclass(slots=True)
class InputProxy:
    """``$input`` — access the current node's input items."""

    _items: list[Item]

    def all(self) -> list[AttrDict]:
        """Return every input item's JSON payload."""
        return [AttrDict(item.json) for item in self._items]

    def first(self) -> AttrDict | None:
        """Return the first input item's JSON payload or ``None``."""
        return AttrDict(self._items[0].json) if self._items else None

    def last(self) -> AttrDict | None:
        """Return the last input item's JSON payload or ``None``."""
        return AttrDict(self._items[-1].json) if self._items else None

    def item(self, index: int) -> AttrDict | None:
        """Return the item at ``index`` (supports negative indexing)."""
        try:
            return AttrDict(self._items[index].json)
        except IndexError:
            return None

    def count(self) -> int:
        """Return the number of input items on port 0."""
        return len(self._items)


@dataclass(slots=True)
class WeftlyflowDateTime:
    """Tz-aware ``datetime`` wrapper exposing ergonomic chain-builders.

    Examples:
        >>> now = WeftlyflowDateTime.now()
        >>> now.plus(days=1).to_iso()  # doctest: +SKIP
        '2026-04-23T00:00:00+00:00'
    """

    _dt: datetime

    @classmethod
    def now(cls, tz: tzinfo = UTC) -> WeftlyflowDateTime:
        """Construct a proxy anchored at the current UTC instant."""
        return cls(_dt=datetime.now(tz))

    @classmethod
    def today(cls, tz: tzinfo = UTC) -> WeftlyflowDateTime:
        """Construct a proxy anchored at today 00:00 in ``tz``."""
        now = datetime.now(tz)
        return cls(_dt=now.replace(hour=0, minute=0, second=0, microsecond=0))

    def to_iso(self) -> str:
        """Return ISO-8601 string with timezone suffix."""
        return self._dt.isoformat()

    def to_epoch(self) -> float:
        """Return POSIX timestamp (seconds since epoch)."""
        return self._dt.timestamp()

    def plus(self, **kwargs: int) -> WeftlyflowDateTime:
        """Return a copy shifted forward by ``timedelta(**kwargs)``."""
        return WeftlyflowDateTime(_dt=self._dt + timedelta(**kwargs))

    def minus(self, **kwargs: int) -> WeftlyflowDateTime:
        """Return a copy shifted backward by ``timedelta(**kwargs)``."""
        return WeftlyflowDateTime(_dt=self._dt - timedelta(**kwargs))

    def format(self, fmt: str) -> str:
        """Return ``strftime(fmt)`` — exposed because common templating needs it."""
        return self._dt.strftime(fmt)

    def __str__(self) -> str:
        """Default string form is ISO-8601 so ``f"{$now}"`` works."""
        return self.to_iso()


def build_proxies(
    *,
    item: Item,
    inputs: list[Item],
    workflow_id: str,
    workflow_name: str,
    project_id: str,
    execution_id: str,
    execution_mode: str,
    env_vars: dict[str, str],
    user_vars: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the globals dict handed to :func:`weftlyflow.expression.sandbox.evaluate`.

    Kept as a plain function so tests can easily check the full set of
    names and values without constructing an :class:`ExecutionContext`.
    """
    return {
        "$json": AttrDict(item.json),
        "$binary": AttrDict(
            {name: _binary_view(ref) for name, ref in (item.binary or {}).items()},
        ),
        "$input": InputProxy(_items=list(inputs)),
        "$now": WeftlyflowDateTime.now(),
        "$today": WeftlyflowDateTime.today(),
        "$env": AttrDict(env_vars),
        "$vars": AttrDict(user_vars or {}),
        "$workflow": AttrDict(
            {"id": workflow_id, "name": workflow_name, "project_id": project_id},
        ),
        "$execution": AttrDict({"id": execution_id, "mode": execution_mode}),
    }


def _binary_view(ref: Any) -> dict[str, Any]:
    # Keep ``$binary`` a plain dict of metadata — never expose raw bytes to
    # the expression sandbox.
    return {
        "filename": getattr(ref, "filename", None),
        "mime_type": getattr(ref, "mime_type", None),
        "size_bytes": getattr(ref, "size_bytes", None),
    }


def filter_env(raw_env: dict[str, str], *, prefix: str = "WEFTLYFLOW_VAR_") -> dict[str, str]:
    """Keep only ``WEFTLYFLOW_VAR_*`` entries and strip the prefix.

    Every expression has access to ``$env``, but only to variables the
    operator explicitly exposed under the reserved prefix. This prevents
    accidental leakage of database URLs, keys, etc.
    """
    return {
        key[len(prefix) :]: value
        for key, value in raw_env.items()
        if key.startswith(prefix)
    }
