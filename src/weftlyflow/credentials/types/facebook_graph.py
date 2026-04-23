"""Facebook Graph credential — Bearer + optional HMAC ``appsecret_proof`` query.

Facebook Graph (https://developers.facebook.com/docs/graph-api/security/)
authenticates with ``Authorization: Bearer <access_token>``. What
makes this credential distinctive is the **optional** ``appsecret_proof``
query parameter — when an ``app_secret`` is configured, every call
appends ``appsecret_proof=hex(hmac_sha256(access_token, app_secret))``
to *prove* the call originated from the app that owns the token.
Apps configured with "Require App Secret" reject calls without the
proof; without the secret, calls work but are vulnerable to leaked
tokens being replayed by other apps.

This is an HMAC-in-query-parameter pattern absent elsewhere in the
catalog. The signer is isolated as :func:`build_appsecret_proof` so
the same shape can be reused by the generic HTTP Request node.

The self-test calls ``GET /me?fields=id`` which works with any valid
user/page/system-user token.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any, ClassVar, Final

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_API_BASE_URL: Final[str] = "https://graph.facebook.com"
_PROOF_PARAM: Final[str] = "appsecret_proof"
_TEST_TIMEOUT_SECONDS: Final[float] = 10.0


def build_appsecret_proof(access_token: str, app_secret: str) -> str:
    """Return ``hex(hmac_sha256(access_token, app_secret))``."""
    if not access_token or not app_secret:
        msg = "Facebook: both access_token and app_secret are required"
        raise ValueError(msg)
    return hmac.new(
        app_secret.encode("utf-8"),
        access_token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


class FacebookGraphCredential(BaseCredentialType):
    """Inject Bearer + optional ``appsecret_proof`` query parameter."""

    slug: ClassVar[str] = "weftlyflow.facebook_graph"
    display_name: ClassVar[str] = "Facebook Graph"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://developers.facebook.com/docs/graph-api/security/"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="access_token",
            display_name="Access Token",
            type="string",
            required=True,
            description="Facebook user, page, or system-user access token.",
            type_options={"password": True},
        ),
        PropertySchema(
            name="app_secret",
            display_name="App Secret",
            type="string",
            required=False,
            description=(
                "Optional app secret — enables HMAC 'appsecret_proof' "
                "query param on every call."
            ),
            type_options={"password": True},
        ),
        PropertySchema(
            name="api_version",
            display_name="API Version",
            type="string",
            required=False,
            default="v21.0",
            description="Graph API version prefix (e.g. v21.0).",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set Bearer auth + optional ``appsecret_proof`` query parameter."""
        token = str(creds.get("access_token", "")).strip()
        request.headers["Authorization"] = f"Bearer {token}"
        app_secret = str(creds.get("app_secret", "")).strip()
        if token and app_secret:
            proof = build_appsecret_proof(token, app_secret)
            updated = request.url.copy_merge_params({_PROOF_PARAM: proof})
            request.url = updated
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /me?fields=id`` and report the outcome."""
        token = str(creds.get("access_token") or "").strip()
        if not token:
            return CredentialTestResult(ok=False, message="access_token is empty")
        version = str(creds.get("api_version") or "v21.0").strip()
        params: dict[str, str] = {"fields": "id"}
        app_secret = str(creds.get("app_secret") or "").strip()
        if app_secret:
            try:
                params[_PROOF_PARAM] = build_appsecret_proof(token, app_secret)
            except ValueError as exc:
                return CredentialTestResult(ok=False, message=str(exc))
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    f"{_API_BASE_URL}/{version}/me",
                    params=params,
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
                message=f"facebook rejected token: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = FacebookGraphCredential
