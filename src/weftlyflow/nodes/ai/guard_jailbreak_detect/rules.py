"""Heuristic rules used by the ``guard_jailbreak_detect`` node.

A small, explicit ruleset is deliberate. Prompt-injection detection
is adversarial and any single rule can be defeated; the point of this
layer is to catch the *boring* attacks (copy-pasted jailbreak prompts,
accidental role-switching by users) cheaply, so the LLM's own safety
training only has to handle novel cases. For sophisticated attackers
pair this with a model-based classifier downstream.

Rules provided:

* ``instruction_override`` - "ignore previous instructions", "disregard
  the above", "forget everything" and close variants.
* ``role_switch`` - "you are now", "act as", "pretend (to be|you are)",
  "new persona".
* ``system_role_injection`` - inline fake system/assistant turns like
  ``"System:"`` or ``"<s>[INST]"``.
* ``dan_mode`` - the classic DAN / developer-mode jailbreak family.
* ``tool_injection`` - smuggled tool-call markers such as
  ``"<tool_call>"``, ``"<function_call>"``, ``"```tool_code"``.

Each rule is case-insensitive and matches only substrings that are
likely to appear in an actual attempt (e.g. ``"ignore previous"``
requires the word ``previous`` or ``above`` after ``ignore`` rather
than matching any sentence starting with ``ignore``).
"""

from __future__ import annotations

import re
from typing import Final

RULE_INSTRUCTION_OVERRIDE: Final[str] = "instruction_override"
RULE_ROLE_SWITCH: Final[str] = "role_switch"
RULE_SYSTEM_ROLE_INJECTION: Final[str] = "system_role_injection"
RULE_DAN_MODE: Final[str] = "dan_mode"
RULE_TOOL_INJECTION: Final[str] = "tool_injection"

ALL_RULES: Final[frozenset[str]] = frozenset(
    {
        RULE_INSTRUCTION_OVERRIDE,
        RULE_ROLE_SWITCH,
        RULE_SYSTEM_ROLE_INJECTION,
        RULE_DAN_MODE,
        RULE_TOOL_INJECTION,
    },
)

_FLAGS: Final[int] = re.IGNORECASE | re.DOTALL

_INSTRUCTION_OVERRIDE_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(ignore|disregard|forget)\b[^.?!\n]{0,40}\b"
    r"(previous|prior|above|earlier|everything|all)\b[^.?!\n]{0,40}\b"
    r"(instructions?|prompts?|rules?|directives?|context)\b",
    _FLAGS,
)

_ROLE_SWITCH_RE: Final[re.Pattern[str]] = re.compile(
    r"\b("
    r"you\s+are\s+now"
    r"|act\s+as(?:\s+a|\s+an)?"
    r"|pretend\s+(?:to\s+be|you\s+are)"
    r"|role[\s-]?play\s+as"
    r"|(?:new|switch|assume)\s+(?:persona|role|identity)"
    r")\b",
    _FLAGS,
)

_SYSTEM_ROLE_INJECTION_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:"
    r"<s>\s*\[INST\]"
    r"|<\|im_start\|>\s*(?:system|assistant|user)"
    r"|(?:^|[\n.!?])\s*(?:system|assistant|developer)\s*:"
    r"|###\s*(?:system|instruction|assistant)\s*:?"
    r")",
    _FLAGS | re.MULTILINE,
)

_DAN_MODE_RE: Final[re.Pattern[str]] = re.compile(
    r"\b("
    r"DAN\s+mode"
    r"|do\s+anything\s+now"
    r"|developer\s+mode\s+(?:enabled|on|activated)"
    r"|jailbreak\s+mode"
    r"|unrestricted\s+mode"
    r"|AIM\s+mode"
    r")\b",
    _FLAGS,
)

_TOOL_INJECTION_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:"
    r"<\s*(?:tool_call|function_call|tool_code|tool_use|invoke)\s*>"
    r"|```(?:tool_code|tool_call|function_call)"
    r"|\{\s*\"(?:tool|function|name)\"\s*:\s*\"[^\"]+\"\s*,\s*\"(?:arguments|parameters)\""
    r")",
    _FLAGS,
)

_RULE_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    (RULE_INSTRUCTION_OVERRIDE, _INSTRUCTION_OVERRIDE_RE),
    (RULE_ROLE_SWITCH, _ROLE_SWITCH_RE),
    (RULE_SYSTEM_ROLE_INJECTION, _SYSTEM_ROLE_INJECTION_RE),
    (RULE_DAN_MODE, _DAN_MODE_RE),
    (RULE_TOOL_INJECTION, _TOOL_INJECTION_RE),
)


def detect(
    text: str,
    *,
    enabled_rules: frozenset[str] | None = None,
) -> list[tuple[str, str]]:
    """Return ``(rule, match_text)`` for every rule that fires on ``text``.

    Args:
        text: Input to scan. Empty input returns an empty list.
        enabled_rules: When set, only rules in this set are evaluated.
            ``None`` means :data:`ALL_RULES`.

    Returns:
        List of ``(rule, match)`` tuples in the order rules are checked.
        At most one match per rule is returned - the detector flags
        presence, not occurrence count. Callers needing every match
        should run the underlying regex directly.
    """
    if not text:
        return []
    allowed = enabled_rules if enabled_rules is not None else ALL_RULES
    hits: list[tuple[str, str]] = []
    for name, pattern in _RULE_PATTERNS:
        if name not in allowed:
            continue
        match = pattern.search(text)
        if match is not None:
            hits.append((name, match.group(0)))
    return hits
