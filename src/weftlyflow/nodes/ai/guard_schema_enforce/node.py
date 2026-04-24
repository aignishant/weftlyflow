"""Guard Schema Enforce node - validate item JSON against a schema.

Complements the other two Phase-7 guardrails (``guard_pii_redact``,
``guard_jailbreak_detect``) by policing *structured* output: an LLM
coaxed into returning JSON can still return *almost*-JSON that breaks
downstream code. Placing this node immediately after an LLM call (or
an HTTP response parser) catches those failures at workflow edge
rather than three nodes deeper in a branch.

Two operating modes:

* ``strict=false`` (default) - every item is annotated with
  ``schema_valid`` and ``schema_errors``; the workflow decides what to
  do. Compose with an IF node to route failures to a remediation path.
* ``strict=true`` - invalid items raise :class:`NodeExecutionError`,
  which aborts the run unless the node is marked ``continue_on_fail``
  (standard executor contract). Use this when downstream nodes would
  corrupt data given malformed input and an abort is the safe default.

The ``field`` parameter selects what gets validated. The empty string
(default) validates the whole ``item.json``; a non-empty key validates
that sub-field.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.node_spec import (
    NodeCategory,
    NodeSpec,
    PropertySchema,
)
from weftlyflow.nodes.ai.guard_schema_enforce.validator import validate
from weftlyflow.nodes.base import BaseNode

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_WHOLE_ITEM: str = ""


class GuardSchemaEnforceNode(BaseNode):
    """Validate a JSON value on each input item against a JSON-Schema subset."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.guard_schema_enforce",
        version=1,
        display_name="Guard: Schema Enforce",
        description=(
            "Validate structured data against a JSON-Schema subset. Emits "
            "schema_valid and schema_errors; optionally aborts on invalid."
        ),
        icon="icons/guard-schema.svg",
        category=NodeCategory.AI,
        group=["ai", "guardrails"],
        properties=[
            PropertySchema(
                name="field",
                display_name="Field",
                type="string",
                default=_WHOLE_ITEM,
                description=(
                    "JSON key to validate. Leave empty to validate the "
                    "entire item payload."
                ),
            ),
            PropertySchema(
                name="schema",
                display_name="JSON Schema",
                type="json",
                required=True,
                description=(
                    "Schema subset: type, required, properties, "
                    "additionalProperties, items, enum, minLength, "
                    "maxLength, minimum, maximum, pattern, minItems, "
                    "maxItems."
                ),
            ),
            PropertySchema(
                name="strict",
                display_name="Strict",
                type="boolean",
                default=False,
                description=(
                    "When true, raise on invalid. When false, annotate "
                    "the item and pass through."
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Validate one field per item, annotating or raising per ``strict``."""
        return [[_run_one(ctx, item) for item in items]]


def _run_one(ctx: ExecutionContext, item: Item) -> Item:
    params = ctx.resolved_params(item=item)
    field = str(params.get("field") or _WHOLE_ITEM)
    schema = params.get("schema")
    if not isinstance(schema, dict):
        msg = "Guard Schema Enforce: 'schema' must be a JSON object"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    strict = _coerce_bool(params.get("strict"))

    source = item.json if isinstance(item.json, dict) else {}
    target: Any = source if field == _WHOLE_ITEM else source.get(field)

    errors = validate(target, schema)
    formatted = [{"path": path or "/", "message": message} for path, message in errors]
    valid = not errors

    if strict and not valid:
        msg = f"Guard Schema Enforce: validation failed with {len(errors)} error(s)"
        raise NodeExecutionError(msg, node_id=ctx.node.id)

    new_json: dict[str, Any] = dict(source)
    new_json["schema_valid"] = valid
    new_json["schema_errors"] = formatted
    return Item(
        json=new_json,
        binary=item.binary,
        paired_item=item.paired_item,
        error=item.error,
    )


def _coerce_bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in {"true", "1", "yes", "on"}
    return bool(raw)
