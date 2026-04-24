"""Unit tests for the ``guard_pii_redact`` node and its detector helpers.

Split into two clusters: pure-function tests for the regex-based
detectors in :mod:`weftlyflow.nodes.ai.guard_pii_redact.patterns`, and
node-level tests driven through an :class:`ExecutionContext`.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.unit.engine.conftest import build_workflow
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.ai.guard_pii_redact import GuardPiiRedactNode
from weftlyflow.nodes.ai.guard_pii_redact.patterns import (
    ALL_KINDS,
    KIND_CREDIT_CARD,
    KIND_EMAIL,
    KIND_IBAN,
    KIND_IPV4,
    KIND_PHONE,
    detect,
    redact,
)


def _ctx_for(
    node: Node,
    *,
    static_data: dict[str, Any] | None = None,
) -> ExecutionContext:
    wf = build_workflow([node], [])
    return ExecutionContext(
        workflow=wf,
        execution_id="ex_test",
        mode="manual",
        node=node,
        inputs={"main": []},
        static_data=static_data if static_data is not None else {},
    )


# --- detectors -------------------------------------------------------


def test_detect_empty_text_returns_empty() -> None:
    assert detect("") == []


def test_detect_email() -> None:
    matches = detect("contact: alice@example.com!")
    assert [(k, m) for k, _, _, m in matches] == [(KIND_EMAIL, "alice@example.com")]


def test_detect_phone() -> None:
    matches = detect("call +1 (415) 555-0199 tomorrow")
    kinds = [k for k, _, _, _ in matches]
    assert KIND_PHONE in kinds


def test_detect_short_digit_runs_are_not_phones() -> None:
    assert detect("order 1234 shipped") == []


def test_detect_credit_card_luhn_valid() -> None:
    # Visa test card
    matches = detect("card 4242 4242 4242 4242 expires")
    assert any(k == KIND_CREDIT_CARD for k, _, _, _ in matches)


def test_detect_credit_card_rejects_luhn_invalid() -> None:
    kinds = {k for k, _, _, _ in detect("card 4242 4242 4242 4241 expires")}
    assert KIND_CREDIT_CARD not in kinds


def test_detect_ipv4_valid_range() -> None:
    kinds = {k for k, _, _, _ in detect("host at 10.0.0.1 responded")}
    assert KIND_IPV4 in kinds


def test_detect_ipv4_rejects_out_of_range() -> None:
    kinds = {k for k, _, _, _ in detect("bad 10.0.0.999 entry")}
    assert KIND_IPV4 not in kinds


def test_detect_iban() -> None:
    kinds = {k for k, _, _, _ in detect("account GB82WEST12345698765432 ok")}
    assert KIND_IBAN in kinds


def test_detect_overlap_keeps_leftmost_only() -> None:
    # A long digit run could be matched by both the credit-card regex (Luhn-gated)
    # and the phone regex — ensure we don't double-report.
    matches = detect("card 4242424242424242 now")
    assert len({(start, end) for _, start, end, _ in matches}) == len(matches)


def test_detect_enabled_kinds_filters_out_others() -> None:
    matches = detect(
        "alice@example.com and 10.0.0.1",
        enabled_kinds=frozenset({KIND_EMAIL}),
    )
    kinds = {k for k, _, _, _ in matches}
    assert kinds == {KIND_EMAIL}


def test_redact_replaces_every_detected_span() -> None:
    redacted, detections = redact("alice@example.com at 10.0.0.1")
    assert redacted == "[REDACTED_email] at [REDACTED_ipv4]"
    assert {d[0] for d in detections} == {KIND_EMAIL, KIND_IPV4}


def test_redact_with_no_matches_returns_input_unchanged() -> None:
    redacted, detections = redact("nothing to see here")
    assert redacted == "nothing to see here"
    assert detections == []


def test_redact_custom_mask_template_interpolates_kind() -> None:
    redacted, _ = redact("alice@example.com", mask_template="<<{kind}>>")
    assert redacted == "<<email>>"


def test_all_kinds_set_matches_enumeration() -> None:
    expected = {KIND_EMAIL, KIND_PHONE, KIND_CREDIT_CARD, KIND_IPV4, KIND_IBAN}
    assert expected == ALL_KINDS


# --- node ------------------------------------------------------------


async def test_node_in_place_redacts_text_field() -> None:
    node = Node(
        id="g", name="g", type="weftlyflow.guard_pii_redact",
        parameters={"field": "text"},
    )
    item = Item(json={"text": "email alice@example.com", "keep": "intact"})
    out = await GuardPiiRedactNode().execute(_ctx_for(node), [item])
    payload = out[0][0].json
    assert payload["text"] == "email [REDACTED_email]"
    assert payload["keep"] == "intact"
    assert payload["pii_count"] == 1
    assert payload["pii_detections"][0]["kind"] == KIND_EMAIL


async def test_node_writes_to_output_field_when_different() -> None:
    node = Node(
        id="g", name="g", type="weftlyflow.guard_pii_redact",
        parameters={"field": "text", "output_field": "clean"},
    )
    item = Item(json={"text": "alice@example.com"})
    out = await GuardPiiRedactNode().execute(_ctx_for(node), [item])
    payload = out[0][0].json
    assert payload["text"] == "alice@example.com"
    assert payload["clean"] == "[REDACTED_email]"


async def test_node_honours_enabled_kinds_filter() -> None:
    node = Node(
        id="g", name="g", type="weftlyflow.guard_pii_redact",
        parameters={"field": "text", "enabled_kinds": ["ipv4"]},
    )
    item = Item(json={"text": "alice@example.com and 10.0.0.1"})
    out = await GuardPiiRedactNode().execute(_ctx_for(node), [item])
    payload = out[0][0].json
    # Only IPv4 should be masked; email remains.
    assert "alice@example.com" in payload["text"]
    assert "[REDACTED_ipv4]" in payload["text"]


async def test_node_rejects_non_string_field() -> None:
    node = Node(
        id="g", name="g", type="weftlyflow.guard_pii_redact",
        parameters={"field": "text"},
    )
    item = Item(json={"text": 42})
    with pytest.raises(NodeExecutionError, match="must be a string"):
        await GuardPiiRedactNode().execute(_ctx_for(node), [item])


async def test_node_rejects_unknown_detector_kind() -> None:
    node = Node(
        id="g", name="g", type="weftlyflow.guard_pii_redact",
        parameters={"field": "text", "enabled_kinds": ["not-a-kind"]},
    )
    item = Item(json={"text": "hi"})
    with pytest.raises(NodeExecutionError, match="unknown detector"):
        await GuardPiiRedactNode().execute(_ctx_for(node), [item])


async def test_node_custom_mask_template_is_applied() -> None:
    node = Node(
        id="g", name="g", type="weftlyflow.guard_pii_redact",
        parameters={"field": "text", "mask_template": "###"},
    )
    item = Item(json={"text": "write alice@example.com"})
    out = await GuardPiiRedactNode().execute(_ctx_for(node), [item])
    assert out[0][0].json["text"] == "write ###"


async def test_node_default_field_is_text() -> None:
    node = Node(
        id="g", name="g", type="weftlyflow.guard_pii_redact",
        parameters={},
    )
    item = Item(json={"text": "10.0.0.1"})
    out = await GuardPiiRedactNode().execute(_ctx_for(node), [item])
    assert out[0][0].json["text"] == "[REDACTED_ipv4]"


async def test_node_zero_detections_still_emits_metadata() -> None:
    node = Node(
        id="g", name="g", type="weftlyflow.guard_pii_redact",
        parameters={"field": "text"},
    )
    item = Item(json={"text": "nothing here"})
    out = await GuardPiiRedactNode().execute(_ctx_for(node), [item])
    payload = out[0][0].json
    assert payload["pii_count"] == 0
    assert payload["pii_detections"] == []
