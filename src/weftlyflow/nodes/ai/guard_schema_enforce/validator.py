"""Tiny JSON-Schema subset validator used by the ``guard_schema_enforce`` node.

Supports the Draft-7 keywords most commonly emitted when coaxing JSON
out of an LLM; anything more exotic (``$ref``, ``allOf``, ``oneOf``,
format-validators, conditional schemas) is deliberately omitted.
If users need full Draft-7/2020-12, they should plug in a dedicated
library downstream - but in practice the subset below catches the
failure modes that matter for LLM output shaping:

* ``type`` - one of ``object``, ``array``, ``string``, ``number``,
  ``integer``, ``boolean``, ``null`` (or a list of these).
* ``required`` - list of property names that must be present.
* ``properties`` - per-key sub-schemas.
* ``additionalProperties`` - ``False`` rejects extra keys; defaults to
  ``True``.
* ``items`` - sub-schema applied to every element.
* ``enum`` - whitelist of allowed scalar values (compared with ``==``).
* ``minLength`` / ``maxLength`` - string length bounds.
* ``minimum`` / ``maximum`` - numeric bounds (inclusive).
* ``pattern`` - regex the string must match (``re.search``).
* ``minItems`` / ``maxItems`` - array length bounds.

The validator is a top-down recursion over ``value`` and ``schema``;
errors are reported as ``(path, message)`` pairs where ``path`` is a
JSON-Pointer-style slash string (``""`` for the root, ``"/foo/0/bar"``
for a nested value).
"""

from __future__ import annotations

import re
from typing import Any, Final

ValidationError = tuple[str, str]

_PRIMITIVE_TYPES: Final[frozenset[str]] = frozenset(
    {"object", "array", "string", "number", "integer", "boolean", "null"},
)


def validate(
    value: Any,
    schema: dict[str, Any],
) -> list[ValidationError]:
    """Return every validation error for ``value`` against ``schema``.

    An empty list means the value is valid. The schema itself is
    trusted to be well-formed - malformed schemas produce malformed
    error messages, which is the caller's problem.

    Args:
        value: The JSON-like object to validate.
        schema: JSON-Schema dict. See the module docstring for the
            supported keyword subset.

    Returns:
        List of ``(path, message)`` tuples, in a deterministic
        left-to-right, depth-first order.
    """
    errors: list[ValidationError] = []
    _validate(value, schema, path="", errors=errors)
    return errors


def _validate(
    value: Any,
    schema: dict[str, Any],
    *,
    path: str,
    errors: list[ValidationError],
) -> None:
    expected_type = schema.get("type")
    if expected_type is not None and not _type_matches(value, expected_type):
        errors.append(
            (path, f"expected type {expected_type!r}, got {_type_name(value)}"),
        )
        return  # further per-type checks are meaningless once the type is wrong

    if "enum" in schema:
        allowed = schema["enum"]
        if value not in allowed:
            errors.append((path, f"value {value!r} is not one of {allowed!r}"))

    if isinstance(value, str):
        _validate_string(value, schema, path=path, errors=errors)
    elif isinstance(value, bool):
        # bool is a subclass of int in Python - no numeric bounds apply.
        pass
    elif isinstance(value, (int, float)):
        _validate_number(value, schema, path=path, errors=errors)
    elif isinstance(value, list):
        _validate_array(value, schema, path=path, errors=errors)
    elif isinstance(value, dict):
        _validate_object(value, schema, path=path, errors=errors)


def _validate_string(
    value: str,
    schema: dict[str, Any],
    *,
    path: str,
    errors: list[ValidationError],
) -> None:
    min_length = schema.get("minLength")
    if isinstance(min_length, int) and len(value) < min_length:
        errors.append((path, f"string length {len(value)} < minLength {min_length}"))
    max_length = schema.get("maxLength")
    if isinstance(max_length, int) and len(value) > max_length:
        errors.append((path, f"string length {len(value)} > maxLength {max_length}"))
    pattern = schema.get("pattern")
    if isinstance(pattern, str) and not re.search(pattern, value):
        errors.append((path, f"string does not match pattern {pattern!r}"))


def _validate_number(
    value: float,
    schema: dict[str, Any],
    *,
    path: str,
    errors: list[ValidationError],
) -> None:
    minimum = schema.get("minimum")
    if isinstance(minimum, (int, float)) and value < minimum:
        errors.append((path, f"value {value} < minimum {minimum}"))
    maximum = schema.get("maximum")
    if isinstance(maximum, (int, float)) and value > maximum:
        errors.append((path, f"value {value} > maximum {maximum}"))


def _validate_array(
    value: list[Any],
    schema: dict[str, Any],
    *,
    path: str,
    errors: list[ValidationError],
) -> None:
    min_items = schema.get("minItems")
    if isinstance(min_items, int) and len(value) < min_items:
        errors.append((path, f"array length {len(value)} < minItems {min_items}"))
    max_items = schema.get("maxItems")
    if isinstance(max_items, int) and len(value) > max_items:
        errors.append((path, f"array length {len(value)} > maxItems {max_items}"))
    items_schema = schema.get("items")
    if isinstance(items_schema, dict):
        for idx, element in enumerate(value):
            _validate(element, items_schema, path=f"{path}/{idx}", errors=errors)


def _validate_object(
    value: dict[str, Any],
    schema: dict[str, Any],
    *,
    path: str,
    errors: list[ValidationError],
) -> None:
    required = schema.get("required")
    if isinstance(required, list):
        for key in required:
            if key not in value:
                errors.append((path, f"missing required property {key!r}"))
    properties = schema.get("properties")
    if isinstance(properties, dict):
        for key, sub_schema in properties.items():
            if key in value and isinstance(sub_schema, dict):
                _validate(
                    value[key],
                    sub_schema,
                    path=f"{path}/{key}",
                    errors=errors,
                )
    additional = schema.get("additionalProperties", True)
    if additional is False and isinstance(properties, dict):
        declared = set(properties.keys())
        for extra_key in value:
            if extra_key not in declared:
                errors.append(
                    (path, f"unexpected property {extra_key!r}"),
                )


def _type_matches(value: Any, expected: Any) -> bool:
    """Return True when ``value`` matches ``expected`` (a name or list of names)."""
    if isinstance(expected, list):
        return any(_type_matches(value, t) for t in expected)
    if expected not in _PRIMITIVE_TYPES:
        return True  # unknown/unsupported type - treat as permissive
    return _type_name(value) == expected or (
        expected == "number" and _type_name(value) == "integer"
    )


_TYPE_CHECKS: Final[tuple[tuple[type, str], ...]] = (
    (bool, "boolean"),  # must precede int — ``True`` is an ``int`` in Python
    (int, "integer"),
    (float, "number"),
    (str, "string"),
    (list, "array"),
    (dict, "object"),
)


def _type_name(value: Any) -> str:
    """Return the JSON-Schema type name for ``value``.

    ``bool`` is checked before ``int`` because in Python ``True`` is
    also an ``int`` - and in JSON Schema that would be wrong.
    """
    if value is None:
        return "null"
    for py_type, name in _TYPE_CHECKS:
        if isinstance(value, py_type):
            return name
    return type(value).__name__
