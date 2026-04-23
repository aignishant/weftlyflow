"""Hasura credential — ``X-Hasura-Admin-Secret`` + optional ``X-Hasura-Role``.

Hasura (https://hasura.io/docs/latest/auth/authentication/admin-secret/)
GraphQL Engine authenticates with a single ``X-Hasura-Admin-Secret``
header carrying the admin secret configured in the engine. The secret
grants unfiltered access; to invoke a non-admin role and have
row/column authz applied, callers also send ``X-Hasura-Role: <role>``
(and any ``X-Hasura-<session-var>`` headers the role expects).

Self-hosted deployments are the common case — the credential therefore
stores a configurable ``base_url`` (e.g. ``https://gql.example.com``)
rather than a fixed host.

The self-test calls a tiny introspection query against ``/v1/graphql``
which returns 200 only when the admin secret is valid.
"""

from __future__ import annotations

from typing import Any, ClassVar, Final

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_ADMIN_SECRET_HEADER: Final[str] = "X-Hasura-Admin-Secret"
_ROLE_HEADER: Final[str] = "X-Hasura-Role"
_TEST_PATH: Final[str] = "/v1/graphql"
_TEST_QUERY: Final[str] = "{ __schema { queryType { name } } }"
_TEST_TIMEOUT_SECONDS: Final[float] = 10.0


class HasuraApiCredential(BaseCredentialType):
    """Inject ``X-Hasura-Admin-Secret`` (+ optional ``X-Hasura-Role``)."""

    slug: ClassVar[str] = "weftlyflow.hasura_api"
    display_name: ClassVar[str] = "Hasura API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://hasura.io/docs/latest/auth/authentication/admin-secret/"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="base_url",
            display_name="Base URL",
            type="string",
            required=True,
            description="GraphQL Engine root, e.g. https://gql.example.com (no trailing slash).",
        ),
        PropertySchema(
            name="admin_secret",
            display_name="Admin Secret",
            type="string",
            required=True,
            description="Value of HASURA_GRAPHQL_ADMIN_SECRET on the server.",
            type_options={"password": True},
        ),
        PropertySchema(
            name="role",
            display_name="Role",
            type="string",
            required=False,
            description="Optional 'X-Hasura-Role' to scope the request away from admin.",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set ``X-Hasura-Admin-Secret`` (+ role header when provided)."""
        secret = str(creds.get("admin_secret", "")).strip()
        request.headers[_ADMIN_SECRET_HEADER] = secret
        role = str(creds.get("role", "")).strip()
        if role:
            request.headers[_ROLE_HEADER] = role
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Run a tiny introspection query against ``/v1/graphql``."""
        base_url = str(creds.get("base_url") or "").strip().rstrip("/")
        secret = str(creds.get("admin_secret") or "").strip()
        if not base_url:
            return CredentialTestResult(ok=False, message="base_url is empty")
        if not secret:
            return CredentialTestResult(ok=False, message="admin_secret is empty")
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    f"{base_url}{_TEST_PATH}",
                    json={"query": _TEST_QUERY},
                    headers={
                        _ADMIN_SECRET_HEADER: secret,
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"hasura rejected admin secret: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = HasuraApiCredential
