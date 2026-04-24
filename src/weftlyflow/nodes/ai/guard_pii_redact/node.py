"""Guard PII Redact node — mask sensitive patterns in a text field.

A thin wrapper around :mod:`weftlyflow.nodes.ai.guard_pii_redact.patterns`.
Positioned upstream of LLM / memory / logging nodes so prompts and chat
history never store raw credentials, card numbers, or contact details.

Typical placements:

* Before a ``memory_buffer.append`` to strip PII from chat turns before
  they're persisted — the stored history becomes sharable across
  workflows without leaking subject data.
* Between a webhook trigger and an LLM request, so the model never sees
  customer PII in the prompt context.
* Immediately before structured logging of free-form text, so ingest
  pipelines in the observability layer don't need their own redaction.

The node operates on a single text field per item; structured fields
are left untouched. A workflow that needs deep-tree redaction can
compose this node with ``weftlyflow.transform`` to project the targeted
path into ``text``, redact, and fold it back.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.node_spec import (
    NodeCategory,
    NodeSpec,
    PropertyOption,
    PropertySchema,
)
from weftlyflow.nodes.ai.guard_pii_redact.patterns import (
    ALL_KINDS,
    KIND_CREDIT_CARD,
    KIND_EMAIL,
    KIND_IBAN,
    KIND_IPV4,
    KIND_PHONE,
    redact,
)
from weftlyflow.nodes.base import BaseNode

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_DEFAULT_FIELD: str = "text"
_DEFAULT_MASK: str = "[REDACTED_{kind}]"


class GuardPiiRedactNode(BaseNode):
    """Redact PII from a string field on each incoming item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.guard_pii_redact",
        version=1,
        display_name="Guard: PII Redact",
        description=(
            "Mask emails, phones, credit cards, IPs, and IBANs in a text "
            "field. Safe to place upstream of LLM, memory, and logging nodes."
        ),
        icon="icons/guard-pii.svg",
        category=NodeCategory.AI,
        group=["ai", "guardrails"],
        properties=[
            PropertySchema(
                name="field",
                display_name="Text Field",
                type="string",
                default=_DEFAULT_FIELD,
                required=True,
                description="JSON key on the input item that holds the text.",
            ),
            PropertySchema(
                name="output_field",
                display_name="Output Field",
                type="string",
                description=(
                    "Where to write the redacted text. Defaults to the "
                    "same key as 'field' (in-place)."
                ),
            ),
            PropertySchema(
                name="mask_template",
                display_name="Mask Template",
                type="string",
                default=_DEFAULT_MASK,
                description=(
                    "Replacement string. '{kind}' is substituted with the "
                    "detector name (email, phone, credit_card, ipv4, iban)."
                ),
            ),
            PropertySchema(
                name="enabled_kinds",
                display_name="Enabled Detectors",
                type="multi_options",
                default=sorted(ALL_KINDS),
                options=[
                    PropertyOption(value=KIND_EMAIL, label="Email"),
                    PropertyOption(value=KIND_PHONE, label="Phone"),
                    PropertyOption(value=KIND_CREDIT_CARD, label="Credit card"),
                    PropertyOption(value=KIND_IPV4, label="IPv4"),
                    PropertyOption(value=KIND_IBAN, label="IBAN"),
                ],
                description="Subset of detectors to apply.",
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Redact one text field per item and append detection metadata."""
        return [[_run_one(ctx, item) for item in items]]


def _run_one(ctx: ExecutionContext, item: Item) -> Item:
    params = ctx.resolved_params(item=item)
    field = str(params.get("field") or _DEFAULT_FIELD).strip() or _DEFAULT_FIELD
    output_field = str(params.get("output_field") or "").strip() or field
    mask = str(params.get("mask_template") or _DEFAULT_MASK)
    enabled = _coerce_enabled_kinds(params.get("enabled_kinds"), node_id=ctx.node.id)

    source = item.json if isinstance(item.json, dict) else {}
    text = source.get(field)
    if not isinstance(text, str):
        msg = f"Guard PII Redact: field {field!r} must be a string, got {type(text).__name__}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)

    redacted, detections = redact(text, enabled_kinds=enabled, mask_template=mask)
    new_json: dict[str, Any] = dict(source)
    new_json[output_field] = redacted
    new_json["pii_detections"] = [
        {"kind": kind, "start": start, "end": end} for kind, start, end, _ in detections
    ]
    new_json["pii_count"] = len(detections)
    return Item(
        json=new_json,
        binary=item.binary,
        paired_item=item.paired_item,
        error=item.error,
    )


def _coerce_enabled_kinds(raw: Any, *, node_id: str) -> frozenset[str]:
    if raw is None or raw == "":
        return ALL_KINDS
    if isinstance(raw, str):
        candidates = [part.strip() for part in raw.split(",") if part.strip()]
    elif isinstance(raw, list):
        candidates = [str(item).strip() for item in raw if str(item).strip()]
    else:
        msg = "Guard PII Redact: 'enabled_kinds' must be a list or comma-separated string"
        raise NodeExecutionError(msg, node_id=node_id)
    unknown = [k for k in candidates if k not in ALL_KINDS]
    if unknown:
        msg = f"Guard PII Redact: unknown detector kind(s) {unknown!r}"
        raise NodeExecutionError(msg, node_id=node_id)
    return frozenset(candidates) if candidates else ALL_KINDS
