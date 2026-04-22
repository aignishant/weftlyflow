"""Unit tests for :class:`HttpRequestNode` using :mod:`respx` for HTTP mocks."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import BearerTokenCredential
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.core.http_request import HttpRequestNode


def _ctx_for(
    node: Node,
    inputs: list[Item] | None = None,
    *,
    resolver: InMemoryCredentialResolver | None = None,
) -> ExecutionContext:
    wf = build_workflow([node], [])
    return ExecutionContext(
        workflow=wf,
        execution_id="ex_test",
        mode="manual",
        node=node,
        inputs={"main": list(inputs or [])},
        credential_resolver=resolver,
    )


@respx.mock
async def test_http_request_get_returns_json_body() -> None:
    respx.get("https://api.example.com/users/42").mock(
        return_value=Response(200, json={"id": 42, "name": "alice"}),
    )
    node = Node(
        id="node_1",
        name="HTTP",
        type="weftlyflow.http_request",
        parameters={
            "url": "https://api.example.com/users/42",
            "method": "GET",
        },
    )
    out = await HttpRequestNode().execute(_ctx_for(node, [Item()]), [Item()])
    [result] = out[0]
    assert result.json["status_code"] == 200
    assert result.json["body"] == {"id": 42, "name": "alice"}


@respx.mock
async def test_http_request_resolves_url_expression_per_item() -> None:
    respx.get("https://api.example.com/users/1").mock(
        return_value=Response(200, json={"id": 1}),
    )
    respx.get("https://api.example.com/users/2").mock(
        return_value=Response(200, json={"id": 2}),
    )
    node = Node(
        id="node_1",
        name="HTTP",
        type="weftlyflow.http_request",
        parameters={"url": "https://api.example.com/users/{{ $json.id }}"},
    )
    inputs = [Item(json={"id": 1}), Item(json={"id": 2})]
    out = await HttpRequestNode().execute(_ctx_for(node, inputs), inputs)
    ids = [item.json["body"]["id"] for item in out[0]]
    assert ids == [1, 2]


@respx.mock
async def test_http_request_posts_json_body() -> None:
    route = respx.post("https://api.example.com/echo").mock(
        return_value=Response(201, json={"accepted": True}),
    )
    node = Node(
        id="node_1",
        name="HTTP",
        type="weftlyflow.http_request",
        parameters={
            "url": "https://api.example.com/echo",
            "method": "POST",
            "body_type": "json",
            "body": {"hello": "world"},
        },
    )
    out = await HttpRequestNode().execute(_ctx_for(node, [Item()]), [Item()])
    assert route.called
    req = route.calls.last.request
    assert req.content == b'{"hello": "world"}'
    assert req.headers["content-type"].startswith("application/json")
    assert out[0][0].json["status_code"] == 201


@respx.mock
async def test_http_request_injects_bearer_credential() -> None:
    route = respx.get("https://api.example.com/me").mock(
        return_value=Response(200, json={"ok": True}),
    )
    resolver = InMemoryCredentialResolver(
        types={"weftlyflow.bearer_token": BearerTokenCredential},
        rows={"cr_1": ("weftlyflow.bearer_token", {"token": "sekrit"}, "pr_test")},
    )
    node = Node(
        id="node_1",
        name="HTTP",
        type="weftlyflow.http_request",
        parameters={"url": "https://api.example.com/me"},
        credentials={"auth": "cr_1"},
    )
    await HttpRequestNode().execute(
        _ctx_for(node, [Item()], resolver=resolver), [Item()],
    )
    assert route.called
    assert route.calls.last.request.headers["authorization"] == "Bearer sekrit"


@respx.mock
async def test_http_request_missing_url_raises() -> None:
    node = Node(
        id="node_1",
        name="HTTP",
        type="weftlyflow.http_request",
        parameters={"url": ""},
    )
    with pytest.raises(ValueError, match="url is required"):
        await HttpRequestNode().execute(_ctx_for(node, [Item()]), [Item()])


@respx.mock
async def test_http_request_unknown_method_raises() -> None:
    node = Node(
        id="node_1",
        name="HTTP",
        type="weftlyflow.http_request",
        parameters={"url": "https://api.example.com/", "method": "BOGUS"},
    )
    with pytest.raises(ValueError, match="unsupported method"):
        await HttpRequestNode().execute(_ctx_for(node, [Item()]), [Item()])


@respx.mock
async def test_http_request_response_text_format() -> None:
    respx.get("https://api.example.com/text").mock(
        return_value=Response(200, text="hello"),
    )
    node = Node(
        id="node_1",
        name="HTTP",
        type="weftlyflow.http_request",
        parameters={
            "url": "https://api.example.com/text",
            "response_format": "text",
        },
    )
    out = await HttpRequestNode().execute(_ctx_for(node, [Item()]), [Item()])
    assert out[0][0].json["body"] == "hello"


@respx.mock
async def test_http_request_form_body_urlencodes() -> None:
    route = respx.post("https://api.example.com/form").mock(
        return_value=Response(200, json={"ok": True}),
    )
    node = Node(
        id="node_1",
        name="HTTP",
        type="weftlyflow.http_request",
        parameters={
            "url": "https://api.example.com/form",
            "method": "POST",
            "body_type": "form",
            "body": {"a": "1", "b": "two"},
        },
    )
    await HttpRequestNode().execute(_ctx_for(node, [Item()]), [Item()])
    assert route.called
    req = route.calls.last.request
    assert req.headers["content-type"].startswith("application/x-www-form-urlencoded")
    # urlencode may order differently; check both pairs present.
    assert b"a=1" in req.content
    assert b"b=two" in req.content
