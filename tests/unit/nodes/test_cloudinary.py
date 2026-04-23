"""Unit tests for :class:`CloudinaryNode` and ``CloudinaryApiCredential``.

Cloudinary is the catalog's first integration that signs request
bodies with **SHA-1** of sorted ``key=value`` pairs concatenated
directly with ``api_secret``. The tests pin that signing algorithm
against a hand-computed reference, verify that :meth:`inject` attaches
Basic auth, and cover the four supported operations
(upload, destroy, list_resources, get_resource).
"""

from __future__ import annotations

import base64
import hashlib
from urllib.parse import parse_qs

import httpx
import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import CloudinaryApiCredential
from weftlyflow.credentials.types.cloudinary_api import (
    basic_auth_header,
    sign_params,
)
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.cloudinary import CloudinaryNode
from weftlyflow.nodes.integrations.cloudinary.operations import build_request

_CRED_ID: str = "cr_cloudinary"
_PROJECT_ID: str = "pr_test"
_CLOUD: str = "demo"
_KEY: str = "cldy_key_abc"
_SECRET: str = "cldy_secret_xyz"
_API: str = "https://api.cloudinary.com"


def _resolver(
    *,
    cloud_name: str = _CLOUD,
    api_key: str = _KEY,
    api_secret: str = _SECRET,
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.cloudinary_api": CloudinaryApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.cloudinary_api",
                {
                    "cloud_name": cloud_name,
                    "api_key": api_key,
                    "api_secret": api_secret,
                },
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


def _expected_basic_header() -> str:
    token = base64.b64encode(f"{_KEY}:{_SECRET}".encode()).decode("ascii")
    return f"Basic {token}"


# --- signing helper -----------------------------------------------


def test_sign_params_matches_hand_computed_sha1() -> None:
    params = {
        "timestamp": "1700000000",
        "public_id": "sample",
        "folder": "uploads/2024",
    }
    signing_input = (
        "folder=uploads/2024&public_id=sample&timestamp=1700000000" + _SECRET
    )
    expected = hashlib.sha1(signing_input.encode("utf-8")).hexdigest()
    assert sign_params(params, _SECRET) == expected


def test_sign_params_excludes_api_key_and_file() -> None:
    signed = {"timestamp": "1700000000", "public_id": "s"}
    full = {**signed, "api_key": "should-not-appear", "file": "a.jpg"}
    assert sign_params(full, _SECRET) == sign_params(signed, _SECRET)


def test_sign_params_skips_empty_values() -> None:
    assert sign_params({"a": "v", "b": ""}, _SECRET) == sign_params({"a": "v"}, _SECRET)
    assert sign_params({"a": "v", "b": None}, _SECRET) == sign_params({"a": "v"}, _SECRET)


def test_basic_auth_header_format() -> None:
    assert basic_auth_header(_KEY, _SECRET) == _expected_basic_header()


# --- credential inject --------------------------------------------


async def test_credential_inject_sets_basic_auth() -> None:
    request = httpx.Request("GET", f"{_API}/v1_1/{_CLOUD}/resources/image")
    out = await CloudinaryApiCredential().inject(
        {"cloud_name": _CLOUD, "api_key": _KEY, "api_secret": _SECRET}, request,
    )
    assert out.headers["Authorization"] == _expected_basic_header()


# --- upload -------------------------------------------------------


@respx.mock
async def test_upload_posts_signed_form_body() -> None:
    route = respx.post(f"{_API}/v1_1/{_CLOUD}/image/upload").mock(
        return_value=Response(
            200, json={"public_id": "sample", "secure_url": "https://..."},
        ),
    )
    node = Node(
        id="node_1",
        name="Cloudinary",
        type="weftlyflow.cloudinary",
        parameters={
            "operation": "upload",
            "file": "https://example.com/logo.png",
            "public_id": "logos/acme",
            "folder": "brands",
        },
        credentials={"cloudinary_api": _CRED_ID},
    )
    await CloudinaryNode().execute(_ctx_for(node), [Item()])
    sent = route.calls.last.request
    body = parse_qs(sent.content.decode())
    assert body["file"] == ["https://example.com/logo.png"]
    assert body["public_id"] == ["logos/acme"]
    assert body["folder"] == ["brands"]
    assert body["api_key"] == [_KEY]
    assert "timestamp" in body
    assert "signature" in body
    # Signature is SHA-1 over sorted (body - excluded) + api_secret.
    signable = {
        "public_id": "logos/acme",
        "folder": "brands",
        "timestamp": body["timestamp"][0],
    }
    assert body["signature"][0] == sign_params(signable, _SECRET)
    # Basic auth still rides along (harmless for signed calls).
    assert sent.headers["Authorization"] == _expected_basic_header()


@respx.mock
async def test_upload_without_file_is_validation_error() -> None:
    node = Node(
        id="node_1",
        name="Cloudinary",
        type="weftlyflow.cloudinary",
        parameters={"operation": "upload"},
        credentials={"cloudinary_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="'file' is required"):
        await CloudinaryNode().execute(_ctx_for(node), [Item()])


@respx.mock
async def test_upload_video_routes_to_video_path() -> None:
    route = respx.post(f"{_API}/v1_1/{_CLOUD}/video/upload").mock(
        return_value=Response(200, json={"public_id": "clip"}),
    )
    node = Node(
        id="node_1",
        name="Cloudinary",
        type="weftlyflow.cloudinary",
        parameters={
            "operation": "upload",
            "resource_type": "video",
            "file": "https://example.com/clip.mp4",
        },
        credentials={"cloudinary_api": _CRED_ID},
    )
    await CloudinaryNode().execute(_ctx_for(node), [Item()])
    assert route.called


# --- destroy ------------------------------------------------------


@respx.mock
async def test_destroy_posts_signed_public_id() -> None:
    route = respx.post(f"{_API}/v1_1/{_CLOUD}/image/destroy").mock(
        return_value=Response(200, json={"result": "ok"}),
    )
    node = Node(
        id="node_1",
        name="Cloudinary",
        type="weftlyflow.cloudinary",
        parameters={
            "operation": "destroy",
            "public_id": "logos/acme",
            "invalidate": True,
        },
        credentials={"cloudinary_api": _CRED_ID},
    )
    await CloudinaryNode().execute(_ctx_for(node), [Item()])
    sent = route.calls.last.request
    body = parse_qs(sent.content.decode())
    assert body["public_id"] == ["logos/acme"]
    assert body["invalidate"] == ["true"]
    assert body["api_key"] == [_KEY]
    assert "signature" in body
    signable = {
        "public_id": "logos/acme",
        "invalidate": "true",
        "timestamp": body["timestamp"][0],
    }
    assert body["signature"][0] == sign_params(signable, _SECRET)


def test_destroy_requires_public_id() -> None:
    with pytest.raises(ValueError, match="'public_id' is required"):
        build_request("destroy", _CLOUD, {})


# --- list_resources / get_resource (Basic auth only) --------------


@respx.mock
async def test_list_resources_uses_basic_auth_and_query_params() -> None:
    route = respx.get(f"{_API}/v1_1/{_CLOUD}/resources/image").mock(
        return_value=Response(200, json={"resources": []}),
    )
    node = Node(
        id="node_1",
        name="Cloudinary",
        type="weftlyflow.cloudinary",
        parameters={
            "operation": "list_resources",
            "max_results": "25",
            "prefix": "brands/",
        },
        credentials={"cloudinary_api": _CRED_ID},
    )
    await CloudinaryNode().execute(_ctx_for(node), [Item()])
    sent = route.calls.last.request
    qs = parse_qs(
        sent.url.query.decode() if isinstance(sent.url.query, bytes) else sent.url.query,
    )
    assert qs["max_results"] == ["25"]
    assert qs["prefix"] == ["brands/"]
    assert sent.headers["Authorization"] == _expected_basic_header()
    # Unsigned path — body signing fields must not leak into the URL.
    assert "signature" not in qs


@respx.mock
async def test_get_resource_uses_delivery_type_in_path() -> None:
    route = respx.get(f"{_API}/v1_1/{_CLOUD}/resources/image/upload/sample").mock(
        return_value=Response(200, json={"public_id": "sample"}),
    )
    node = Node(
        id="node_1",
        name="Cloudinary",
        type="weftlyflow.cloudinary",
        parameters={
            "operation": "get_resource",
            "public_id": "sample",
        },
        credentials={"cloudinary_api": _CRED_ID},
    )
    await CloudinaryNode().execute(_ctx_for(node), [Item()])
    assert route.called
    sent = route.calls.last.request
    assert sent.headers["Authorization"] == _expected_basic_header()


@respx.mock
async def test_get_resource_accepts_custom_delivery_type() -> None:
    route = respx.get(f"{_API}/v1_1/{_CLOUD}/resources/image/fetch/sample").mock(
        return_value=Response(200, json={}),
    )
    node = Node(
        id="node_1",
        name="Cloudinary",
        type="weftlyflow.cloudinary",
        parameters={
            "operation": "get_resource",
            "public_id": "sample",
            "delivery_type": "fetch",
        },
        credentials={"cloudinary_api": _CRED_ID},
    )
    await CloudinaryNode().execute(_ctx_for(node), [Item()])
    assert route.called


# --- validation / errors ------------------------------------------


def test_build_request_rejects_empty_cloud_name() -> None:
    with pytest.raises(ValueError, match="cloud_name is required"):
        build_request("upload", "", {"file": "x"})


def test_build_request_rejects_unknown_resource_type() -> None:
    with pytest.raises(ValueError, match="'resource_type' must be"):
        build_request("upload", _CLOUD, {"file": "x", "resource_type": "gif"})


def test_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("nuke", _CLOUD, {})


@respx.mock
async def test_api_error_surfaces_error_message() -> None:
    respx.post(f"{_API}/v1_1/{_CLOUD}/image/upload").mock(
        return_value=Response(
            401, json={"error": {"message": "Invalid Signature"}},
        ),
    )
    node = Node(
        id="node_1",
        name="Cloudinary",
        type="weftlyflow.cloudinary",
        parameters={
            "operation": "upload",
            "file": "https://example.com/logo.png",
        },
        credentials={"cloudinary_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="Invalid Signature"):
        await CloudinaryNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Cloudinary",
        type="weftlyflow.cloudinary",
        parameters={
            "operation": "upload",
            "file": "https://example.com/logo.png",
        },
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await CloudinaryNode().execute(_ctx_for(node), [Item()])


async def test_empty_cloud_name_raises() -> None:
    resolver = _resolver(cloud_name="")
    node = Node(
        id="node_1",
        name="Cloudinary",
        type="weftlyflow.cloudinary",
        parameters={
            "operation": "upload",
            "file": "https://example.com/logo.png",
        },
        credentials={"cloudinary_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="empty 'cloud_name'"):
        await CloudinaryNode().execute(_ctx_for(node, resolver=resolver), [Item()])
