"""Plain data types passed around the webhook layer.

Kept free of any IO dependency so both the in-memory registry and the
async ingress handler can share them without import cycles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True, frozen=True)
class WebhookEntry:
    """One active registration, fully indexed for fast lookup.

    Attributes:
        id: ``wh_<ulid>`` — identifier of the row in the ``webhooks`` table.
        workflow_id: The workflow this webhook belongs to.
        node_id: The trigger node inside the workflow.
        project_id: Owning project — carried forward to the execution row.
        path: The stored URL path, without leading slash.
        method: Uppercased HTTP method.
        is_dynamic: True when the path was auto-generated (UUID-based).
        response_mode: How the ingress handler replies to the caller.
    """

    id: str
    workflow_id: str
    node_id: str
    project_id: str
    path: str
    method: str
    is_dynamic: bool = False
    response_mode: str = "immediately"


@dataclass(slots=True)
class ParsedRequest:
    """Request shape that the webhook-trigger node emits as its first item.

    Mirrors the intuition of ``request`` objects in other automation tools:
    callers' code downstream of the trigger reads ``$json.body`` / ``$json.query``
    in an expression and gets what they typed into curl.

    Attributes:
        method: HTTP verb as received by the server.
        path: URL path the request hit (stored format, leading slash stripped).
        headers: Lower-cased header name → value. Multi-valued headers are joined
            with a comma per RFC 9110.
        query: Flat query-string view. Repeated keys keep the last value to
            match the JSON-friendly output shape; use ``query_all`` for arrays.
        query_all: Query-string view that preserves list values.
        body: Parsed JSON body if ``Content-Type`` is JSON; otherwise the raw
            decoded text under the ``raw`` key.
    """

    method: str
    path: str
    headers: dict[str, str] = field(default_factory=dict)
    query: dict[str, str] = field(default_factory=dict)
    query_all: dict[str, list[str]] = field(default_factory=dict)
    body: Any = None
