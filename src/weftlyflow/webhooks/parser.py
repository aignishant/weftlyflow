"""Parse an incoming FastAPI request into a :class:`ParsedRequest`.

Kept as a pure function so unit tests don't need an ASGI harness — callers
pass in the primitives (method, path, headers, raw body bytes, query MultiDict)
and get back the deterministic dataclass the ingress enqueues.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from weftlyflow.webhooks.types import ParsedRequest

if TYPE_CHECKING:
    from collections.abc import Iterable

_JSON_MARKERS = ("application/json", "+json")


def parse_request(
    *,
    method: str,
    path: str,
    headers: Iterable[tuple[str, str]],
    query_items: Iterable[tuple[str, str]],
    body: bytes,
) -> ParsedRequest:
    """Deterministically convert request primitives into a :class:`ParsedRequest`.

    The body is treated as JSON only when the ``Content-Type`` header claims
    so. Everything else is preserved as ``{"raw": "<utf-8 text>"}`` so a
    downstream node can decide what to do with it.
    """
    headers_dict = _collapse_headers(headers)
    query_all = _collect_query(query_items)
    query_flat = {key: values[-1] for key, values in query_all.items()}
    body_value = _parse_body(body, content_type=headers_dict.get("content-type", ""))
    return ParsedRequest(
        method=method.upper(),
        path=path,
        headers=headers_dict,
        query=query_flat,
        query_all=query_all,
        body=body_value,
    )


def _collapse_headers(headers: Iterable[tuple[str, str]]) -> dict[str, str]:
    collected: dict[str, list[str]] = {}
    for raw_name, value in headers:
        name = raw_name.lower()
        collected.setdefault(name, []).append(value)
    return {name: ", ".join(values) for name, values in collected.items()}


def _collect_query(items: Iterable[tuple[str, str]]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for key, value in items:
        out.setdefault(key, []).append(value)
    return out


def _parse_body(body: bytes, *, content_type: str) -> Any:
    if not body:
        return None
    ct_lower = content_type.lower()
    is_json = any(marker in ct_lower for marker in _JSON_MARKERS)
    if is_json:
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            # Fall through to raw — we'd rather expose a readable payload than
            # 400 on a body the user intended for debugging downstream.
            pass
    try:
        return {"raw": body.decode("utf-8")}
    except UnicodeDecodeError:
        return {"raw_bytes_length": len(body)}
