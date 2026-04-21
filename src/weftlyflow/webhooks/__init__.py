"""Webhook lifecycle + HTTP routing.

Three layers (populated in Phase 3):
    registry.py : in-memory + DB-backed mapping of ``(path, method)`` → workflow+node.
    router.py   : match an incoming request against the registry.
    handler.py  : parse request into an :class:`Item`, enqueue execution.
    waiting.py  : resume an execution paused at a Wait node.

Leader-follower coordination is in :mod:`weftlyflow.triggers.manager`; this
package is concerned only with the request path once a webhook is registered.

See IMPLEMENTATION_BIBLE.md §12.
"""

from __future__ import annotations
