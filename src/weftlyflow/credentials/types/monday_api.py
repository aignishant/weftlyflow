"""Monday.com API credential — raw ``Authorization`` header (no prefix).

Monday.com's GraphQL API (https://developer.monday.com/api-reference/)
expects the personal API token directly in the ``Authorization`` header
with no ``Bearer`` prefix. The self-test issues a trivial GraphQL query
(``{ me { id name } }``) to ``https://api.monday.com/v2``.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_API_URL: str = "https://api.monday.com/v2"
_TEST_QUERY: str = "{ me { id name } }"
_TEST_TIMEOUT_SECONDS: float = 10.0


class MondayApiCredential(BaseCredentialType):
    """Inject ``Authorization: <api_token>`` (no prefix) on every request."""

    slug: ClassVar[str] = "weftlyflow.monday_api"
    display_name: ClassVar[str] = "Monday.com API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://developer.monday.com/api-reference/docs/authentication"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="api_token",
            display_name="API Token",
            type="string",
            required=True,
            description="Personal API token from Monday.com Developer admin.",
            type_options={"password": True},
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set raw ``Authorization: <api_token>`` on ``request``."""
        token = str(creds.get("api_token", "")).strip()
        request.headers["Authorization"] = token
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """POST a trivial GraphQL ``me`` query and report the outcome."""
        token = str(creds.get("api_token", "")).strip()
        if not token:
            return CredentialTestResult(ok=False, message="api_token is empty")
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    _API_URL,
                    headers={
                        "Authorization": token,
                        "Content-Type": "application/json",
                    },
                    json={"query": _TEST_QUERY},
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"monday rejected token: HTTP {response.status_code}",
            )
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if isinstance(payload, dict) and payload.get("errors"):
            return CredentialTestResult(
                ok=False,
                message=f"monday returned errors: {payload['errors']}",
            )
        name = ""
        if isinstance(payload, dict):
            data = payload.get("data")
            if isinstance(data, dict):
                me = data.get("me")
                if isinstance(me, dict):
                    name = str(me.get("name", ""))
        suffix = f" as {name}" if name else ""
        return CredentialTestResult(ok=True, message=f"authenticated{suffix}")


TYPE = MondayApiCredential
