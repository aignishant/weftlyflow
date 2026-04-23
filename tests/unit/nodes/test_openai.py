"""Unit tests for :class:`OpenAINode`.

Exercises every supported operation against a respx-mocked OpenAI API.
Verifies the Bearer + ``OpenAI-Organization`` + ``OpenAI-Project``
multi-dimensional header triple, chat-completion body coercion,
response_format envelope, image size validation, and the
``error: {message}`` envelope parse.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import OpenAIApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.openai import OpenAINode
from weftlyflow.nodes.integrations.openai.operations import build_request

_CRED_ID: str = "cr_openai"
_PROJECT_ID: str = "pr_test"
_TOKEN: str = "sk-test"
_ORG: str = "org-abc"
_PROJECT_HEADER: str = "proj_xyz"
_BASE: str = "https://api.openai.com/v1"


def _resolver(
    *,
    token: str = _TOKEN,
    org: str = _ORG,
    project: str = _PROJECT_HEADER,
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.openai_api": OpenAIApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.openai_api",
                {
                    "api_key": token,
                    "organization_id": org,
                    "project_id": project,
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


# --- chat_completion -------------------------------------------------


@respx.mock
async def test_chat_completion_sends_bearer_and_scoping_headers() -> None:
    route = respx.post(f"{_BASE}/chat/completions").mock(
        return_value=Response(200, json={"id": "cmpl-1"}),
    )
    node = Node(
        id="node_1",
        name="OpenAI",
        type="weftlyflow.openai",
        parameters={
            "operation": "chat_completion",
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hello"}],
            "temperature": 0.5,
        },
        credentials={"openai_api": _CRED_ID},
    )
    await OpenAINode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.headers["Authorization"] == f"Bearer {_TOKEN}"
    assert request.headers["OpenAI-Organization"] == _ORG
    assert request.headers["OpenAI-Project"] == _PROJECT_HEADER
    body = json.loads(request.content)
    assert body["model"] == "gpt-4o-mini"
    assert body["messages"] == [{"role": "user", "content": "hello"}]
    assert body["stream"] is False
    assert body["temperature"] == 0.5


@respx.mock
async def test_chat_completion_omits_scoping_when_empty() -> None:
    route = respx.post(f"{_BASE}/chat/completions").mock(
        return_value=Response(200, json={}),
    )
    resolver = _resolver(org="", project="")
    node = Node(
        id="node_1",
        name="OpenAI",
        type="weftlyflow.openai",
        parameters={
            "operation": "chat_completion",
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hi"}],
        },
        credentials={"openai_api": _CRED_ID},
    )
    await OpenAINode().execute(_ctx_for(node, resolver=resolver), [Item()])
    request = route.calls.last.request
    assert "OpenAI-Organization" not in request.headers
    assert "OpenAI-Project" not in request.headers


def test_chat_completion_wraps_response_format() -> None:
    _, _, body, _ = build_request(
        "chat_completion",
        {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "x"}],
            "response_format": "json_object",
        },
    )
    assert body is not None
    assert body["response_format"] == {"type": "json_object"}


def test_chat_completion_rejects_bad_response_format() -> None:
    with pytest.raises(ValueError, match="'response_format' must be"):
        build_request(
            "chat_completion",
            {
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "x"}],
                "response_format": "yaml",
            },
        )


def test_chat_completion_requires_messages() -> None:
    with pytest.raises(ValueError, match="'messages' is required"):
        build_request("chat_completion", {"model": "gpt-4o-mini"})


def test_chat_completion_rejects_non_list_messages() -> None:
    with pytest.raises(ValueError, match="non-empty list"):
        build_request(
            "chat_completion",
            {"model": "gpt-4o-mini", "messages": "hi"},
        )


def test_chat_completion_rejects_message_missing_role() -> None:
    with pytest.raises(ValueError, match="missing 'role'"):
        build_request(
            "chat_completion",
            {
                "model": "gpt-4o-mini",
                "messages": [{"content": "x"}],
            },
        )


def test_chat_completion_passes_tools_through() -> None:
    tools = [{"type": "function", "function": {"name": "x"}}]
    _, _, body, _ = build_request(
        "chat_completion",
        {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "x"}],
            "tools": tools,
        },
    )
    assert body is not None
    assert body["tools"] == tools


# --- create_embedding ------------------------------------------------


@respx.mock
async def test_create_embedding_posts_input() -> None:
    route = respx.post(f"{_BASE}/embeddings").mock(
        return_value=Response(200, json={"data": []}),
    )
    node = Node(
        id="node_1",
        name="OpenAI",
        type="weftlyflow.openai",
        parameters={
            "operation": "create_embedding",
            "model": "text-embedding-3-small",
            "input": ["a", "b"],
            "dimensions": 256,
        },
        credentials={"openai_api": _CRED_ID},
    )
    await OpenAINode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "model": "text-embedding-3-small",
        "input": ["a", "b"],
        "dimensions": 256,
    }


def test_create_embedding_requires_input() -> None:
    with pytest.raises(ValueError, match="'input' is required"):
        build_request(
            "create_embedding",
            {"model": "text-embedding-3-small"},
        )


# --- list_models / get_model ----------------------------------------


@respx.mock
async def test_list_models_uses_get() -> None:
    route = respx.get(f"{_BASE}/models").mock(
        return_value=Response(200, json={"data": []}),
    )
    node = Node(
        id="node_1",
        name="OpenAI",
        type="weftlyflow.openai",
        parameters={"operation": "list_models"},
        credentials={"openai_api": _CRED_ID},
    )
    await OpenAINode().execute(_ctx_for(node), [Item()])
    assert route.calls.last.request.method == "GET"


@respx.mock
async def test_get_model_hits_model_path() -> None:
    respx.get(f"{_BASE}/models/gpt-4o-mini").mock(
        return_value=Response(200, json={"id": "gpt-4o-mini"}),
    )
    node = Node(
        id="node_1",
        name="OpenAI",
        type="weftlyflow.openai",
        parameters={"operation": "get_model", "model": "gpt-4o-mini"},
        credentials={"openai_api": _CRED_ID},
    )
    await OpenAINode().execute(_ctx_for(node), [Item()])


# --- create_moderation ----------------------------------------------


@respx.mock
async def test_create_moderation_posts_input_only() -> None:
    route = respx.post(f"{_BASE}/moderations").mock(
        return_value=Response(200, json={}),
    )
    node = Node(
        id="node_1",
        name="OpenAI",
        type="weftlyflow.openai",
        parameters={"operation": "create_moderation", "input": "hi"},
        credentials={"openai_api": _CRED_ID},
    )
    await OpenAINode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"input": "hi"}


# --- create_image ---------------------------------------------------


@respx.mock
async def test_create_image_validates_size() -> None:
    route = respx.post(f"{_BASE}/images/generations").mock(
        return_value=Response(200, json={}),
    )
    node = Node(
        id="node_1",
        name="OpenAI",
        type="weftlyflow.openai",
        parameters={
            "operation": "create_image",
            "prompt": "a cat",
            "size": "1024x1024",
            "n": 1,
        },
        credentials={"openai_api": _CRED_ID},
    )
    await OpenAINode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["prompt"] == "a cat"
    assert body["size"] == "1024x1024"
    assert body["n"] == 1


def test_create_image_rejects_bad_size() -> None:
    with pytest.raises(ValueError, match="'size' must be one of"):
        build_request(
            "create_image",
            {"prompt": "x", "size": "999x999"},
        )


def test_create_image_rejects_bad_response_format() -> None:
    with pytest.raises(ValueError, match="'response_format' must be one of"):
        build_request(
            "create_image",
            {"prompt": "x", "response_format": "webp"},
        )


# --- errors ----------------------------------------------------------


@respx.mock
async def test_api_error_surfaces_error_envelope() -> None:
    respx.get(f"{_BASE}/models/bad").mock(
        return_value=Response(
            404,
            json={"error": {"message": "model not found", "code": "not_found"}},
        ),
    )
    node = Node(
        id="node_1",
        name="OpenAI",
        type="weftlyflow.openai",
        parameters={"operation": "get_model", "model": "bad"},
        credentials={"openai_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="model not found"):
        await OpenAINode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="OpenAI",
        type="weftlyflow.openai",
        parameters={"operation": "list_models"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await OpenAINode().execute(_ctx_for(node), [Item()])


def test_build_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("unknown_op", {})
