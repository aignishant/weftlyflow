"""Pure-Python PII detectors used by the ``guard_pii_redact`` node.

Each detector is a regex plus an optional post-filter (credit-card Luhn,
IPv4 octet range). Detectors return matches as ``(kind, start, end, text)``
4-tuples so callers can redact in reverse order without recomputing
offsets when earlier spans were replaced with different-length masks.

The set is intentionally conservative: false positives on plain text are
worse than false negatives in a redaction context, because a negative is
obvious to the user and a positive silently destroys legitimate data.
Common patterns covered:

* ``email`` - RFC-5322-ish "local@domain.tld" with TLD >= 2.
* ``phone`` - E.164-ish with optional ``+``, country code, and 7-14
  digits with allowed separators. Short sequences (<7 digits) are
  excluded to avoid matching order numbers.
* ``credit_card`` - 13-19 digit runs with optional hyphens/spaces,
  gated by the Luhn checksum.
* ``ipv4`` - four octets in 0-255 range (regex + per-octet check).
* ``iban`` - 2 letters + 2 check digits + 11-30 alphanumerics.

All detectors are ``re.Pattern`` objects compiled at import time; running
them is O(n) in input length.
"""

from __future__ import annotations

import re
from typing import Final

KIND_EMAIL: Final[str] = "email"
KIND_PHONE: Final[str] = "phone"
KIND_CREDIT_CARD: Final[str] = "credit_card"
KIND_IPV4: Final[str] = "ipv4"
KIND_IBAN: Final[str] = "iban"

ALL_KINDS: Final[frozenset[str]] = frozenset(
    {KIND_EMAIL, KIND_PHONE, KIND_CREDIT_CARD, KIND_IPV4, KIND_IBAN},
)

_EMAIL_RE: Final[re.Pattern[str]] = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,24}\b",
)

# Require 7+ digits *after* an optional leading '+', so short order-number-like
# runs don't match. Separators: space, dash, dot, parentheses.
_PHONE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?<!\w)\+?(?:\d[\s\-\.()]?){6,14}\d(?!\w)",
)

# 13-19 digits in runs of 4 separated by optional space or dash. Gated by Luhn.
_CREDIT_CARD_RE: Final[re.Pattern[str]] = re.compile(
    r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)",
)

_IPV4_RE: Final[re.Pattern[str]] = re.compile(
    r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)",
)

_IBAN_RE: Final[re.Pattern[str]] = re.compile(
    r"(?<![A-Z0-9])[A-Z]{2}\d{2}[A-Z0-9]{11,30}(?![A-Z0-9])",
)


_LUHN_SINGLE_DIGIT_MAX: Final[int] = 9
_CREDIT_CARD_MIN_LEN: Final[int] = 13
_CREDIT_CARD_MAX_LEN: Final[int] = 19
_IPV4_OCTET_COUNT: Final[int] = 4
_IPV4_OCTET_MAX: Final[int] = 255


def _luhn_valid(number: str) -> bool:
    """Return True when ``number`` (digits only) satisfies the Luhn checksum."""
    total = 0
    alt = False
    for ch in reversed(number):
        digit = ord(ch) - ord("0")
        if alt:
            digit *= 2
            if digit > _LUHN_SINGLE_DIGIT_MAX:
                digit -= _LUHN_SINGLE_DIGIT_MAX
        total += digit
        alt = not alt
    return total % 10 == 0


def _ipv4_valid(match: str) -> bool:
    parts = match.split(".")
    return len(parts) == _IPV4_OCTET_COUNT and all(
        0 <= int(p) <= _IPV4_OCTET_MAX for p in parts
    )


def detect(
    text: str,
    *,
    enabled_kinds: frozenset[str] | None = None,
) -> list[tuple[str, int, int, str]]:
    """Return every PII span in ``text``, filtered by ``enabled_kinds``.

    Args:
        text: Input to scan.
        enabled_kinds: When set, only report matches whose kind is in this
            set. ``None`` means "all kinds" (equivalent to :data:`ALL_KINDS`).

    Returns:
        List of ``(kind, start, end, text)`` 4-tuples, sorted by ``start``.
        Overlapping matches from different detectors are resolved by
        keeping the leftmost span and dropping later spans that start
        inside it — prevents double-reporting a credit-card sequence as
        also matching the phone regex.
    """
    allowed = enabled_kinds if enabled_kinds is not None else ALL_KINDS
    spans: list[tuple[str, int, int, str]] = []

    if KIND_EMAIL in allowed:
        spans.extend(
            (KIND_EMAIL, m.start(), m.end(), m.group(0))
            for m in _EMAIL_RE.finditer(text)
        )
    if KIND_IPV4 in allowed:
        spans.extend(
            (KIND_IPV4, m.start(), m.end(), m.group(0))
            for m in _IPV4_RE.finditer(text)
            if _ipv4_valid(m.group(0))
        )
    if KIND_IBAN in allowed:
        spans.extend(
            (KIND_IBAN, m.start(), m.end(), m.group(0))
            for m in _IBAN_RE.finditer(text)
        )
    if KIND_CREDIT_CARD in allowed:
        for m in _CREDIT_CARD_RE.finditer(text):
            digits = re.sub(r"[^0-9]", "", m.group(0))
            if (
                _CREDIT_CARD_MIN_LEN <= len(digits) <= _CREDIT_CARD_MAX_LEN
                and _luhn_valid(digits)
            ):
                spans.append((KIND_CREDIT_CARD, m.start(), m.end(), m.group(0)))
    if KIND_PHONE in allowed:
        spans.extend(
            (KIND_PHONE, m.start(), m.end(), m.group(0))
            for m in _PHONE_RE.finditer(text)
        )

    spans.sort(key=lambda span: span[1])
    return _drop_overlaps(spans)


def _drop_overlaps(
    spans: list[tuple[str, int, int, str]],
) -> list[tuple[str, int, int, str]]:
    """Keep the first span; drop later spans that overlap an already-kept one."""
    out: list[tuple[str, int, int, str]] = []
    cursor = -1
    for span in spans:
        _, start, end, _ = span
        if start < cursor:
            continue
        out.append(span)
        cursor = end
    return out


def redact(
    text: str,
    *,
    enabled_kinds: frozenset[str] | None = None,
    mask_template: str = "[REDACTED_{kind}]",
) -> tuple[str, list[tuple[str, int, int, str]]]:
    """Return ``(redacted, detections)`` for ``text``.

    The ``mask_template`` string is formatted with ``kind=<detector>``.
    For example the default maps an email match to ``"[REDACTED_email]"``.
    Detections are returned as-found on the **original** input — the
    caller gets byte offsets into ``text``, not into the redacted output.
    """
    detections = detect(text, enabled_kinds=enabled_kinds)
    if not detections:
        return text, detections

    parts: list[str] = []
    cursor = 0
    for kind, start, end, _ in detections:
        parts.append(text[cursor:start])
        parts.append(mask_template.format(kind=kind))
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts), detections
