"""Pinecone credential — ``Api-Key`` header + split control/data-plane hosts.

Pinecone (https://docs.pinecone.io/guides/get-started/authentication)
is the first catalog provider whose control plane and data plane live
on *different* hosts **and the data-plane host varies per index**:

* Control plane — ``https://api.pinecone.io`` (create/list/describe
  indexes, collections, projects).
* Data plane — a unique per-index host like
  ``https://my-index-proj.svc.us-east-1-aws.pinecone.io`` returned by
  ``GET /indexes/{name}`` as ``host``. The Pinecone node passes that
  value per-call.

Auth is a flat ``Api-Key: <key>`` header on both planes.

The self-test calls control-plane ``GET /indexes`` which returns 200
when the key is valid for the project.
"""

from __future__ import annotations

from typing import Any, ClassVar, Final

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_API_KEY_HEADER: Final[str] = "Api-Key"
_CONTROL_PLANE_HOST: Final[str] = "https://api.pinecone.io"
_TEST_PATH: Final[str] = "/indexes"
_TEST_TIMEOUT_SECONDS: Final[float] = 10.0


class PineconeApiCredential(BaseCredentialType):
    """Inject ``Api-Key: <key>`` on every outgoing request."""

    slug: ClassVar[str] = "weftlyflow.pinecone_api"
    display_name: ClassVar[str] = "Pinecone API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://docs.pinecone.io/guides/get-started/authentication"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="api_key",
            display_name="API Key",
            type="string",
            required=True,
            description="Project-scoped Pinecone API key.",
            type_options={"password": True},
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set ``Api-Key: <key>`` on the outgoing request."""
        api_key = str(creds.get("api_key", "")).strip()
        request.headers[_API_KEY_HEADER] = api_key
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call control-plane ``GET /indexes`` and report the outcome."""
        api_key = str(creds.get("api_key") or "").strip()
        if not api_key:
            return CredentialTestResult(ok=False, message="api_key is empty")
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    f"{_CONTROL_PLANE_HOST}{_TEST_PATH}",
                    headers={
                        _API_KEY_HEADER: api_key,
                        "Accept": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"pinecone rejected key: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = PineconeApiCredential
