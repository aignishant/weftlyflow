"""Unit tests for :class:`AnthropicNode` and ``AnthropicApiCredential``.

Exercises the distinctive ``x-api-key`` + ``anthropic-version`` header
pair (NOT Bearer), the ``count_tokens`` separate endpoint, and the
``error.message`` envelope parser.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import AnthropicApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.anthropic import AnthropicNode
from weftlyflow.nodes.integrations.anthropic.operations import build_request

_CRED_ID: str = "cr_anthropic"
_PROJECT_ID: str = "pr_test"
_KEY: str = "sk-ant-test-key"
_VERSION: str = "2023-06-01"
_BASE: str = "https://api.anthropic.com"


def _resolver(
    *,
    api_key: str = _KEY,
    version: str = _VERSION,
    beta: str = "",
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.anthropic_api": AnthropicApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.anthropic_api",
                {
                    "api_key": api_key,
                    "anthropic_version": version,
                    "anthropic_beta": beta,
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


# --- credential.inject ----------------------------------------------


async def test_credential_sets_x_api_key_not_bearer() -> None:
    request = httpx.Request("POST", f"{_BASE}/v1/messages")
    out = await AnthropicApiCredential().inject(
        {"api_key": _KEY, "anthropic_version": _VERSION},
        request,
    )
    assert out.headers["x-api-key"] == _KEY
    assert out.headers["anthropic-version"] == _VERSION
    assert "Authorization" not in out.headers


async def test_credential_inject_sets_beta_header_when_present() -> None:
    request = httpx.Request("POST", f"{_BASE}/v1/messages")
    out = await AnthropicApiCredential().inject(
        {
            "api_key": _KEY,
            "anthropic_version": _VERSION,
            "anthropic_beta": "prompt-caching-2024-07-31",
        },
        request,
    )
    assert out.headers["anthropic-beta"] == "prompt-caching-2024-07-31"


async def test_credential_inject_defaults_version_when_blank() -> None:
    request = httpx.Request("POST", f"{_BASE}/v1/messages")
    out = await AnthropicApiCredential().inject({"api_key": _KEY}, request)
    assert out.headers["anthropic-version"] == "2023-06-01"


# --- create_message --------------------------------------------------


@respx.mock
async def test_create_message_posts_required_fields() -> None:
    route = respx.post(f"{_BASE}/v1/messages").mock(
        return_value=Response(200, json={"id": "msg_1"}),
    )
    node = Node(
        id="node_1",
        name="Anthropic",
        type="weftlyflow.anthropic",
        parameters={
            "operation": "create_message",
            "model": "claude-3-5-sonnet-latest",
            "messages": [{"role": "user", "content": "Hi"}],
            "system": "Be terse.",
            "max_tokens": 512,
            "temperature": 0.2,
        },
        credentials={"anthropic_api": _CRED_ID},
    )
    await AnthropicNode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.headers["x-api-key"] == _KEY
    assert request.headers["anthropic-version"] == _VERSION
    body = json.loads(request.content)
    assert body == {
        "model": "claude-3-5-sonnet-latest",
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 512,
        "system": "Be terse.",
        "temperature": 0.2,
    }


def test_create_message_defaults_max_tokens_to_1024() -> None:
    _, _, body, _ = build_request(
        "create_message",
        {"messages": [{"role": "user", "content": "Hi"}]},
    )
    assert body is not None
    assert body["max_tokens"] == 1024


def test_create_message_requires_messages() -> None:
    with pytest.raises(ValueError, match="'messages' is required"):
        build_request("create_message", {})


def test_create_message_rejects_empty_messages_list() -> None:
    with pytest.raises(ValueError, match="non-empty JSON array"):
        build_request("create_message", {"messages": []})


def test_create_message_rejects_non_dict_message_entry() -> None:
    with pytest.raises(ValueError, match="must be a JSON object"):
        build_request("create_message", {"messages": ["nope"]})


# --- count_tokens ----------------------------------------------------


@respx.mock
async def test_count_tokens_posts_to_dedicated_endpoint() -> None:
    route = respx.post(f"{_BASE}/v1/messages/count_tokens").mock(
        return_value=Response(200, json={"input_tokens": 12}),
    )
    node = Node(
        id="node_1",
        name="Anthropic",
        type="weftlyflow.anthropic",
        parameters={
            "operation": "count_tokens",
            "model": "claude-3-5-sonnet-latest",
            "messages": [{"role": "user", "content": "Hello world"}],
        },
        credentials={"anthropic_api": _CRED_ID},
    )
    await AnthropicNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["model"] == "claude-3-5-sonnet-latest"


# --- list / get model -----------------------------------------------


@respx.mock
async def test_list_models_uses_get() -> None:
    route = respx.get(f"{_BASE}/v1/models").mock(
        return_value=Response(200, json={"data": []}),
    )
    node = Node(
        id="node_1",
        name="Anthropic",
        type="weftlyflow.anthropic",
        parameters={"operation": "list_models"},
        credentials={"anthropic_api": _CRED_ID},
    )
    await AnthropicNode().execute(_ctx_for(node), [Item()])
    assert route.calls.last.request.method == "GET"


@respx.mock
async def test_get_model_uses_path() -> None:
    respx.get(f"{_BASE}/v1/models/claude-3-5-sonnet-latest").mock(
        return_value=Response(200, json={"id": "claude-3-5-sonnet-latest"}),
    )
    node = Node(
        id="node_1",
        name="Anthropic",
        type="weftlyflow.anthropic",
        parameters={"operation": "get_model", "model_id": "claude-3-5-sonnet-latest"},
        credentials={"anthropic_api": _CRED_ID},
    )
    await AnthropicNode().execute(_ctx_for(node), [Item()])


def test_get_model_requires_model_id() -> None:
    with pytest.raises(ValueError, match="'model_id' is required"):
        build_request("get_model", {})


# --- errors ----------------------------------------------------------


@respx.mock
async def test_error_envelope_is_parsed() -> None:
    respx.post(f"{_BASE}/v1/messages").mock(
        return_value=Response(
            400,
            json={
                "type": "error",
                "error": {"type": "invalid_request_error", "message": "bad"},
            },
        ),
    )
    node = Node(
        id="node_1",
        name="Anthropic",
        type="weftlyflow.anthropic",
        parameters={
            "operation": "create_message",
            "messages": [{"role": "user", "content": "Hi"}],
        },
        credentials={"anthropic_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="bad"):
        await AnthropicNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Anthropic",
        type="weftlyflow.anthropic",
        parameters={"operation": "list_models"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await AnthropicNode().execute(_ctx_for(node), [Item()])


def test_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("nuke", {})
