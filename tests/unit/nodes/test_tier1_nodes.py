"""Per-node unit tests for the remaining Tier-1 Weftlyflow nodes.

Separate from ``test_phase6_nodes`` to keep each test file under the 400-line
project guideline while preserving the one-behaviour-per-test convention.
"""

from __future__ import annotations

from typing import Any

from tests.unit.engine.conftest import build_workflow
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.core.html_parse_node import HtmlParseNode
from weftlyflow.nodes.core.split_in_batches import SplitInBatchesNode
from weftlyflow.nodes.core.transform_node import TransformNode


def _ctx_for(
    node: Node,
    *,
    inputs: dict[str, list[Item]] | None = None,
    static_data: dict[str, Any] | None = None,
    mode: str = "manual",
) -> ExecutionContext:
    wf = build_workflow([node], [])
    return ExecutionContext(
        workflow=wf,
        execution_id="ex_test",
        mode=mode,  # type: ignore[arg-type]
        node=node,
        inputs=inputs or {},
        static_data=static_data if static_data is not None else {},
    )


# --- Split In Batches -------------------------------------------------------


async def test_split_in_batches_emits_first_batch_on_batch_port() -> None:
    node = Node(
        id="n_split", name="chunk", type="weftlyflow.split_in_batches",
        parameters={"batch_size": 2},
    )
    items = [Item(json={"i": i}) for i in range(5)]
    ctx = _ctx_for(node, inputs={"main": items})
    out = await SplitInBatchesNode().execute(ctx, items)
    assert [it.json["i"] for it in out[0]] == [0, 1]
    assert out[1] == []
    assert ctx.static_data["split_in_batches:n_split:cursor"] == 2


async def test_split_in_batches_advances_cursor_across_calls() -> None:
    node = Node(
        id="n_split", name="chunk", type="weftlyflow.split_in_batches",
        parameters={"batch_size": 2},
    )
    items = [Item(json={"i": i}) for i in range(5)]
    state: dict[str, Any] = {}
    ctx = _ctx_for(node, inputs={"main": items}, static_data=state)

    first = await SplitInBatchesNode().execute(ctx, items)
    assert [it.json["i"] for it in first[0]] == [0, 1]

    second = await SplitInBatchesNode().execute(ctx, items)
    assert [it.json["i"] for it in second[0]] == [2, 3]

    third = await SplitInBatchesNode().execute(ctx, items)
    assert [it.json["i"] for it in third[0]] == [4]


async def test_split_in_batches_emits_done_when_exhausted() -> None:
    node = Node(
        id="n_split", name="chunk", type="weftlyflow.split_in_batches",
        parameters={"batch_size": 5},
    )
    items = [Item(json={"i": i}) for i in range(3)]
    state: dict[str, Any] = {"split_in_batches:n_split:cursor": 3}
    ctx = _ctx_for(node, inputs={"main": items}, static_data=state)

    out = await SplitInBatchesNode().execute(ctx, items)
    assert out[0] == []
    assert [it.json["i"] for it in out[1]] == [0, 1, 2]
    # Cursor resets so a subsequent run starts fresh.
    assert ctx.static_data["split_in_batches:n_split:cursor"] == 0


async def test_split_in_batches_reset_flag_restarts_iteration() -> None:
    node = Node(
        id="n_split", name="chunk", type="weftlyflow.split_in_batches",
        parameters={"batch_size": 2, "reset": True},
    )
    items = [Item(json={"i": i}) for i in range(3)]
    state: dict[str, Any] = {"split_in_batches:n_split:cursor": 99}
    ctx = _ctx_for(node, inputs={"main": items}, static_data=state)

    out = await SplitInBatchesNode().execute(ctx, items)
    assert [it.json["i"] for it in out[0]] == [0, 1]
    assert ctx.static_data["split_in_batches:n_split:cursor"] == 2


async def test_split_in_batches_rejects_non_positive_size() -> None:
    import pytest

    node = Node(
        id="n_split", name="chunk", type="weftlyflow.split_in_batches",
        parameters={"batch_size": 0},
    )
    with pytest.raises(ValueError, match=">= 1"):
        await SplitInBatchesNode().execute(_ctx_for(node), [Item()])


# --- Transform --------------------------------------------------------------


async def test_transform_adds_fields_computed_from_expressions() -> None:
    node = Node(
        id="n_t", name="t", type="weftlyflow.transform",
        parameters={
            "mode": "merge",
            "assignments": [
                {"name": "upper", "value": "{{ $json.name.upper() }}"},
                {"name": "doubled", "value": "{{ $json.n * 2 }}"},
            ],
        },
    )
    items = [Item(json={"name": "ada", "n": 3}), Item(json={"name": "grace", "n": 5})]
    ctx = _ctx_for(node, inputs={"main": items})
    out = await TransformNode().execute(ctx, items)
    payloads = [it.json for it in out[0]]
    assert payloads[0] == {"name": "ada", "n": 3, "upper": "ADA", "doubled": 6}
    assert payloads[1] == {"name": "grace", "n": 5, "upper": "GRACE", "doubled": 10}


async def test_transform_replace_mode_drops_untouched_keys() -> None:
    node = Node(
        id="n_t", name="t", type="weftlyflow.transform",
        parameters={
            "mode": "replace",
            "assignments": [
                {"name": "id", "value": "{{ $json.id }}"},
                {"name": "label", "value": "x-{{ $json.id }}"},
            ],
        },
    )
    items = [Item(json={"id": 1, "secret": "keep-out"})]
    ctx = _ctx_for(node, inputs={"main": items})
    out = await TransformNode().execute(ctx, items)
    assert out[0][0].json == {"id": 1, "label": "x-1"}


async def test_transform_supports_dotted_destinations() -> None:
    node = Node(
        id="n_t", name="t", type="weftlyflow.transform",
        parameters={
            "mode": "merge",
            "assignments": [
                {"name": "nested.value", "value": "{{ $json.raw }}"},
            ],
        },
    )
    items = [Item(json={"raw": "hi"})]
    ctx = _ctx_for(node, inputs={"main": items})
    out = await TransformNode().execute(ctx, items)
    assert out[0][0].json == {"raw": "hi", "nested": {"value": "hi"}}


async def test_transform_rejects_unknown_mode() -> None:
    import pytest

    node = Node(
        id="n_t", name="t", type="weftlyflow.transform",
        parameters={"mode": "weird", "assignments": []},
    )
    with pytest.raises(ValueError, match="unknown mode"):
        await TransformNode().execute(_ctx_for(node), [Item()])


async def test_transform_passthrough_when_no_assignments() -> None:
    node = Node(
        id="n_t", name="t", type="weftlyflow.transform",
        parameters={"assignments": []},
    )
    items = [Item(json={"a": 1}), Item(json={"a": 2})]
    out = await TransformNode().execute(_ctx_for(node, inputs={"main": items}), items)
    assert [it.json for it in out[0]] == [{"a": 1}, {"a": 2}]


# --- HTML Parse -------------------------------------------------------------

_SAMPLE_HTML: str = """
<html>
  <body>
    <h1 class="title">Hello <em>World</em></h1>
    <ul>
      <li class="tag">one</li>
      <li class="tag">two</li>
      <li class="tag">three</li>
    </ul>
    <a id="link" href="https://example.com">example</a>
  </body>
</html>
"""


async def test_html_parse_extracts_text_from_first_match() -> None:
    node = Node(
        id="n_h", name="h", type="weftlyflow.html_parse",
        parameters={
            "source_path": "html",
            "extractions": [
                {"name": "title", "selector": "h1.title", "return": "text"},
            ],
        },
    )
    items = [Item(json={"html": _SAMPLE_HTML})]
    out = await HtmlParseNode().execute(_ctx_for(node, inputs={"main": items}), items)
    assert out[0][0].json["title"] == "Hello World"


async def test_html_parse_return_all_collects_matches() -> None:
    node = Node(
        id="n_h", name="h", type="weftlyflow.html_parse",
        parameters={
            "source_path": "html",
            "extractions": [
                {"name": "tags", "selector": "li.tag", "return_all": True},
            ],
        },
    )
    items = [Item(json={"html": _SAMPLE_HTML})]
    out = await HtmlParseNode().execute(_ctx_for(node, inputs={"main": items}), items)
    assert out[0][0].json["tags"] == ["one", "two", "three"]


async def test_html_parse_attribute_mode_returns_attribute_value() -> None:
    node = Node(
        id="n_h", name="h", type="weftlyflow.html_parse",
        parameters={
            "source_path": "html",
            "extractions": [
                {
                    "name": "link_href",
                    "selector": "#link",
                    "return": "attribute",
                    "attribute_name": "href",
                },
            ],
        },
    )
    items = [Item(json={"html": _SAMPLE_HTML})]
    out = await HtmlParseNode().execute(_ctx_for(node, inputs={"main": items}), items)
    assert out[0][0].json["link_href"] == "https://example.com"


async def test_html_parse_missing_match_yields_none() -> None:
    node = Node(
        id="n_h", name="h", type="weftlyflow.html_parse",
        parameters={
            "extractions": [{"name": "missing", "selector": "span.none"}],
        },
    )
    items = [Item(json={"html": "<p>hi</p>"})]
    out = await HtmlParseNode().execute(_ctx_for(node, inputs={"main": items}), items)
    assert out[0][0].json["missing"] is None


async def test_html_parse_rejects_non_string_source() -> None:
    import pytest

    node = Node(
        id="n_h", name="h", type="weftlyflow.html_parse",
        parameters={
            "extractions": [{"name": "x", "selector": "h1"}],
        },
    )
    items = [Item(json={"html": 42})]
    with pytest.raises(ValueError, match="not a string"):
        await HtmlParseNode().execute(_ctx_for(node, inputs={"main": items}), items)


async def test_html_parse_attribute_without_name_raises() -> None:
    import pytest

    node = Node(
        id="n_h", name="h", type="weftlyflow.html_parse",
        parameters={
            "extractions": [
                {"name": "x", "selector": "a", "return": "attribute"},
            ],
        },
    )
    with pytest.raises(ValueError, match="attribute_name"):
        await HtmlParseNode().execute(_ctx_for(node), [Item(json={"html": "<a/>"})])
