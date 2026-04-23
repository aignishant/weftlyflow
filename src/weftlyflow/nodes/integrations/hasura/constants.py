"""Constants for the Hasura integration node.

Reference: https://hasura.io/docs/latest/api-reference/graphql-api/overview/.
"""

from __future__ import annotations

from typing import Final

DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0
GRAPHQL_PATH: Final[str] = "/v1/graphql"

OP_RUN_QUERY: Final[str] = "run_query"
OP_RUN_MUTATION: Final[str] = "run_mutation"
OP_INTROSPECT: Final[str] = "introspect"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_RUN_QUERY,
    OP_RUN_MUTATION,
    OP_INTROSPECT,
)

INTROSPECTION_QUERY: Final[str] = (
    "query IntrospectionQuery { __schema { "
    "queryType { name } "
    "mutationType { name } "
    "subscriptionType { name } "
    "types { kind name description } "
    "} }"
)
