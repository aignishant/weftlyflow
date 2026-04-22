"""HTTP Request node — issues an outbound HTTP call, emits the response.

The canonical Weftlyflow demo: use expressions (``{{ $json.id }}``) in the URL,
use a credential from the Credentials panel, and see the response JSON as
the next item in the workflow.

Parameters (all expression-capable):

* ``url``        — target URL (required).
* ``method``     — HTTP verb (default ``GET``).
* ``headers``    — ``dict[str, str]`` appended to the request.
* ``query``      — ``dict[str, str]`` merged into the query string.
* ``body``       — JSON-serialisable payload; sent verbatim when ``body_type``
  is ``"json"`` or form-encoded when it is ``"form"``; wrapped as
  ``{"raw": ...}`` text otherwise.
* ``body_type``  — one of ``"json"``, ``"form"``, ``"text"``, ``"none"``.
* ``timeout``    — seconds (default 30).
* ``response_format`` — ``"json"`` (parse on success) or ``"text"``.

Credentials:

* slot ``"auth"`` — optional; if present the credential type's
  :meth:`inject` is called on the request before it's sent.

Output:

* One item per input item containing ``status_code``, ``headers`` (dict),
  and ``body`` (parsed per ``response_format``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import httpx

from weftlyflow.domain.execution import Item
from weftlyflow.domain.node_spec import (
    CredentialSlot,
    NodeCategory,
    NodeSpec,
    PropertyOption,
    PropertySchema,
)
from weftlyflow.nodes.base import BaseNode

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext


_DEFAULT_TIMEOUT_SECONDS: float = 30.0
_METHODS: tuple[str, ...] = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")
_BODY_TYPES: tuple[str, ...] = ("none", "json", "form", "text")
_RESPONSE_FORMATS: tuple[str, ...] = ("json", "text")


class HttpRequestNode(BaseNode):
    """Make an outbound HTTP request and emit the response as the output item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.http_request",
        version=1,
        display_name="HTTP Request",
        description="Issue an HTTP request with optional credentials and expression URL.",
        icon="icons/http-request.svg",
        category=NodeCategory.CORE,
        group=["core", "http"],
        credentials=[
            CredentialSlot(
                name="auth",
                required=False,
                credential_types=[
                    "weftlyflow.bearer_token",
                    "weftlyflow.basic_auth",
                    "weftlyflow.api_key_header",
                    "weftlyflow.api_key_query",
                    "weftlyflow.oauth2_generic",
                ],
            ),
        ],
        properties=[
            PropertySchema(name="url", display_name="URL", type="string", required=True),
            PropertySchema(
                name="method",
                display_name="Method",
                type="options",
                default="GET",
                options=[PropertyOption(value=m, label=m) for m in _METHODS],
            ),
            PropertySchema(
                name="headers", display_name="Headers", type="json", default={},
            ),
            PropertySchema(
                name="query", display_name="Query parameters", type="json", default={},
            ),
            PropertySchema(
                name="body_type",
                display_name="Body type",
                type="options",
                default="none",
                options=[PropertyOption(value=b, label=b) for b in _BODY_TYPES],
            ),
            PropertySchema(name="body", display_name="Body", type="json", default=None),
            PropertySchema(
                name="timeout",
                display_name="Timeout (s)",
                type="number",
                default=_DEFAULT_TIMEOUT_SECONDS,
            ),
            PropertySchema(
                name="response_format",
                display_name="Response format",
                type="options",
                default="json",
                options=[PropertyOption(value=f, label=f) for f in _RESPONSE_FORMATS],
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one HTTP request per input item and emit the response."""
        seed = items or [Item()]
        results: list[Item] = []
        timeout = float(ctx.param("timeout", _DEFAULT_TIMEOUT_SECONDS) or _DEFAULT_TIMEOUT_SECONDS)
        async with httpx.AsyncClient(timeout=timeout) as client:
            for item in seed:
                results.append(await self._issue_one(ctx, item, client))
        return [results]

    async def _issue_one(
        self,
        ctx: ExecutionContext,
        item: Item,
        client: httpx.AsyncClient,
    ) -> Item:
        params = ctx.resolved_params(item=item)
        url = str(params.get("url") or "").strip()
        if not url:
            msg = "HTTP Request: url is required"
            raise ValueError(msg)
        method = str(params.get("method") or "GET").upper()
        if method not in _METHODS:
            msg = f"HTTP Request: unsupported method {method!r}"
            raise ValueError(msg)

        request = client.build_request(
            method=method,
            url=url,
            params=_coerce_mapping(params.get("query")) or None,
            headers=_coerce_mapping(params.get("headers")) or None,
            content=_build_body_content(params),
        )
        content_type = _content_type_for(params)
        if content_type is not None and "content-type" not in {
            k.lower() for k in request.headers
        }:
            request.headers["Content-Type"] = content_type

        credential = await ctx.load_credential("auth")
        if credential is not None:
            cred_type, payload = credential
            request = await cred_type.inject(payload, request)

        response = await client.send(request)
        body = _parse_response(response, str(params.get("response_format") or "json"))
        return Item(
            json={
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": body,
            },
        )


def _coerce_mapping(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(k): str(v) for k, v in value.items()}


def _build_body_content(params: dict[str, Any]) -> bytes | None:
    body_type = str(params.get("body_type") or "none").lower()
    body = params.get("body")
    if body_type == "none" or body is None:
        return None
    if body_type == "json":
        import json  # noqa: PLC0415 — stdlib lazy import keeps cold path cheap.

        return json.dumps(body).encode("utf-8")
    if body_type == "form":
        from urllib.parse import urlencode  # noqa: PLC0415

        if not isinstance(body, dict):
            msg = "HTTP Request: form body must be a dict"
            raise ValueError(msg)
        return urlencode({k: str(v) for k, v in body.items()}).encode("utf-8")
    if body_type == "text":
        return str(body).encode("utf-8")
    msg = f"HTTP Request: unknown body_type {body_type!r}"
    raise ValueError(msg)


def _content_type_for(params: dict[str, Any]) -> str | None:
    body_type = str(params.get("body_type") or "none").lower()
    if body_type == "json":
        return "application/json"
    if body_type == "form":
        return "application/x-www-form-urlencoded"
    if body_type == "text":
        return "text/plain; charset=utf-8"
    return None


def _parse_response(response: httpx.Response, response_format: str) -> Any:
    fmt = response_format.lower()
    if fmt == "text":
        return response.text
    if fmt == "json":
        try:
            return response.json()
        except ValueError:
            return {"raw": response.text}
    msg = f"HTTP Request: unknown response_format {response_format!r}"
    raise ValueError(msg)
