"""Per-operation GraphQL body builders for the Hasura node.

All three supported operations POST to the same ``/v1/graphql`` endpoint
with a distinct JSON envelope:

* ``run_query`` / ``run_mutation`` — carry the user-supplied GraphQL
  document plus optional ``variables`` and ``operationName``. The two
  are wire-identical; they are split so node-editor validation can
  display the operation's intent.
* ``introspect`` — shorthand for the standard schema introspection
  query. No user input required.

Distinctive Hasura shape: the payload is always
``{"query": "...", "variables": {...}|null, "operationName": str|null}``
and the HTTP status is 200 even for GraphQL-level errors — those land
in ``response["errors"]`` and must be surfaced at the node layer.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from weftlyflow.nodes.integrations.hasura.constants import (
    INTROSPECTION_QUERY,
    OP_INTROSPECT,
    OP_RUN_MUTATION,
    OP_RUN_QUERY,
)

RequestSpec = tuple[dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> dict[str, Any]:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Hasura: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_run_query(params: dict[str, Any]) -> dict[str, Any]:
    return _build_document_body(params)


def _build_run_mutation(params: dict[str, Any]) -> dict[str, Any]:
    return _build_document_body(params)


def _build_document_body(params: dict[str, Any]) -> dict[str, Any]:
    query = str(params.get("query") or "").strip()
    if not query:
        msg = "Hasura: 'query' is required"
        raise ValueError(msg)
    body: dict[str, Any] = {"query": query}
    variables = params.get("variables")
    if variables not in (None, ""):
        if not isinstance(variables, dict):
            msg = "Hasura: 'variables' must be a JSON object"
            raise ValueError(msg)
        body["variables"] = variables
    operation_name = str(params.get("operation_name") or "").strip()
    if operation_name:
        body["operationName"] = operation_name
    return body


def _build_introspect(_: dict[str, Any]) -> dict[str, Any]:
    return {"query": INTROSPECTION_QUERY, "operationName": "IntrospectionQuery"}


_Builder = Callable[[dict[str, Any]], dict[str, Any]]
_BUILDERS: dict[str, _Builder] = {
    OP_RUN_QUERY: _build_run_query,
    OP_RUN_MUTATION: _build_run_mutation,
    OP_INTROSPECT: _build_introspect,
}
