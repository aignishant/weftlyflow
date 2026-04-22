"""Linear API credential — raw ``Authorization: <api_key>`` (no prefix).

Linear's GraphQL API (https://developers.linear.app/docs/graphql/working-with-the-graphql-api/)
accepts personal API keys directly in the ``Authorization`` header with
no scheme prefix — distinct from Bearer tokens. The self-test issues a
trivial ``{ viewer { id name } }`` GraphQL query against
``https://api.linear.app/graphql``.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_API_URL: str = "https://api.linear.app/graphql"
_TEST_QUERY: str = "{ viewer { id name } }"
_TEST_TIMEOUT_SECONDS: float = 10.0


class LinearApiCredential(BaseCredentialType):
    """Inject ``Authorization: <api_key>`` (no prefix) on every request."""

    slug: ClassVar[str] = "weftlyflow.linear_api"
    display_name: ClassVar[str] = "Linear API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://developers.linear.app/docs/graphql/working-with-the-graphql-api/"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="api_key",
            display_name="API Key",
            type="string",
            required=True,
            description="Personal API key from Linear workspace settings.",
            type_options={"password": True},
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set raw ``Authorization: <api_key>`` on ``request``."""
        key = str(creds.get("api_key", "")).strip()
        request.headers["Authorization"] = key
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """POST a trivial ``viewer`` GraphQL query and report the outcome."""
        key = str(creds.get("api_key", "")).strip()
        if not key:
            return CredentialTestResult(ok=False, message="api_key is empty")
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    _API_URL,
                    headers={
                        "Authorization": key,
                        "Content-Type": "application/json",
                    },
                    json={"query": _TEST_QUERY},
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"linear rejected key: HTTP {response.status_code}",
            )
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if isinstance(payload, dict) and payload.get("errors"):
            return CredentialTestResult(
                ok=False,
                message=f"linear returned errors: {payload['errors']}",
            )
        name = ""
        if isinstance(payload, dict):
            data = payload.get("data")
            if isinstance(data, dict):
                viewer = data.get("viewer")
                if isinstance(viewer, dict):
                    name = str(viewer.get("name", ""))
        suffix = f" as {name}" if name else ""
        return CredentialTestResult(ok=True, message=f"authenticated{suffix}")


TYPE = LinearApiCredential
