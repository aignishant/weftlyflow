"""Unit tests for :class:`OllamaNode` and ``OllamaApiCredential``.

Exercises the distinctive optional-auth shape (no Authorization header
when ``api_key`` is blank), the credential-owned base URL with a
default of ``http://localhost:11434``, the four supported operations,
and the node's fallback to the default base URL when no credential is
attached.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import OllamaApiCredential
from weftlyflow.credentials.types.ollama_api import base_url_from
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.ollama import OllamaNode
from weftlyflow.nodes.integrations.ollama.operations import build_request

_CRED_ID: str = "cr_ollama"
_PROJECT_ID: str = "pr_test"
_DEFAULT_BASE: str = "http://localhost:11434"
_REMOTE_BASE: str = "https://ollama.example.com"
_API_KEY: str = "proxy-token-abc"


def _resolver(
    *,
    base_url: str = _DEFAULT_BASE,
    api_key: str = "",
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.ollama_api": OllamaApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.ollama_api",
                {"base_url": base_url, "api_key": api_key},
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
        credential_resolver=resolver,
    )


# --- credential.inject ----------------------------------------------


async def test_credential_omits_authorization_when_api_key_blank() -> None:
    request = httpx.Request("POST", f"{_DEFAULT_BASE}/api/chat")
    out = await OllamaApiCredential().inject(
        {"base_url": _DEFAULT_BASE, "api_key": ""}, request,
    )
    assert "Authorization" not in out.headers


async def test_credential_sets_bearer_when_api_key_present() -> None:
    request = httpx.Request("POST", f"{_REMOTE_BASE}/api/chat")
    out = await OllamaApiCredential().inject(
        {"base_url": _REMOTE_BASE, "api_key": _API_KEY}, request,
    )
    assert out.headers["Authorization"] == f"Bearer {_API_KEY}"


def test_base_url_from_defaults_when_blank() -> None:
    assert base_url_from("") == _DEFAULT_BASE


def test_base_url_from_strips_trailing_slash() -> None:
    assert base_url_from("http://box:11434/") == "http://box:11434"


def test_base_url_from_adds_http_scheme_when_missing() -> None:
    assert base_url_from("box.local:11434") == "http://box.local:11434"


# --- operations: generate --------------------------------------------


@respx.mock
async def test_generate_posts_required_fields() -> None:
    route = respx.post(f"{_REMOTE_BASE}/api/generate").mock(
        return_value=Response(200, json={"response": "hello"}),
    )
    node = Node(
        id="node_1",
        name="Ollama",
        type="weftlyflow.ollama",
        parameters={
            "operation": "generate",
            "model": "llama3.2",
            "prompt": "Say hi",
            "system": "Be terse.",
            "format": "json",
            "options": {"temperature": 0.1},
        },
        credentials={"ollama_api": _CRED_ID},
    )
    await OllamaNode().execute(
        _ctx_for(node, resolver=_resolver(base_url=_REMOTE_BASE, api_key=_API_KEY)),
        [Item()],
    )
    request = route.calls.last.request
    assert request.headers["Authorization"] == f"Bearer {_API_KEY}"
    body = json.loads(request.content)
    assert body == {
        "model": "llama3.2",
        "prompt": "Say hi",
        "stream": False,
        "system": "Be terse.",
        "format": "json",
        "options": {"temperature": 0.1},
    }


def test_generate_requires_prompt() -> None:
    with pytest.raises(ValueError, match="'prompt' is required"):
        build_request("generate", {"model": "llama3.2"})


def test_generate_forces_stream_false() -> None:
    _, _, body, _ = build_request("generate", {"prompt": "hi"})
    assert body is not None
    assert body["stream"] is False


# --- operations: chat ------------------------------------------------


@respx.mock
async def test_chat_posts_messages_to_chat_endpoint() -> None:
    route = respx.post(f"{_DEFAULT_BASE}/api/chat").mock(
        return_value=Response(200, json={"message": {"role": "assistant", "content": "hi"}}),
    )
    node = Node(
        id="node_1",
        name="Ollama",
        type="weftlyflow.ollama",
        parameters={
            "operation": "chat",
            "model": "llama3.2",
            "messages": [{"role": "user", "content": "Hello"}],
        },
        credentials={"ollama_api": _CRED_ID},
    )
    await OllamaNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["messages"] == [{"role": "user", "content": "Hello"}]
    assert body["stream"] is False


def test_chat_requires_messages() -> None:
    with pytest.raises(ValueError, match="'messages' is required"):
        build_request("chat", {"model": "llama3.2"})


def test_chat_rejects_non_list_messages() -> None:
    with pytest.raises(ValueError, match="non-empty JSON array"):
        build_request("chat", {"messages": []})


def test_chat_rejects_non_dict_message_entry() -> None:
    with pytest.raises(ValueError, match="must be a JSON object"):
        build_request("chat", {"messages": ["nope"]})


# --- operations: embeddings -----------------------------------------


@respx.mock
async def test_embeddings_posts_to_embeddings_endpoint() -> None:
    route = respx.post(f"{_DEFAULT_BASE}/api/embeddings").mock(
        return_value=Response(200, json={"embedding": [0.1, 0.2]}),
    )
    node = Node(
        id="node_1",
        name="Ollama",
        type="weftlyflow.ollama",
        parameters={
            "operation": "embeddings",
            "model": "nomic-embed-text",
            "prompt": "The quick brown fox",
        },
        credentials={"ollama_api": _CRED_ID},
    )
    await OllamaNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"model": "nomic-embed-text", "prompt": "The quick brown fox"}


def test_embeddings_requires_prompt() -> None:
    with pytest.raises(ValueError, match="'prompt' is required"):
        build_request("embeddings", {"model": "nomic-embed-text"})


# --- operations: list_models ----------------------------------------


@respx.mock
async def test_list_models_uses_get_on_tags() -> None:
    route = respx.get(f"{_DEFAULT_BASE}/api/tags").mock(
        return_value=Response(200, json={"models": []}),
    )
    node = Node(
        id="node_1",
        name="Ollama",
        type="weftlyflow.ollama",
        parameters={"operation": "list_models"},
        credentials={"ollama_api": _CRED_ID},
    )
    await OllamaNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.calls.last.request.method == "GET"


# --- no-credential fallback -----------------------------------------


@respx.mock
async def test_node_works_without_credential_against_localhost() -> None:
    route = respx.get(f"{_DEFAULT_BASE}/api/tags").mock(
        return_value=Response(200, json={"models": []}),
    )
    node = Node(
        id="node_1",
        name="Ollama",
        type="weftlyflow.ollama",
        parameters={"operation": "list_models"},
    )
    await OllamaNode().execute(_ctx_for(node), [Item()])
    assert "Authorization" not in route.calls.last.request.headers


# --- errors ---------------------------------------------------------


@respx.mock
async def test_error_envelope_is_parsed() -> None:
    respx.post(f"{_DEFAULT_BASE}/api/chat").mock(
        return_value=Response(500, json={"error": "model 'llama3.2' not found"}),
    )
    node = Node(
        id="node_1",
        name="Ollama",
        type="weftlyflow.ollama",
        parameters={
            "operation": "chat",
            "messages": [{"role": "user", "content": "Hi"}],
        },
        credentials={"ollama_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="not found"):
        await OllamaNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


def test_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("nuke", {})
