"""Unit tests for :class:`GoogleGenAINode` and ``GoogleGenAIApiCredential``.

Exercises the ``x-goog-api-key`` header injection, the
``:generateContent`` URL composition, ``generationConfig`` grouping,
``systemInstruction`` wrapping, and the Gemini ``error.message``
envelope parser.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import GoogleGenAIApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.google_genai import GoogleGenAINode
from weftlyflow.nodes.integrations.google_genai.operations import build_request

_CRED_ID: str = "cr_google_genai"
_PROJECT_ID: str = "pr_test"
_KEY: str = "AIza-test-key"
_BASE: str = "https://generativelanguage.googleapis.com"


def _resolver(*, api_key: str = _KEY) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.google_genai_api": GoogleGenAIApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.google_genai_api",
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


async def test_credential_sets_x_goog_api_key_header() -> None:
    request = httpx.Request("POST", f"{_BASE}/v1beta/models")
    out = await GoogleGenAIApiCredential().inject({"api_key": _KEY}, request)
    assert out.headers["x-goog-api-key"] == _KEY
    assert "Authorization" not in out.headers


# --- generate_content ------------------------------------------------


@respx.mock
async def test_generate_content_builds_model_scoped_url() -> None:
    route = respx.post(
        f"{_BASE}/v1beta/models/gemini-1.5-pro:generateContent",
    ).mock(return_value=Response(200, json={"candidates": []}))
    node = Node(
        id="node_1",
        name="Gemini",
        type="weftlyflow.google_genai",
        parameters={
            "operation": "generate_content",
            "model": "gemini-1.5-pro",
            "contents": [
                {"role": "user", "parts": [{"text": "Hi"}]},
            ],
            "system": "Be terse.",
            "temperature": 0.2,
            "max_output_tokens": 256,
            "top_p": 0.9,
            "top_k": 40,
        },
        credentials={"google_genai_api": _CRED_ID},
    )
    await GoogleGenAINode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.headers["x-goog-api-key"] == _KEY
    body = json.loads(request.content)
    assert body["contents"] == [
        {"role": "user", "parts": [{"text": "Hi"}]},
    ]
    assert body["systemInstruction"] == {"parts": [{"text": "Be terse."}]}
    assert body["generationConfig"] == {
        "temperature": 0.2,
        "maxOutputTokens": 256,
        "topP": 0.9,
        "topK": 40,
    }


@respx.mock
async def test_generate_content_strips_models_prefix_from_url() -> None:
    """``models/gemini-1.5-flash`` and ``gemini-1.5-flash`` produce the same URL."""
    route = respx.post(
        f"{_BASE}/v1beta/models/gemini-1.5-flash:generateContent",
    ).mock(return_value=Response(200, json={"candidates": []}))
    node = Node(
        id="node_1",
        name="Gemini",
        type="weftlyflow.google_genai",
        parameters={
            "operation": "generate_content",
            "model": "models/gemini-1.5-flash",
            "contents": [{"role": "user", "parts": [{"text": "hi"}]}],
        },
        credentials={"google_genai_api": _CRED_ID},
    )
    await GoogleGenAINode().execute(_ctx_for(node), [Item()])
    assert route.called


def test_generate_content_requires_contents() -> None:
    with pytest.raises(ValueError, match="'contents' is required"):
        build_request("generate_content", {})


def test_generate_content_rejects_empty_contents_list() -> None:
    with pytest.raises(ValueError, match="non-empty JSON array"):
        build_request("generate_content", {"contents": []})


def test_generate_content_rejects_non_dict_content_entry() -> None:
    with pytest.raises(ValueError, match="JSON object"):
        build_request("generate_content", {"contents": ["hi"]})


def test_generate_content_omits_generation_config_when_empty() -> None:
    _, _, body, _ = build_request(
        "generate_content",
        {"contents": [{"role": "user", "parts": [{"text": "hi"}]}]},
    )
    assert body is not None
    assert "generationConfig" not in body


def test_generate_content_defaults_to_gemini_1_5_flash() -> None:
    _, path, _, _ = build_request(
        "generate_content",
        {"contents": [{"role": "user", "parts": [{"text": "hi"}]}]},
    )
    assert "gemini-1.5-flash:generateContent" in path


# --- count_tokens ----------------------------------------------------


@respx.mock
async def test_count_tokens_posts_contents_to_scoped_endpoint() -> None:
    route = respx.post(
        f"{_BASE}/v1beta/models/gemini-1.5-flash:countTokens",
    ).mock(return_value=Response(200, json={"totalTokens": 4}))
    node = Node(
        id="node_1",
        name="Gemini",
        type="weftlyflow.google_genai",
        parameters={
            "operation": "count_tokens",
            "model": "gemini-1.5-flash",
            "contents": [{"role": "user", "parts": [{"text": "Hello"}]}],
        },
        credentials={"google_genai_api": _CRED_ID},
    )
    await GoogleGenAINode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "contents": [{"role": "user", "parts": [{"text": "Hello"}]}],
    }


# --- list_models / get_model ----------------------------------------


@respx.mock
async def test_list_models_issues_get() -> None:
    route = respx.get(f"{_BASE}/v1beta/models").mock(
        return_value=Response(200, json={"models": []}),
    )
    node = Node(
        id="node_1",
        name="Gemini",
        type="weftlyflow.google_genai",
        parameters={"operation": "list_models"},
        credentials={"google_genai_api": _CRED_ID},
    )
    out = await GoogleGenAINode().execute(_ctx_for(node), [Item()])
    assert route.called
    assert out[0][0].json["status"] == 200


@respx.mock
async def test_get_model_url_encodes_id() -> None:
    route = respx.get(
        f"{_BASE}/v1beta/models/gemini-1.5-pro",
    ).mock(return_value=Response(200, json={"name": "models/gemini-1.5-pro"}))
    node = Node(
        id="node_1",
        name="Gemini",
        type="weftlyflow.google_genai",
        parameters={"operation": "get_model", "model_id": "gemini-1.5-pro"},
        credentials={"google_genai_api": _CRED_ID},
    )
    await GoogleGenAINode().execute(_ctx_for(node), [Item()])
    assert route.called


def test_get_model_requires_model_id() -> None:
    with pytest.raises(ValueError, match="'model_id' is required"):
        build_request("get_model", {})


# --- validation / errors --------------------------------------------


def test_generation_config_rejects_non_numeric_temperature() -> None:
    with pytest.raises(ValueError, match="'temperature' must be a number"):
        build_request(
            "generate_content",
            {
                "contents": [{"role": "user", "parts": [{"text": "hi"}]}],
                "temperature": "hot",
            },
        )


def test_generation_config_rejects_non_positive_max_output_tokens() -> None:
    with pytest.raises(ValueError, match="'max_output_tokens' must be >= 1"):
        build_request(
            "generate_content",
            {
                "contents": [{"role": "user", "parts": [{"text": "hi"}]}],
                "max_output_tokens": 0,
            },
        )


@respx.mock
async def test_api_error_surface_uses_error_message() -> None:
    respx.post(
        f"{_BASE}/v1beta/models/gemini-1.5-flash:generateContent",
    ).mock(
        return_value=Response(
            429,
            json={
                "error": {
                    "message": "Resource has been exhausted",
                    "status": "RESOURCE_EXHAUSTED",
                },
            },
        ),
    )
    node = Node(
        id="node_1",
        name="Gemini",
        type="weftlyflow.google_genai",
        parameters={
            "operation": "generate_content",
            "contents": [{"role": "user", "parts": [{"text": "hi"}]}],
        },
        credentials={"google_genai_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="Resource has been exhausted"):
        await GoogleGenAINode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Gemini",
        type="weftlyflow.google_genai",
        parameters={
            "operation": "generate_content",
            "contents": [{"role": "user", "parts": [{"text": "hi"}]}],
        },
        credentials={},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await GoogleGenAINode().execute(_ctx_for(node), [Item()])


async def test_empty_api_key_raises() -> None:
    node = Node(
        id="node_1",
        name="Gemini",
        type="weftlyflow.google_genai",
        parameters={
            "operation": "generate_content",
            "contents": [{"role": "user", "parts": [{"text": "hi"}]}],
        },
        credentials={"google_genai_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="empty 'api_key'"):
        await GoogleGenAINode().execute(
            _ctx_for(node, resolver=_resolver(api_key="")),
            [Item()],
        )


def test_unsupported_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("not_a_real_op", {})
