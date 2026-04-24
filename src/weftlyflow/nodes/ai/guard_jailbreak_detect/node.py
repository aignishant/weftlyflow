"""Guard Jailbreak Detect node - score incoming text for injection risk.

Non-blocking detector: the node enriches each item with
``jailbreak_risk``, ``jailbreak_rules``, and ``jailbreak_flagged``
fields and leaves routing to the workflow author. Typical pattern:

    webhook -> guard_jailbreak_detect -> if ({{ $json.jailbreak_flagged }})
                                          -> stop_and_error
                                          -> llm_chat

Placing this node *before* credentials/tool-calling guarantees that
flagged inputs never reach downstream LLM nodes. Pair with
``guard_pii_redact`` for defense-in-depth on public chat-trigger
endpoints.

The detector is heuristic - it catches copy-pasted jailbreak prompts
cheaply but is not a substitute for model-side safety. For high-stakes
workflows, send flagged items to a model-based classifier downstream
rather than acting on the verdict alone.
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
from weftlyflow.nodes.ai.guard_jailbreak_detect.rules import (
    ALL_RULES,
    RULE_DAN_MODE,
    RULE_INSTRUCTION_OVERRIDE,
    RULE_ROLE_SWITCH,
    RULE_SYSTEM_ROLE_INJECTION,
    RULE_TOOL_INJECTION,
    detect,
)
from weftlyflow.nodes.base import BaseNode

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_DEFAULT_FIELD: str = "text"
_DEFAULT_THRESHOLD: int = 1


class GuardJailbreakDetectNode(BaseNode):
    """Score a text field against prompt-injection / jailbreak heuristics."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.guard_jailbreak_detect",
        version=1,
        display_name="Guard: Jailbreak Detect",
        description=(
            "Flag prompt-injection and jailbreak attempts in a text field. "
            "Emits jailbreak_risk, jailbreak_rules, and jailbreak_flagged."
        ),
        icon="icons/guard-jailbreak.svg",
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
                name="threshold",
                display_name="Risk Threshold",
                type="number",
                default=_DEFAULT_THRESHOLD,
                description=(
                    "Number of matched rules at or above which the input "
                    "is flagged as risky."
                ),
            ),
            PropertySchema(
                name="enabled_rules",
                display_name="Enabled Rules",
                type="multi_options",
                default=sorted(ALL_RULES),
                options=[
                    PropertyOption(
                        value=RULE_INSTRUCTION_OVERRIDE,
                        label="Instruction override",
                    ),
                    PropertyOption(value=RULE_ROLE_SWITCH, label="Role switch"),
                    PropertyOption(
                        value=RULE_SYSTEM_ROLE_INJECTION,
                        label="System/assistant role injection",
                    ),
                    PropertyOption(value=RULE_DAN_MODE, label="DAN / developer mode"),
                    PropertyOption(value=RULE_TOOL_INJECTION, label="Tool-call injection"),
                ],
                description="Subset of heuristic rules to evaluate.",
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Score each input item and append the verdict metadata."""
        return [[_run_one(ctx, item) for item in items]]


def _run_one(ctx: ExecutionContext, item: Item) -> Item:
    params = ctx.resolved_params(item=item)
    field = str(params.get("field") or _DEFAULT_FIELD).strip() or _DEFAULT_FIELD
    threshold = _coerce_threshold(params.get("threshold"), node_id=ctx.node.id)
    enabled = _coerce_enabled_rules(params.get("enabled_rules"), node_id=ctx.node.id)

    source = item.json if isinstance(item.json, dict) else {}
    text = source.get(field)
    if text is None:
        text = ""
    elif not isinstance(text, str):
        msg = (
            f"Guard Jailbreak Detect: field {field!r} must be a string, "
            f"got {type(text).__name__}"
        )
        raise NodeExecutionError(msg, node_id=ctx.node.id)

    hits = detect(text, enabled_rules=enabled)
    risk = len(hits)
    new_json: dict[str, Any] = dict(source)
    new_json["jailbreak_risk"] = risk
    new_json["jailbreak_rules"] = [
        {"rule": rule, "match": match} for rule, match in hits
    ]
    new_json["jailbreak_flagged"] = risk >= threshold
    return Item(
        json=new_json,
        binary=item.binary,
        paired_item=item.paired_item,
        error=item.error,
    )


def _coerce_threshold(raw: Any, *, node_id: str) -> int:
    if raw is None or raw == "":
        return _DEFAULT_THRESHOLD
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Guard Jailbreak Detect: 'threshold' must be a non-negative integer"
        raise NodeExecutionError(msg, node_id=node_id, original=exc) from exc
    if value < 0:
        msg = "Guard Jailbreak Detect: 'threshold' must be >= 0"
        raise NodeExecutionError(msg, node_id=node_id)
    return value


def _coerce_enabled_rules(raw: Any, *, node_id: str) -> frozenset[str]:
    if raw is None or raw == "":
        return ALL_RULES
    if isinstance(raw, str):
        candidates = [part.strip() for part in raw.split(",") if part.strip()]
    elif isinstance(raw, list):
        candidates = [str(entry).strip() for entry in raw if str(entry).strip()]
    else:
        msg = (
            "Guard Jailbreak Detect: 'enabled_rules' must be a list or "
            "comma-separated string"
        )
        raise NodeExecutionError(msg, node_id=node_id)
    unknown = [c for c in candidates if c not in ALL_RULES]
    if unknown:
        msg = f"Guard Jailbreak Detect: unknown rule(s) {unknown!r}"
        raise NodeExecutionError(msg, node_id=node_id)
    return frozenset(candidates) if candidates else ALL_RULES
