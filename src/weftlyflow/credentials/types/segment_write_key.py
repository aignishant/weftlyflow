"""Segment write-key credential — HTTP Basic with empty password.

Segment's Track/Identify/Group/Page/Alias HTTP API
(https://segment.com/docs/connections/sources/catalog/libraries/server/http-api/)
authenticates by placing the **source write key** in the HTTP Basic
*username* slot with an **empty password**. This is an unusual
Basic-auth convention — nothing in the tranche-1-through-20 catalog
uses it — and preserving the exact ``Authorization: Basic <b64(KEY:)>``
wire shape matters because Segment rejects requests whose basic-auth
payload omits the trailing colon.

The self-test issues a no-op identify call to ``/v1/identify``; Segment
returns ``200 {"success": true}`` for authenticated empty payloads and
``401`` for bad keys.
"""

from __future__ import annotations

import base64
from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_TEST_URL: str = "https://api.segment.io/v1/identify"
_TEST_TIMEOUT_SECONDS: float = 10.0


class SegmentWriteKeyCredential(BaseCredentialType):
    """Inject ``Authorization: Basic base64(write_key:)`` per request."""

    slug: ClassVar[str] = "weftlyflow.segment_write_key"
    display_name: ClassVar[str] = "Segment Write Key"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://segment.com/docs/connections/sources/catalog/libraries/server/http-api/"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="write_key",
            display_name="Write Key",
            type="string",
            required=True,
            type_options={"password": True},
            description="Source-level write key from the Segment dashboard.",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set ``Authorization: Basic b64(write_key:)`` on ``request``."""
        write_key = str(creds.get("write_key", ""))
        encoded = base64.b64encode(f"{write_key}:".encode()).decode("ascii")
        request.headers["Authorization"] = f"Basic {encoded}"
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Send a minimal identify payload to validate the write key."""
        write_key = str(creds.get("write_key", "")).strip()
        if not write_key:
            return CredentialTestResult(ok=False, message="write_key is required")
        encoded = base64.b64encode(f"{write_key}:".encode()).decode("ascii")
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    _TEST_URL,
                    headers={
                        "Authorization": f"Basic {encoded}",
                        "Content-Type": "application/json",
                    },
                    json={"userId": "weftlyflow-test"},
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"segment rejected write_key: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="write_key valid")


TYPE = SegmentWriteKeyCredential
