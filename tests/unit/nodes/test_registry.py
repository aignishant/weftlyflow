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
    # ``weftlyflow.code`` is intentionally absent from the default discovery
    # set: it is gated behind ``settings.enable_code_node`` until the
    # subprocess sandbox runner lands (see IMPLEMENTATION_BIBLE.md §26
    # risk #2). Flip ``WEFTLYFLOW_ENABLE_CODE_NODE=true`` in environments
    # that accept the in-process RestrictedPython threat model.
    reg = NodeRegistry()
    added = reg.load_builtins()
    assert added == 121
    types = {spec.type for spec in reg.catalog()}
    assert types == {
        "weftlyflow.manual_trigger",
        "weftlyflow.no_op",
        "weftlyflow.set",
        "weftlyflow.if",
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
        "weftlyflow.split_in_batches",
        "weftlyflow.transform",
        "weftlyflow.html_parse",
        "weftlyflow.xml_parse",
        "weftlyflow.compare_datasets",
        "weftlyflow.read_binary_file",
        "weftlyflow.write_binary_file",
        "weftlyflow.function_call",
        "weftlyflow.wait",
        "weftlyflow.slack",
        "weftlyflow.github",
        "weftlyflow.sendgrid",
        "weftlyflow.notion",
        "weftlyflow.stripe",
        "weftlyflow.google_sheets",
        "weftlyflow.discord",
        "weftlyflow.airtable",
        "weftlyflow.mailgun",
        "weftlyflow.telegram",
        "weftlyflow.trello",
        "weftlyflow.hubspot",
        "weftlyflow.jira",
        "weftlyflow.shopify",
        "weftlyflow.clickup",
        "weftlyflow.twilio",
        "weftlyflow.gitlab",
        "weftlyflow.intercom",
        "weftlyflow.monday",
        "weftlyflow.zendesk",
        "weftlyflow.brevo",
        "weftlyflow.pagerduty",
        "weftlyflow.algolia",
        "weftlyflow.mailchimp",
        "weftlyflow.pipedrive",
        "weftlyflow.zoho_crm",
        "weftlyflow.mattermost",
        "weftlyflow.cloudflare",
        "weftlyflow.freshdesk",
        "weftlyflow.supabase",
        "weftlyflow.okta",
        "weftlyflow.linear",
        "weftlyflow.pushover",
        "weftlyflow.elasticsearch",
        "weftlyflow.dropbox",
        "weftlyflow.twitch",
        "weftlyflow.salesforce",
        "weftlyflow.zoom",
        "weftlyflow.microsoft_graph",
        "weftlyflow.asana",
        "weftlyflow.box",
        "weftlyflow.snowflake",
        "weftlyflow.datadog",
        "weftlyflow.activecampaign",
        "weftlyflow.aws_s3",
        "weftlyflow.openai",
        "weftlyflow.xero",
        "weftlyflow.netsuite",
        "weftlyflow.quickbooks",
        "weftlyflow.square",
        "weftlyflow.facebook_graph",
        "weftlyflow.anthropic",
        "weftlyflow.bitbucket",
        "weftlyflow.paypal",
        "weftlyflow.mapbox",
        "weftlyflow.rocket_chat",
        "weftlyflow.contentful",
        "weftlyflow.hasura",
        "weftlyflow.ghost",
        "weftlyflow.pinecone",
        "weftlyflow.gmail",
        "weftlyflow.google_drive",
        "weftlyflow.onedrive",
        "weftlyflow.segment",
        "weftlyflow.mixpanel",
        "weftlyflow.posthog",
        "weftlyflow.plaid",
        "weftlyflow.klaviyo",
        "weftlyflow.harvest",
        "weftlyflow.mongodb_atlas",
        "weftlyflow.ga4",
        "weftlyflow.reddit",
        "weftlyflow.coinbase",
        "weftlyflow.binance",
        "weftlyflow.alpaca",
        "weftlyflow.asc",
        "weftlyflow.docusign",
        "weftlyflow.cloudinary",
        "weftlyflow.gcs",
        "weftlyflow.azure_blob",
        "weftlyflow.backblaze_b2",
        "weftlyflow.ollama",
        "weftlyflow.memory_buffer",
        "weftlyflow.memory_window",
        "weftlyflow.memory_summary",
        "weftlyflow.guard_pii_redact",
        "weftlyflow.guard_jailbreak_detect",
        "weftlyflow.guard_schema_enforce",
        "weftlyflow.text_splitter",
        "weftlyflow.vector_memory",
        "weftlyflow.embed_local",
        "weftlyflow.chat_respond",
        "weftlyflow.agent_tool_dispatch",
        "weftlyflow.agent_tool_result",
        "weftlyflow.trigger_chat",
        "weftlyflow.google_genai",
        "weftlyflow.mistral",
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
