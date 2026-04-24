"""Unit tests for :class:`AgentReactNode`.

Covers the composed ReAct orchestrator against both OpenAI and
Anthropic credentials:

* auto-detection of the provider from the credential slug,
* translation of the neutral ``{name, description, parameters}``
  tool shape into each provider's native wire format,
* OpenAI-specific ``tool_calls`` parsing and Anthropic-specific
  interleaved ``tool_use`` blocks,
* port routing: ``final`` for plain-text turns, ``calls`` for
  tool-use turns,
* history carry-forward (appended assistant message ready for
  downstream :class:`AgentToolResultNode` -> next ``agent_react``).
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import (
    AnthropicApiCredential,
    OpenAIApiCredential,
)
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.ai.agent_react import AgentReactNode

_OPENAI_CRED_ID: str = "cr_openai"
_ANTHROPIC_CRED_ID: str = "cr_anthropic"
_PROJECT_ID: str = "pr_test"
_OPENAI_KEY: str = "sk-test"
_ANTHROPIC_KEY: str = "ant-test"
_OPENAI_URL: str = "https://api.openai.com/v1/chat/completions"
_ANTHROPIC_URL: str = "https://api.anthropic.com/v1/messages"


def _openai_resolver() -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.openai_api": OpenAIApiCredential},
        rows={
            _OPENAI_CRED_ID: (
                "weftlyflow.openai_api",
                {"api_key": _OPENAI_KEY},
                _PROJECT_ID,
            ),
        },
    )


def _anthropic_resolver() -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.anthropic_api": AnthropicApiCredential},
        rows={
            _ANTHROPIC_CRED_ID: (
                "weftlyflow.anthropic_api",
                {"api_key": _ANTHROPIC_KEY},
                _PROJECT_ID,
            ),
        },
    )


def _ctx_for(
    node: Node,
    *,
    resolver: InMemoryCredentialResolver,
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


def _openai_node(**parameters: object) -> Node:
    return Node(
        id="node_1",
        name="ReAct",
        type="weftlyflow.agent_react",
        parameters=dict(parameters),
        credentials={"llm_api": _OPENAI_CRED_ID},
    )


def _anthropic_node(**parameters: object) -> Node:
    return Node(
        id="node_1",
        name="ReAct",
        type="weftlyflow.agent_react",
        parameters=dict(parameters),
        credentials={"llm_api": _ANTHROPIC_CRED_ID},
    )


# --- OpenAI: final-answer path --------------------------------------


@respx.mock
async def test_openai_final_answer_routes_to_final_port() -> None:
    respx.post(_OPENAI_URL).mock(
        return_value=Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Paris.",
                        },
                        "finish_reason": "stop",
                    },
                ],
            },
        ),
    )
    node = _openai_node(model="gpt-4o-mini")
    out = await AgentReactNode().execute(
        _ctx_for(node, resolver=_openai_resolver()),
        [Item(json={"history": [{"role": "user", "content": "Capital of France?"}]})],
    )
    finals, calls = out[0], out[1]
    assert len(finals) == 1
    assert calls == []
    payload = finals[0].json
    assert payload["content"] == "Paris."
    assert payload["history"][-1] == {
        "role": "assistant",
        "content": "Paris.",
    }


@respx.mock
async def test_openai_request_wraps_neutral_tools_in_function_shape() -> None:
    route = respx.post(_OPENAI_URL).mock(
        return_value=Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
        ),
    )
    node = _openai_node(model="gpt-4o-mini", system="Be terse.")
    await AgentReactNode().execute(
        _ctx_for(node, resolver=_openai_resolver()),
        [
            Item(json={
                "history": [{"role": "user", "content": "Weather in Paris?"}],
                "tools": [
                    {
                        "name": "get_weather",
                        "description": "Get current weather.",
                        "parameters": {
                            "type": "object",
                            "properties": {"city": {"type": "string"}},
                        },
                    },
                ],
            }),
        ],
    )
    body = json.loads(route.calls.last.request.content)
    assert body["model"] == "gpt-4o-mini"
    assert body["messages"][0] == {"role": "system", "content": "Be terse."}
    assert body["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get current weather.",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                },
            },
        },
    ]


@respx.mock
async def test_openai_tool_call_fans_out_on_calls_port() -> None:
    respx.post(_OPENAI_URL).mock(
        return_value=Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "get_weather",
                                        "arguments": '{"city": "Paris"}',
                                    },
                                },
                                {
                                    "id": "call_2",
                                    "type": "function",
                                    "function": {
                                        "name": "get_weather",
                                        "arguments": '{"city": "Berlin"}',
                                    },
                                },
                            ],
                        },
                    },
                ],
            },
        ),
    )
    node = _openai_node(model="gpt-4o-mini")
    seed = [
        Item(json={
            "history": [
                {"role": "user", "content": "Compare Paris and Berlin weather."},
            ],
        }),
    ]
    out = await AgentReactNode().execute(
        _ctx_for(node, resolver=_openai_resolver()), seed,
    )
    finals, calls = out[0], out[1]
    assert finals == []
    assert len(calls) == 2
    first = calls[0].json
    assert first["tool_name"] == "get_weather"
    assert first["tool_args"] == {"city": "Paris"}
    assert first["tool_call_id"] == "call_1"
    assert first["call_index"] == 0
    assert first["call_total"] == 2
    # The full assistant message (content=None with tool_calls) is
    # carried forward so the caller can append tool_result messages
    # against it verbatim.
    assistant = first["history"][-1]
    assert assistant["role"] == "assistant"
    assert assistant["tool_calls"][0]["id"] == "call_1"


# --- Anthropic: shape differences -----------------------------------


@respx.mock
async def test_anthropic_request_strips_system_and_uses_input_schema() -> None:
    route = respx.post(_ANTHROPIC_URL).mock(
        return_value=Response(
            200,
            json={"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
        ),
    )
    node = _anthropic_node(model="claude-3-5-sonnet-latest")
    await AgentReactNode().execute(
        _ctx_for(node, resolver=_anthropic_resolver()),
        [
            Item(json={
                "history": [
                    {"role": "system", "content": "Be terse."},
                    {"role": "user", "content": "Hi"},
                ],
                "tools": [
                    {
                        "name": "search",
                        "description": "Search docs.",
                        "parameters": {"type": "object", "properties": {}},
                    },
                ],
            }),
        ],
    )
    body = json.loads(route.calls.last.request.content)
    # Anthropic does not accept role=system in messages.
    assert all(m.get("role") != "system" for m in body["messages"])
    assert body["system"] == "Be terse."
    # Anthropic uses input_schema, not parameters.
    assert body["tools"] == [
        {
            "name": "search",
            "description": "Search docs.",
            "input_schema": {"type": "object", "properties": {}},
        },
    ]
    # max_tokens is mandatory on Anthropic; defaulted to 1024 when absent.
    assert body["max_tokens"] == 1024


@respx.mock
async def test_anthropic_tool_use_blocks_fan_out_on_calls_port() -> None:
    respx.post(_ANTHROPIC_URL).mock(
        return_value=Response(
            200,
            json={
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "let me check"},
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "get_weather",
                        "input": {"city": "Paris"},
                    },
                ],
            },
        ),
    )
    node = _anthropic_node(model="claude-3-5-sonnet-latest")
    out = await AgentReactNode().execute(
        _ctx_for(node, resolver=_anthropic_resolver()),
        [Item(json={"history": [{"role": "user", "content": "Weather?"}]})],
    )
    finals, calls = out[0], out[1]
    assert finals == []
    assert len(calls) == 1
    first = calls[0].json
    assert first["tool_name"] == "get_weather"
    assert first["tool_args"] == {"city": "Paris"}
    assert first["tool_call_id"] == "toolu_1"
    # The assistant message on history carries BOTH text and tool_use
    # blocks as Anthropic returned them.
    assistant = first["history"][-1]
    assert assistant["role"] == "assistant"
    assert any(b.get("type") == "tool_use" for b in assistant["content"])


@respx.mock
async def test_anthropic_final_text_concatenates_text_blocks() -> None:
    respx.post(_ANTHROPIC_URL).mock(
        return_value=Response(
            200,
            json={
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "The answer is "},
                    {"type": "text", "text": "42."},
                ],
            },
        ),
    )
    node = _anthropic_node(model="claude-3-5-sonnet-latest")
    out = await AgentReactNode().execute(
        _ctx_for(node, resolver=_anthropic_resolver()),
        [Item(json={"history": [{"role": "user", "content": "What?"}]})],
    )
    finals = out[0]
    assert finals[0].json["content"] == "The answer is 42."


# --- credential / provider wiring -----------------------------------


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1", name="ReAct", type="weftlyflow.agent_react",
        parameters={"model": "gpt-4o-mini"}, credentials={},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await AgentReactNode().execute(
            _ctx_for(node, resolver=_openai_resolver()),
            [Item(json={"history": []})],
        )


async def test_empty_api_key_raises() -> None:
    resolver = InMemoryCredentialResolver(
        types={"weftlyflow.openai_api": OpenAIApiCredential},
        rows={
            _OPENAI_CRED_ID: (
                "weftlyflow.openai_api", {"api_key": ""}, _PROJECT_ID,
            ),
        },
    )
    with pytest.raises(NodeExecutionError, match="empty 'api_key'"):
        await AgentReactNode().execute(
            _ctx_for(_openai_node(model="x"), resolver=resolver),
            [Item(json={"history": []})],
        )


async def test_missing_model_raises() -> None:
    with pytest.raises(NodeExecutionError, match="'model' is required"):
        await AgentReactNode().execute(
            _ctx_for(_openai_node(), resolver=_openai_resolver()),
            [Item(json={"history": []})],
        )


async def test_unsupported_provider_override_raises() -> None:
    with pytest.raises(NodeExecutionError, match="unsupported provider"):
        await AgentReactNode().execute(
            _ctx_for(
                _openai_node(model="x", provider="bedrock"),
                resolver=_openai_resolver(),
            ),
            [Item(json={"history": []})],
        )


# --- input validation ----------------------------------------------


async def test_non_list_history_raises() -> None:
    with pytest.raises(NodeExecutionError, match="'history' must be a list"):
        await AgentReactNode().execute(
            _ctx_for(_openai_node(model="x"), resolver=_openai_resolver()),
            [Item(json={"history": "not a list"})],
        )


async def test_non_list_tools_raises() -> None:
    with pytest.raises(NodeExecutionError, match="'tools' must be a list"):
        await AgentReactNode().execute(
            _ctx_for(_openai_node(model="x"), resolver=_openai_resolver()),
            [Item(json={"history": [], "tools": {"nope": "dict"}})],
        )


@respx.mock
async def test_invalid_max_tokens_raises() -> None:
    respx.post(_OPENAI_URL).mock(return_value=Response(200, json={"choices": []}))
    with pytest.raises(NodeExecutionError, match="'max_tokens' must be >= 1"):
        await AgentReactNode().execute(
            _ctx_for(
                _openai_node(model="gpt-4o-mini", max_tokens=0),
                resolver=_openai_resolver(),
            ),
            [Item(json={"history": []})],
        )


# --- api errors ----------------------------------------------------


@respx.mock
async def test_openai_api_error_surfaces_message() -> None:
    respx.post(_OPENAI_URL).mock(
        return_value=Response(
            401, json={"error": {"message": "Invalid API key"}},
        ),
    )
    with pytest.raises(NodeExecutionError, match="Invalid API key"):
        await AgentReactNode().execute(
            _ctx_for(
                _openai_node(model="gpt-4o-mini"),
                resolver=_openai_resolver(),
            ),
            [Item(json={"history": []})],
        )


@respx.mock
async def test_anthropic_api_error_surfaces_message() -> None:
    respx.post(_ANTHROPIC_URL).mock(
        return_value=Response(
            400, json={"error": {"message": "bad model", "type": "invalid"}},
        ),
    )
    with pytest.raises(NodeExecutionError, match="bad model"):
        await AgentReactNode().execute(
            _ctx_for(
                _anthropic_node(model="no-such"),
                resolver=_anthropic_resolver(),
            ),
            [Item(json={"history": []})],
        )


# --- auth / headers ------------------------------------------------


@respx.mock
async def test_openai_sends_bearer_header_via_credential_inject() -> None:
    route = respx.post(_OPENAI_URL).mock(
        return_value=Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
        ),
    )
    await AgentReactNode().execute(
        _ctx_for(_openai_node(model="gpt-4o-mini"), resolver=_openai_resolver()),
        [Item(json={"history": []})],
    )
    assert route.calls.last.request.headers["Authorization"] == f"Bearer {_OPENAI_KEY}"


@respx.mock
async def test_anthropic_sends_x_api_key_and_version_headers() -> None:
    route = respx.post(_ANTHROPIC_URL).mock(
        return_value=Response(
            200,
            json={"role": "assistant", "content": [{"type": "text", "text": "ok"}]},
        ),
    )
    await AgentReactNode().execute(
        _ctx_for(
            _anthropic_node(model="claude-3-5-sonnet-latest"),
            resolver=_anthropic_resolver(),
        ),
        [Item(json={"history": []})],
    )
    headers = route.calls.last.request.headers
    assert headers["x-api-key"] == _ANTHROPIC_KEY
    assert "anthropic-version" in headers
