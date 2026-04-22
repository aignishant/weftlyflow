"""Tests for :class:`weftlyflow.nodes.registry.NodeRegistry`."""

from __future__ import annotations

import pytest

from weftlyflow.domain.node_spec import NodeCategory, NodeSpec
from weftlyflow.nodes.base import BaseNode
from weftlyflow.nodes.core.no_op import NoOpNode
from weftlyflow.nodes.registry import NodeRegistry, NodeRegistryError, register_node


class _FakeNodeV1(BaseNode):
    spec = NodeSpec(
        type="test.fake",
        version=1,
        display_name="Fake v1",
        description="test",
        icon="x",
        category=NodeCategory.CORE,
    )

    async def execute(self, ctx, items):  # type: ignore[no-untyped-def]
        return [items]


class _FakeNodeV2(BaseNode):
    spec = NodeSpec(
        type="test.fake",
        version=2,
        display_name="Fake v2",
        description="test",
        icon="x",
        category=NodeCategory.CORE,
    )

    async def execute(self, ctx, items):  # type: ignore[no-untyped-def]
        return [items]


def test_register_and_get():
    reg = NodeRegistry()
    reg.register(_FakeNodeV1)
    assert reg.get("test.fake", 1) is _FakeNodeV1


def test_duplicate_registration_raises():
    reg = NodeRegistry()
    reg.register(_FakeNodeV1)
    with pytest.raises(NodeRegistryError):
        reg.register(_FakeNodeV1)


def test_replace_true_allows_overwrite():
    reg = NodeRegistry()
    reg.register(_FakeNodeV1)
    reg.register(_FakeNodeV1, replace=True)  # no raise
    assert len(reg) == 1


def test_latest_returns_highest_version():
    reg = NodeRegistry()
    reg.register(_FakeNodeV1)
    reg.register(_FakeNodeV2)
    assert reg.latest("test.fake") is _FakeNodeV2


def test_latest_raises_for_unknown_type():
    with pytest.raises(NodeRegistryError):
        NodeRegistry().latest("nope")


def test_register_node_decorator_registers_class():
    reg = NodeRegistry()
    register = register_node(reg)

    @register
    class _FakeV3(BaseNode):
        spec = NodeSpec(
            type="test.decorated",
            version=1,
            display_name="Decorated",
            description="x",
            icon="x",
            category=NodeCategory.CORE,
        )

        async def execute(self, ctx, items):  # type: ignore[no-untyped-def]
            return [items]

    assert ("test.decorated", 1) in reg


def test_load_builtins_registers_every_core_node():
    reg = NodeRegistry()
    added = reg.load_builtins()
    assert added == 17
    types = {spec.type for spec in reg.catalog()}
    assert types == {
        "weftlyflow.manual_trigger",
        "weftlyflow.no_op",
        "weftlyflow.set",
        "weftlyflow.if",
        "weftlyflow.code",
        "weftlyflow.webhook_trigger",
        "weftlyflow.schedule_trigger",
        "weftlyflow.http_request",
        "weftlyflow.switch",
        "weftlyflow.filter",
        "weftlyflow.merge",
        "weftlyflow.rename_keys",
        "weftlyflow.datetime_ops",
        "weftlyflow.evaluate_expression",
        "weftlyflow.stop_and_error",
        "weftlyflow.execution_data",
        "weftlyflow.slack",
    }


def test_load_builtins_is_idempotent_with_replace_false_on_second_call():
    reg = NodeRegistry()
    reg.load_builtins()
    with pytest.raises(NodeRegistryError):
        reg.load_builtins()


def test_missing_spec_attribute_raises():
    class NoSpec(BaseNode):
        async def execute(self, ctx, items):  # type: ignore[no-untyped-def]
            return [items]

    with pytest.raises(NodeRegistryError):
        NodeRegistry().register(NoSpec)


def test_catalog_returns_every_registered_spec():
    reg = NodeRegistry()
    reg.register(NoOpNode)
    catalog = reg.catalog()
    assert len(catalog) == 1
    assert catalog[0].type == "weftlyflow.no_op"
