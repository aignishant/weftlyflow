"""Unit tests for :class:`EmbedOpenAINode`.

Focuses on the traits that are *distinctive* to the OpenAI-backed
embedder relative to the in-process ``embed_local``:

* it shares the ``weftlyflow.openai_api`` credential (Bearer + org +
  project scoping headers),
* it batches every input item into one ``POST /v1/embeddings`` call,
* it maps embeddings back to source items by the ``index`` field so
  out-of-order responses are handled correctly,
* it preserves the source item body and writes the canonical RAG
  envelope (``<output_field>``, ``embedding_dimensions``,
  ``embedding_model``).
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
from weftlyflow.nodes.ai.embed_openai import EmbedOpenAINode

_CRED_ID: str = "cr_openai"
_PROJECT_ID: str = "pr_test"
_TOKEN: str = "sk-test"
_ORG: str = "org-abc"
_PROJECT_HEADER: str = "proj_xyz"
_EMBEDDINGS_URL: str = "https://api.openai.com/v1/embeddings"


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


def _node(**parameters: object) -> Node:
    return Node(
        id="node_1",
        name="Embed",
        type="weftlyflow.embed_openai",
        parameters=dict(parameters),
        credentials={"openai_api": _CRED_ID},
    )


def _batch_response(
    *vectors: list[float],
    model: str = "text-embedding-3-small",
) -> Response:
    return Response(
        200,
        json={
            "object": "list",
            "data": [
                {"object": "embedding", "index": i, "embedding": v}
                for i, v in enumerate(vectors)
            ],
            "model": model,
        },
    )


# --- request shape ---------------------------------------------------


@respx.mock
async def test_single_batched_request_sends_every_text_as_a_list() -> None:
    route = respx.post(_EMBEDDINGS_URL).mock(
        return_value=_batch_response([0.1, 0.2], [0.3, 0.4]),
    )
    node = _node(text_field="text")
    await EmbedOpenAINode().execute(
        _ctx_for(node),
        [Item(json={"text": "hello"}), Item(json={"text": "world"})],
    )
    assert route.call_count == 1
    body = json.loads(route.calls.last.request.content)
    assert body["model"] == "text-embedding-3-small"
    assert body["input"] == ["hello", "world"]


@respx.mock
async def test_sends_bearer_and_scoping_headers() -> None:
    route = respx.post(_EMBEDDINGS_URL).mock(
        return_value=_batch_response([0.0]),
    )
    node = _node(text_field="text")
    await EmbedOpenAINode().execute(
        _ctx_for(node), [Item(json={"text": "hi"})],
    )
    request = route.calls.last.request
    assert request.headers["Authorization"] == f"Bearer {_TOKEN}"
    assert request.headers["OpenAI-Organization"] == _ORG
    assert request.headers["OpenAI-Project"] == _PROJECT_HEADER


@respx.mock
async def test_forwards_dimensions_and_user_fields_when_set() -> None:
    route = respx.post(_EMBEDDINGS_URL).mock(
        return_value=_batch_response([0.0] * 3),
    )
    node = _node(text_field="text", dimensions=3, user="u-42")
    await EmbedOpenAINode().execute(
        _ctx_for(node), [Item(json={"text": "hi"})],
    )
    body = json.loads(route.calls.last.request.content)
    assert body["dimensions"] == 3
    assert body["user"] == "u-42"


@respx.mock
async def test_omits_dimensions_and_user_when_blank() -> None:
    route = respx.post(_EMBEDDINGS_URL).mock(
        return_value=_batch_response([0.0]),
    )
    node = _node(text_field="text")
    await EmbedOpenAINode().execute(
        _ctx_for(node), [Item(json={"text": "hi"})],
    )
    body = json.loads(route.calls.last.request.content)
    assert "dimensions" not in body
    assert "user" not in body


@respx.mock
async def test_defaults_to_chunk_text_field_for_splitter_interop() -> None:
    route = respx.post(_EMBEDDINGS_URL).mock(
        return_value=_batch_response([0.5, 0.5]),
    )
    await EmbedOpenAINode().execute(
        _ctx_for(_node()),
        [Item(json={"chunk": "splitter-produced text", "chunk_index": 0})],
    )
    body = json.loads(route.calls.last.request.content)
    assert body["input"] == ["splitter-produced text"]


@respx.mock
async def test_coerces_non_string_text_via_str() -> None:
    route = respx.post(_EMBEDDINGS_URL).mock(
        return_value=_batch_response([0.0]),
    )
    await EmbedOpenAINode().execute(
        _ctx_for(_node(text_field="n")),
        [Item(json={"n": 42})],
    )
    body = json.loads(route.calls.last.request.content)
    assert body["input"] == ["42"]


# --- output envelope -------------------------------------------------


@respx.mock
async def test_output_item_has_canonical_rag_envelope() -> None:
    respx.post(_EMBEDDINGS_URL).mock(
        return_value=_batch_response([0.1, 0.2, 0.3]),
    )
    out = await EmbedOpenAINode().execute(
        _ctx_for(_node(text_field="text")),
        [Item(json={"text": "hi", "source": "doc.md"})],
    )
    payload = out[0][0].json
    assert payload["embedding"] == [0.1, 0.2, 0.3]
    assert payload["embedding_dimensions"] == 3
    assert payload["embedding_model"] == "text-embedding-3-small"
    assert payload["source"] == "doc.md"


@respx.mock
async def test_honours_custom_output_field() -> None:
    respx.post(_EMBEDDINGS_URL).mock(
        return_value=_batch_response([0.1, 0.2]),
    )
    out = await EmbedOpenAINode().execute(
        _ctx_for(_node(text_field="text", output_field="vec")),
        [Item(json={"text": "hi"})],
    )
    payload = out[0][0].json
    assert payload["vec"] == [0.1, 0.2]
    assert "embedding" not in payload


@respx.mock
async def test_uses_requested_model_in_envelope_metadata() -> None:
    respx.post(_EMBEDDINGS_URL).mock(
        return_value=_batch_response([0.0], model="text-embedding-3-large"),
    )
    out = await EmbedOpenAINode().execute(
        _ctx_for(_node(text_field="text", model="text-embedding-3-large")),
        [Item(json={"text": "hi"})],
    )
    assert out[0][0].json["embedding_model"] == "text-embedding-3-large"


@respx.mock
async def test_maps_vectors_to_source_items_by_index_even_if_reordered() -> None:
    # OpenAI preserves submission order in practice, but the ``index``
    # field is the documented authority. Return entries out of order to
    # prove we sort by it.
    respx.post(_EMBEDDINGS_URL).mock(
        return_value=Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"object": "embedding", "index": 1, "embedding": [2.0]},
                    {"object": "embedding", "index": 0, "embedding": [1.0]},
                ],
                "model": "text-embedding-3-small",
            },
        ),
    )
    out = await EmbedOpenAINode().execute(
        _ctx_for(_node(text_field="text")),
        [Item(json={"text": "a"}), Item(json={"text": "b"})],
    )
    assert out[0][0].json["embedding"] == [1.0]
    assert out[0][1].json["embedding"] == [2.0]


# --- empty input -----------------------------------------------------


async def test_empty_item_list_emits_empty_output_without_http_call() -> None:
    # No respx.mock: any outbound request would error.
    out = await EmbedOpenAINode().execute(_ctx_for(_node()), [])
    assert out == [[]]


# --- errors ----------------------------------------------------------


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1", name="Embed", type="weftlyflow.embed_openai",
        parameters={"text_field": "text"}, credentials={},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await EmbedOpenAINode().execute(
            _ctx_for(node), [Item(json={"text": "hi"})],
        )


async def test_empty_api_key_raises() -> None:
    with pytest.raises(NodeExecutionError, match="empty 'api_key'"):
        await EmbedOpenAINode().execute(
            _ctx_for(_node(text_field="text"), resolver=_resolver(token="")),
            [Item(json={"text": "hi"})],
        )


@respx.mock
async def test_api_error_surfaces_openai_message() -> None:
    respx.post(_EMBEDDINGS_URL).mock(
        return_value=Response(
            401, json={"error": {"message": "Invalid API key"}},
        ),
    )
    with pytest.raises(NodeExecutionError, match="Invalid API key"):
        await EmbedOpenAINode().execute(
            _ctx_for(_node(text_field="text")),
            [Item(json={"text": "hi"})],
        )


@respx.mock
async def test_rejects_zero_dimensions() -> None:
    # respx mock ensures we surface the validation error, not a network one.
    respx.post(_EMBEDDINGS_URL).mock(return_value=_batch_response([0.0]))
    with pytest.raises(NodeExecutionError, match="'dimensions' must be >= 1"):
        await EmbedOpenAINode().execute(
            _ctx_for(_node(text_field="text", dimensions=0)),
            [Item(json={"text": "hi"})],
        )


@respx.mock
async def test_rejects_non_integer_dimensions() -> None:
    respx.post(_EMBEDDINGS_URL).mock(return_value=_batch_response([0.0]))
    with pytest.raises(NodeExecutionError, match="integer"):
        await EmbedOpenAINode().execute(
            _ctx_for(_node(text_field="text", dimensions="many")),
            [Item(json={"text": "hi"})],
        )


@respx.mock
async def test_mismatched_response_length_raises() -> None:
    respx.post(_EMBEDDINGS_URL).mock(
        return_value=_batch_response([0.0]),  # one vector for two items
    )
    with pytest.raises(NodeExecutionError, match="expected 2 embeddings"):
        await EmbedOpenAINode().execute(
            _ctx_for(_node(text_field="text")),
            [Item(json={"text": "a"}), Item(json={"text": "b"})],
        )


@respx.mock
async def test_missing_data_key_raises() -> None:
    respx.post(_EMBEDDINGS_URL).mock(
        return_value=Response(200, json={"object": "list"}),
    )
    with pytest.raises(NodeExecutionError, match="expected 1 embeddings"):
        await EmbedOpenAINode().execute(
            _ctx_for(_node(text_field="text")),
            [Item(json={"text": "hi"})],
        )
