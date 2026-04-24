"""Unit tests for :class:`MistralNode` and ``MistralApiCredential``.

Exercises the standard ``Authorization: Bearer`` header injection,
the OpenAI-compatible ``/v1/chat/completions`` shape, the
Mistral-distinctive ``/v1/fim/completions`` endpoint, and the error
envelope parser (which prefers ``message`` at the top level over the
nested ``error.message`` form used by OpenAI).
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import MistralApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.mistral import MistralNode
from weftlyflow.nodes.integrations.mistral.operations import build_request

_CRED_ID: str = "cr_mistral"
_PROJECT_ID: str = "pr_test"
_KEY: str = "mst-test-key"
_BASE: str = "https://api.mistral.ai"


def _resolver(*, api_key: str = _KEY) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.mistral_api": MistralApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.mistral_api",
                {"api_key": api_key},
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


async def test_credential_sets_bearer_header() -> None:
    request = httpx.Request("POST", f"{_BASE}/v1/chat/completions")
    out = await MistralApiCredential().inject({"api_key": _KEY}, request)
    assert out.headers["Authorization"] == f"Bearer {_KEY}"


# --- chat_completion ------------------------------------------------


@respx.mock
async def test_chat_completion_posts_openai_compatible_body() -> None:
    route = respx.post(f"{_BASE}/v1/chat/completions").mock(
        return_value=Response(200, json={"id": "cmpl_1"}),
    )
    node = Node(
        id="node_1",
        name="Mistral",
        type="weftlyflow.mistral",
        parameters={
            "operation": "chat_completion",
            "model": "mistral-large-latest",
            "messages": [{"role": "user", "content": "Hi"}],
            "temperature": 0.3,
            "max_tokens": 128,
            "response_format": "json_object",
            "safe_prompt": True,
        },
        credentials={"mistral_api": _CRED_ID},
    )
    await MistralNode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.headers["Authorization"] == f"Bearer {_KEY}"
    body = json.loads(request.content)
    assert body == {
        "model": "mistral-large-latest",
        "messages": [{"role": "user", "content": "Hi"}],
        "stream": False,
        "temperature": 0.3,
        "max_tokens": 128,
        "response_format": {"type": "json_object"},
        "safe_prompt": True,
    }


def test_chat_completion_defaults_model_to_mistral_large() -> None:
    _, _, body, _ = build_request(
        "chat_completion",
        {"messages": [{"role": "user", "content": "Hi"}]},
    )
    assert body is not None
    assert body["model"] == "mistral-large-latest"
    assert body["stream"] is False


def test_chat_completion_requires_messages() -> None:
    with pytest.raises(ValueError, match="'messages' is required"):
        build_request("chat_completion", {})


def test_chat_completion_rejects_empty_messages_list() -> None:
    with pytest.raises(ValueError, match="non-empty list"):
        build_request("chat_completion", {"messages": []})


def test_chat_completion_rejects_message_without_role() -> None:
    with pytest.raises(ValueError, match="'role'"):
        build_request("chat_completion", {"messages": [{"content": "hi"}]})


def test_chat_completion_rejects_message_without_content() -> None:
    with pytest.raises(ValueError, match="'content'"):
        build_request("chat_completion", {"messages": [{"role": "user"}]})


def test_chat_completion_rejects_bad_response_format() -> None:
    with pytest.raises(ValueError, match="'response_format'"):
        build_request(
            "chat_completion",
            {
                "messages": [{"role": "user", "content": "hi"}],
                "response_format": "yaml",
            },
        )


def test_chat_completion_rejects_non_list_tools() -> None:
    with pytest.raises(ValueError, match="'tools'"):
        build_request(
            "chat_completion",
            {
                "messages": [{"role": "user", "content": "hi"}],
                "tools": {"not": "a list"},
            },
        )


# --- fim_completion -------------------------------------------------


@respx.mock
async def test_fim_completion_posts_prompt_and_suffix() -> None:
    route = respx.post(f"{_BASE}/v1/fim/completions").mock(
        return_value=Response(200, json={"id": "fim_1"}),
    )
    node = Node(
        id="node_1",
        name="Mistral",
        type="weftlyflow.mistral",
        parameters={
            "operation": "fim_completion",
            "model": "codestral-latest",
            "prompt": "def add(a, b):",
            "suffix": "    return result",
            "temperature": 0.1,
        },
        credentials={"mistral_api": _CRED_ID},
    )
    await MistralNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "model": "codestral-latest",
        "prompt": "def add(a, b):",
        "suffix": "    return result",
        "stream": False,
        "temperature": 0.1,
    }


def test_fim_completion_defaults_to_codestral() -> None:
    _, _, body, _ = build_request(
        "fim_completion",
        {"prompt": "def f():"},
    )
    assert body is not None
    assert body["model"] == "codestral-latest"
    assert "suffix" not in body


def test_fim_completion_requires_prompt() -> None:
    with pytest.raises(ValueError, match="'prompt' is required"):
        build_request("fim_completion", {})


# --- create_embedding ----------------------------------------------


@respx.mock
async def test_create_embedding_posts_input_and_model() -> None:
    route = respx.post(f"{_BASE}/v1/embeddings").mock(
        return_value=Response(200, json={"data": []}),
    )
    node = Node(
        id="node_1",
        name="Mistral",
        type="weftlyflow.mistral",
        parameters={
            "operation": "create_embedding",
            "input": ["foo", "bar"],
        },
        credentials={"mistral_api": _CRED_ID},
    )
    await MistralNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"model": "mistral-embed", "input": ["foo", "bar"]}


def test_create_embedding_requires_input() -> None:
    with pytest.raises(ValueError, match="'input' is required"):
        build_request("create_embedding", {})


# --- list_models ---------------------------------------------------


@respx.mock
async def test_list_models_issues_get() -> None:
    route = respx.get(f"{_BASE}/v1/models").mock(
        return_value=Response(200, json={"data": []}),
    )
    node = Node(
        id="node_1",
        name="Mistral",
        type="weftlyflow.mistral",
        parameters={"operation": "list_models"},
        credentials={"mistral_api": _CRED_ID},
    )
    out = await MistralNode().execute(_ctx_for(node), [Item()])
    assert route.called
    assert out[0][0].json["status"] == 200


# --- errors --------------------------------------------------------


@respx.mock
async def test_api_error_surface_uses_top_level_message() -> None:
    respx.post(f"{_BASE}/v1/chat/completions").mock(
        return_value=Response(
            401,
            json={"message": "Invalid API key"},
        ),
    )
    node = Node(
        id="node_1",
        name="Mistral",
        type="weftlyflow.mistral",
        parameters={
            "operation": "chat_completion",
            "messages": [{"role": "user", "content": "hi"}],
        },
        credentials={"mistral_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="Invalid API key"):
        await MistralNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Mistral",
        type="weftlyflow.mistral",
        parameters={
            "operation": "chat_completion",
            "messages": [{"role": "user", "content": "hi"}],
        },
        credentials={},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await MistralNode().execute(_ctx_for(node), [Item()])


async def test_empty_api_key_raises() -> None:
    node = Node(
        id="node_1",
        name="Mistral",
        type="weftlyflow.mistral",
        parameters={
            "operation": "chat_completion",
            "messages": [{"role": "user", "content": "hi"}],
        },
        credentials={"mistral_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="empty 'api_key'"):
        await MistralNode().execute(
            _ctx_for(node, resolver=_resolver(api_key="")),
            [Item()],
        )


def test_unsupported_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("definitely_not_real", {})


def test_max_tokens_rejects_zero() -> None:
    with pytest.raises(ValueError, match="'max_tokens' must be >= 1"):
        build_request(
            "chat_completion",
            {
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 0,
            },
        )
