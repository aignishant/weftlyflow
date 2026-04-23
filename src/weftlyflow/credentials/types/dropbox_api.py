"""Dropbox API credential — Bearer access token.

Dropbox (https://www.dropbox.com/developers/documentation/http/overview)
uses plain ``Authorization: Bearer <access_token>``. The credential is
ordinary in header shape, but the *node* built on top of it is
distinctive: every RPC and content request carries an additional
``Dropbox-API-Arg`` header whose value is a JSON-encoded arg blob.
That shape is enforced node-side; this credential only manages the
Bearer half.

The self-test calls ``POST /2/users/get_current_account`` with an
empty body.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_TEST_URL: str = "https://api.dropboxapi.com/2/users/get_current_account"
_TEST_TIMEOUT_SECONDS: float = 10.0


class DropboxApiCredential(BaseCredentialType):
    """Inject ``Authorization: Bearer <access_token>`` on every request."""

    slug: ClassVar[str] = "weftlyflow.dropbox_api"
    display_name: ClassVar[str] = "Dropbox API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://www.dropbox.com/developers/documentation/http/overview"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="access_token",
            display_name="Access Token",
            type="string",
            required=True,
            description="Dropbox access token (scoped app or long-lived).",
            type_options={"password": True},
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set ``Authorization: Bearer <access_token>`` on ``request``."""
        token = str(creds.get("access_token", "")).strip()
        request.headers["Authorization"] = f"Bearer {token}"
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """POST to ``/2/users/get_current_account`` and report."""
        token = str(creds.get("access_token") or "").strip()
        if not token:
            return CredentialTestResult(ok=False, message="access_token is empty")
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    _TEST_URL,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"dropbox rejected token: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = DropboxApiCredential
