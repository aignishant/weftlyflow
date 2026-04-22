"""Webhook lifecycle + HTTP routing.

Four layers:
    constants.py : shared strings (URL prefixes, method tuple, response modes).
    types.py     : plain :class:`WebhookEntry` + :class:`ParsedRequest` dataclasses.
    paths.py     : normalise / generate URL paths.
    registry.py  : in-memory table of ``(path, method)`` → :class:`WebhookEntry`.
    parser.py    : transform a FastAPI request into a :class:`ParsedRequest`.
    handler.py   : hand a matched request to the execution queue.

Leader-follower coordination for external-service webhook installation is in
:mod:`weftlyflow.triggers.manager`; this package is concerned only with the
request path once a webhook is registered locally.

See IMPLEMENTATION_BIBLE.md §12.
"""

from __future__ import annotations

from weftlyflow.webhooks.registry import (
    UnsupportedMethodError,
    WebhookConflictError,
    WebhookRegistry,
    entry_from_entity,
)
from weftlyflow.webhooks.types import ParsedRequest, WebhookEntry

__all__ = [
    "ParsedRequest",
    "UnsupportedMethodError",
    "WebhookConflictError",
    "WebhookEntry",
    "WebhookRegistry",
    "entry_from_entity",
]
