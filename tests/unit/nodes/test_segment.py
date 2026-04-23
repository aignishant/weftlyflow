"""Unit tests for :class:`SegmentNode` and ``SegmentWriteKeyCredential``.

Exercises Segment's distinctive HTTP Basic auth with the write key as
the username and an **empty password** — the wire shape is
``Authorization: Basic base64("WRITE_KEY:")`` — and the five verb
endpoints (``track``/``identify``/``group``/``page``/``alias``) each
with its verb-specific body shape.
"""

from __future__ import annotations

import base64
import json

import httpx
import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import SegmentWriteKeyCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.segment import SegmentNode
from weftlyflow.nodes.integrations.segment.operations import build_request

_CRED_ID: str = "cr_segment"
_PROJECT_ID: str = "pr_test"
_KEY: str = "wkey_abc123"
_API: str = "https://api.segment.io"


def _resolver(*, key: str = _KEY) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.segment_write_key": SegmentWriteKeyCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.segment_write_key",
                {"write_key": key},
                _PROJECT_ID,
            ),
        },
    )


def _ctx_for(
    node: Node,
    *,
    resolver: InMemoryCredentialResolver | None = None,
) -> ExecutionContext:
    wf = build_workflow([node], [], project_id=_PROJECT_ID)
    return ExecutionContext(
        workflow=wf,
        execution_id="ex_test",
        mode="manual",
        node=node,
        inputs={"main": []},
        credential_resolver=resolver or _resolver(),
    )


# --- credential: empty-password Basic auth --------------------------


async def test_credential_inject_basic_auth_with_empty_password() -> None:
    request = httpx.Request("POST", f"{_API}/v1/track")
    out = await SegmentWriteKeyCredential().inject(
        {"write_key": _KEY}, request,
    )
    expected = "Basic " + base64.b64encode(f"{_KEY}:".encode()).decode("ascii")
    assert out.headers["Authorization"] == expected
    # Crucially — the colon MUST be present. A common bug is encoding
    # just the key; Segment rejects that.
    decoded = base64.b64decode(
        out.headers["Authorization"].removeprefix("Basic "),
    ).decode("ascii")
    assert decoded.endswith(":")


# --- track ----------------------------------------------------------


@respx.mock
async def test_track_posts_event_envelope() -> None:
    route = respx.post(f"{_API}/v1/track").mock(
        return_value=Response(200, json={"success": True}),
    )
    node = Node(
        id="node_1",
        name="Segment",
        type="weftlyflow.segment",
        parameters={
            "operation": "track",
            "userId": "u_123",
            "event": "Signed Up",
            "properties": {"plan": "pro"},
        },
        credentials={"segment_write_key": _CRED_ID},
    )
    await SegmentNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "userId": "u_123",
        "event": "Signed Up",
        "properties": {"plan": "pro"},
    }


def test_track_requires_event() -> None:
    with pytest.raises(ValueError, match="'event' is required"):
        build_request("track", {"userId": "u1"})


def test_identity_requires_user_or_anonymous_id() -> None:
    with pytest.raises(ValueError, match="'userId' or 'anonymousId'"):
        build_request("track", {"event": "X"})


@respx.mock
async def test_track_supports_anonymous_id_alone() -> None:
    route = respx.post(f"{_API}/v1/track").mock(
        return_value=Response(200, json={"success": True}),
    )
    node = Node(
        id="node_1",
        name="Segment",
        type="weftlyflow.segment",
        parameters={
            "operation": "track",
            "anonymousId": "anon_99",
            "event": "Viewed",
        },
        credentials={"segment_write_key": _CRED_ID},
    )
    await SegmentNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"anonymousId": "anon_99", "event": "Viewed"}


# --- identify / group / page / alias -------------------------------


@respx.mock
async def test_identify_posts_traits() -> None:
    route = respx.post(f"{_API}/v1/identify").mock(
        return_value=Response(200, json={"success": True}),
    )
    node = Node(
        id="node_1",
        name="Segment",
        type="weftlyflow.segment",
        parameters={
            "operation": "identify",
            "userId": "u_1",
            "traits": {"email": "a@b.c"},
        },
        credentials={"segment_write_key": _CRED_ID},
    )
    await SegmentNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"userId": "u_1", "traits": {"email": "a@b.c"}}


@respx.mock
async def test_group_requires_group_id() -> None:
    respx.post(f"{_API}/v1/group").mock(
        return_value=Response(200, json={"success": True}),
    )
    node = Node(
        id="node_1",
        name="Segment",
        type="weftlyflow.segment",
        parameters={"operation": "group", "userId": "u_1"},
        credentials={"segment_write_key": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="'groupId' is required"):
        await SegmentNode().execute(_ctx_for(node), [Item()])


@respx.mock
async def test_page_forwards_name_and_properties() -> None:
    route = respx.post(f"{_API}/v1/page").mock(
        return_value=Response(200, json={"success": True}),
    )
    node = Node(
        id="node_1",
        name="Segment",
        type="weftlyflow.segment",
        parameters={
            "operation": "page",
            "userId": "u_1",
            "name": "Home",
            "category": "Marketing",
            "properties": {"path": "/"},
        },
        credentials={"segment_write_key": _CRED_ID},
    )
    await SegmentNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["name"] == "Home"
    assert body["category"] == "Marketing"
    assert body["properties"] == {"path": "/"}


@respx.mock
async def test_alias_requires_previous_id() -> None:
    respx.post(f"{_API}/v1/alias").mock(
        return_value=Response(200, json={"success": True}),
    )
    node = Node(
        id="node_1",
        name="Segment",
        type="weftlyflow.segment",
        parameters={"operation": "alias", "userId": "u_new"},
        credentials={"segment_write_key": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="'previousId' is required"):
        await SegmentNode().execute(_ctx_for(node), [Item()])


# --- errors --------------------------------------------------------


@respx.mock
async def test_api_error_is_parsed() -> None:
    respx.post(f"{_API}/v1/track").mock(
        return_value=Response(401, json={"message": "bad write key"}),
    )
    node = Node(
        id="node_1",
        name="Segment",
        type="weftlyflow.segment",
        parameters={"operation": "track", "userId": "u", "event": "E"},
        credentials={"segment_write_key": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="bad write key"):
        await SegmentNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Segment",
        type="weftlyflow.segment",
        parameters={"operation": "track", "userId": "u", "event": "E"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await SegmentNode().execute(_ctx_for(node), [Item()])


async def test_empty_write_key_raises() -> None:
    resolver = _resolver(key="")
    node = Node(
        id="node_1",
        name="Segment",
        type="weftlyflow.segment",
        parameters={"operation": "track", "userId": "u", "event": "E"},
        credentials={"segment_write_key": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="empty 'write_key'"):
        await SegmentNode().execute(_ctx_for(node, resolver=resolver), [Item()])


def test_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("nuke", {})
