"""Per-node unit tests for xml_parse / compare_datasets / binary-file /
function_call / wait nodes.

Kept separate from ``test_tier1_nodes`` so neither file grows past the
400-line project guideline.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from tests.unit.engine.conftest import build_workflow
from weftlyflow.binary import InMemoryBinaryStore
from weftlyflow.binary.store import BinaryStore
from weftlyflow.domain.execution import BinaryRef, Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.engine.subworkflow import SubWorkflowRunner
from weftlyflow.nodes.core.compare_datasets import CompareDatasetsNode
from weftlyflow.nodes.core.function_call import FunctionCallNode
from weftlyflow.nodes.core.read_binary_file import ReadBinaryFileNode
from weftlyflow.nodes.core.wait_node import WaitNode
from weftlyflow.nodes.core.write_binary_file import WriteBinaryFileNode
from weftlyflow.nodes.core.xml_parse_node import XmlParseNode


def _ctx_for(
    node: Node,
    *,
    inputs: dict[str, list[Item]] | None = None,
    static_data: dict[str, Any] | None = None,
    sub_workflow_runner: SubWorkflowRunner | None = None,
    binary_store: BinaryStore | None = None,
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
        sub_workflow_runner=sub_workflow_runner,
        binary_store=binary_store,
    )


# --- XML Parse --------------------------------------------------------------


async def test_xml_parse_converts_root_with_children() -> None:
    node = Node(
        id="n_x", name="x", type="weftlyflow.xml_parse",
        parameters={"source_path": "xml", "destination_path": "parsed"},
    )
    items = [Item(json={"xml": "<root a='1'><child>hi</child></root>"})]
    out = await XmlParseNode().execute(_ctx_for(node, inputs={"main": items}), items)
    parsed = out[0][0].json["parsed"]
    assert parsed["tag"] == "root"
    assert parsed["attrs"] == {"a": "1"}
    assert parsed["children"][0] == {
        "tag": "child",
        "attrs": {},
        "text": "hi",
        "children": [],
    }


async def test_xml_parse_strips_whitespace_only_text() -> None:
    node = Node(
        id="n_x", name="x", type="weftlyflow.xml_parse",
        parameters={"source_path": "xml", "destination_path": "parsed"},
    )
    items = [Item(json={"xml": "<root>   \n  </root>"})]
    out = await XmlParseNode().execute(_ctx_for(node, inputs={"main": items}), items)
    assert out[0][0].json["parsed"]["text"] is None


async def test_xml_parse_rejects_invalid_xml() -> None:
    node = Node(
        id="n_x", name="x", type="weftlyflow.xml_parse",
        parameters={"source_path": "xml"},
    )
    items = [Item(json={"xml": "<broken>"})]
    with pytest.raises(ValueError, match="invalid XML"):
        await XmlParseNode().execute(_ctx_for(node, inputs={"main": items}), items)


async def test_xml_parse_rejects_non_string_source() -> None:
    node = Node(
        id="n_x", name="x", type="weftlyflow.xml_parse",
        parameters={"source_path": "xml"},
    )
    items = [Item(json={"xml": 7})]
    with pytest.raises(ValueError, match="not a string"):
        await XmlParseNode().execute(_ctx_for(node, inputs={"main": items}), items)


# --- Compare Datasets -------------------------------------------------------


async def test_compare_datasets_buckets_each_combination() -> None:
    node = Node(
        id="n_c", name="c", type="weftlyflow.compare_datasets",
        parameters={"key": "id"},
    )
    left = [
        Item(json={"id": 1, "v": "a"}),  # same
        Item(json={"id": 2, "v": "x"}),  # different
        Item(json={"id": 3, "v": "only-a"}),
    ]
    right = [
        Item(json={"id": 1, "v": "a"}),
        Item(json={"id": 2, "v": "y"}),
        Item(json={"id": 4, "v": "only-b"}),
    ]
    ctx = _ctx_for(node, inputs={"main": left, "input_2": right})
    out = await CompareDatasetsNode().execute(ctx, left)
    a_only, b_only, same, diff = out
    assert [it.json["id"] for it in a_only] == [3]
    assert [it.json["id"] for it in b_only] == [4]
    assert [it.json["id"] for it in same] == [1]
    assert diff[0].json == {"a": {"id": 2, "v": "x"}, "b": {"id": 2, "v": "y"}}


async def test_compare_datasets_requires_key() -> None:
    node = Node(
        id="n_c", name="c", type="weftlyflow.compare_datasets",
        parameters={"key": ""},
    )
    with pytest.raises(ValueError, match="'key' is required"):
        await CompareDatasetsNode().execute(
            _ctx_for(node, inputs={"main": [], "input_2": []}), [],
        )


# --- Read / Write Binary File ----------------------------------------------


async def test_read_binary_file_attaches_ref_to_items(tmp_path: Path) -> None:
    source = tmp_path / "hello.txt"
    source.write_bytes(b"hello")
    node = Node(
        id="n_r", name="r", type="weftlyflow.read_binary_file",
        parameters={"path": str(source), "binary_property": "payload"},
    )
    items = [Item(json={})]
    out = await ReadBinaryFileNode().execute(_ctx_for(node, inputs={"main": items}), items)
    ref = out[0][0].binary["payload"]
    assert isinstance(ref, BinaryRef)
    assert ref.filename == "hello.txt"
    assert ref.size_bytes == 5
    assert ref.data_ref == f"fs:{source.resolve()}"


async def test_read_binary_file_rejects_missing_file(tmp_path: Path) -> None:
    node = Node(
        id="n_r", name="r", type="weftlyflow.read_binary_file",
        parameters={"path": str(tmp_path / "missing.bin")},
    )
    with pytest.raises(ValueError, match="is not a file"):
        await ReadBinaryFileNode().execute(
            _ctx_for(node, inputs={"main": [Item()]}), [Item()],
        )


async def test_write_binary_file_copies_fs_ref(tmp_path: Path) -> None:
    source = tmp_path / "in.bin"
    source.write_bytes(b"abc")
    dest = tmp_path / "out" / "out.bin"
    node = Node(
        id="n_w", name="w", type="weftlyflow.write_binary_file",
        parameters={"path": str(dest), "binary_property": "payload"},
    )
    ref = BinaryRef(
        filename="in.bin", mime_type="application/octet-stream",
        size_bytes=3, data_ref=f"fs:{source}",
    )
    items = [Item(json={}, binary={"payload": ref})]
    out = await WriteBinaryFileNode().execute(_ctx_for(node, inputs={"main": items}), items)
    assert dest.read_bytes() == b"abc"
    # Item is forwarded unchanged.
    assert out[0][0].binary["payload"] is ref


async def test_write_binary_file_rejects_non_fs_scheme(tmp_path: Path) -> None:
    node = Node(
        id="n_w", name="w", type="weftlyflow.write_binary_file",
        parameters={"path": str(tmp_path / "out.bin")},
    )
    ref = BinaryRef(filename=None, mime_type="x", size_bytes=1, data_ref="s3://b/k")
    items = [Item(json={}, binary={"data": ref})]
    with pytest.raises(ValueError, match="unsupported data_ref scheme"):
        await WriteBinaryFileNode().execute(
            _ctx_for(node, inputs={"main": items}), items,
        )


async def test_write_binary_file_honours_overwrite_false(tmp_path: Path) -> None:
    source = tmp_path / "in.bin"
    source.write_bytes(b"abc")
    dest = tmp_path / "out.bin"
    dest.write_bytes(b"existing")
    ref = BinaryRef(
        filename=None, mime_type="x", size_bytes=3, data_ref=f"fs:{source}",
    )
    items = [Item(json={}, binary={"data": ref})]
    node = Node(
        id="n_w", name="w", type="weftlyflow.write_binary_file",
        parameters={"path": str(dest), "overwrite": False},
    )
    with pytest.raises(ValueError, match="overwrite=False"):
        await WriteBinaryFileNode().execute(
            _ctx_for(node, inputs={"main": items}), items,
        )
    assert dest.read_bytes() == b"existing"


async def test_write_binary_file_uses_binary_store_for_non_fs_ref(
    tmp_path: Path,
) -> None:
    store = InMemoryBinaryStore()
    ref = await store.put(b"from-store", filename="b", mime_type="x")
    dest = tmp_path / "out" / "written.bin"
    node = Node(
        id="n_w", name="w", type="weftlyflow.write_binary_file",
        parameters={"path": str(dest)},
    )
    items = [Item(json={}, binary={"data": ref})]
    ctx = _ctx_for(node, inputs={"main": items}, binary_store=store)
    await WriteBinaryFileNode().execute(ctx, items)
    assert dest.read_bytes() == b"from-store"


# --- Function Call ----------------------------------------------------------


class _FakeRunner:
    def __init__(self, output: list[Item]) -> None:
        self.output = output
        self.called_with: dict[str, Any] = {}

    async def run(
        self,
        *,
        workflow_id: str,
        items: list[Item],
        parent_execution_id: str,
        project_id: str,
    ) -> list[Item]:
        self.called_with = {
            "workflow_id": workflow_id,
            "items": items,
            "parent_execution_id": parent_execution_id,
            "project_id": project_id,
        }
        return self.output


async def test_function_call_delegates_to_sub_workflow_runner() -> None:
    runner = _FakeRunner(output=[Item(json={"from": "child"})])
    node = Node(
        id="n_f", name="f", type="weftlyflow.function_call",
        parameters={"workflow_id": "wf_child", "forward": "main"},
    )
    items = [Item(json={"k": "v"})]
    ctx = _ctx_for(node, inputs={"main": items}, sub_workflow_runner=runner)
    out = await FunctionCallNode().execute(ctx, items)
    assert [it.json for it in out[0]] == [{"from": "child"}]
    assert runner.called_with["workflow_id"] == "wf_child"
    assert runner.called_with["items"] == items
    assert runner.called_with["parent_execution_id"] == "ex_test"


async def test_function_call_forward_none_sends_empty_items() -> None:
    runner = _FakeRunner(output=[])
    node = Node(
        id="n_f", name="f", type="weftlyflow.function_call",
        parameters={"workflow_id": "wf_child", "forward": "none"},
    )
    items = [Item(json={"k": "v"})]
    ctx = _ctx_for(node, inputs={"main": items}, sub_workflow_runner=runner)
    await FunctionCallNode().execute(ctx, items)
    assert runner.called_with["items"] == []


async def test_function_call_without_runner_raises() -> None:
    node = Node(
        id="n_f", name="f", type="weftlyflow.function_call",
        parameters={"workflow_id": "wf_child"},
    )
    with pytest.raises(ValueError, match="no sub_workflow_runner"):
        await FunctionCallNode().execute(_ctx_for(node), [])


async def test_function_call_requires_workflow_id() -> None:
    runner = _FakeRunner(output=[])
    node = Node(
        id="n_f", name="f", type="weftlyflow.function_call",
        parameters={"workflow_id": "  "},
    )
    with pytest.raises(ValueError, match="'workflow_id' is required"):
        await FunctionCallNode().execute(
            _ctx_for(node, sub_workflow_runner=runner), [],
        )


# --- Wait -------------------------------------------------------------------


async def test_wait_duration_forwards_items_after_sleep() -> None:
    node = Node(
        id="n_wt", name="wt", type="weftlyflow.wait",
        parameters={"mode": "duration", "seconds": 0.0},
    )
    items = [Item(json={"i": 1})]
    out = await WaitNode().execute(_ctx_for(node, inputs={"main": items}), items)
    assert [it.json for it in out[0]] == [{"i": 1}]


async def test_wait_rejects_negative_duration() -> None:
    node = Node(
        id="n_wt", name="wt", type="weftlyflow.wait",
        parameters={"mode": "duration", "seconds": -1},
    )
    with pytest.raises(ValueError, match="non-negative"):
        await WaitNode().execute(_ctx_for(node), [])


async def test_wait_until_past_timestamp_returns_immediately() -> None:
    node = Node(
        id="n_wt", name="wt", type="weftlyflow.wait",
        parameters={"mode": "until", "until_datetime": "2000-01-01T00:00:00Z"},
    )
    items = [Item(json={"i": 1})]
    out = await WaitNode().execute(_ctx_for(node, inputs={"main": items}), items)
    assert [it.json for it in out[0]] == [{"i": 1}]


async def test_wait_until_requires_iso8601() -> None:
    node = Node(
        id="n_wt", name="wt", type="weftlyflow.wait",
        parameters={"mode": "until", "until_datetime": "not-a-date"},
    )
    with pytest.raises(ValueError, match="not ISO-8601"):
        await WaitNode().execute(_ctx_for(node), [])


async def test_wait_cooperative_cancel_exits_early() -> None:
    node = Node(
        id="n_wt", name="wt", type="weftlyflow.wait",
        parameters={"mode": "duration", "seconds": 60.0},
    )
    ctx = _ctx_for(node)

    async def cancel_soon() -> None:
        await asyncio.sleep(0.05)
        ctx.canceled = True

    await asyncio.gather(
        WaitNode().execute(ctx, []),
        cancel_soon(),
    )
