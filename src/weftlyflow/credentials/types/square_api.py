"""Square credential — Bearer token paired with a *mandatory* API version header.

Square (https://developer.squareup.com/docs/build-basics/access-tokens)
authenticates with ``Authorization: Bearer <access_token>`` — but the
distinctive shape is the **mandatory** ``Square-Version: YYYY-MM-DD``
header. Square explicitly version-pins every request: omitting the
header silently routes calls to whatever default version Square is
serving today, and behaviour can change. The header is required to
guarantee deterministic responses, so this credential refuses to
inject without a non-empty version.

The credential also carries an ``environment`` switch
(``sandbox`` / ``production``) since Square exposes both at
``connect.squareupsandbox.com`` and ``connect.squareup.com`` with
distinct token universes.

The self-test calls ``GET /v2/locations`` which returns 200 + the
caller's locations on valid keys.
"""

from __future__ import annotations

from typing import Any, ClassVar, Final

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_PRODUCTION_HOST: Final[str] = "connect.squareup.com"
_SANDBOX_HOST: Final[str] = "connect.squareupsandbox.com"
_ENV_SANDBOX: Final[str] = "sandbox"
_ENV_PRODUCTION: Final[str] = "production"
_VALID_ENVIRONMENTS: Final[frozenset[str]] = frozenset(
    {_ENV_SANDBOX, _ENV_PRODUCTION},
)
_VERSION_HEADER: Final[str] = "Square-Version"
_DEFAULT_VERSION: Final[str] = "2024-12-18"
_TEST_TIMEOUT_SECONDS: Final[float] = 10.0


def host_from(environment: str) -> str:
    """Return the Square host for ``environment``."""
    cleaned = environment.strip().lower()
    if cleaned not in _VALID_ENVIRONMENTS:
        msg = (
            f"Square: 'environment' must be one of "
            f"{sorted(_VALID_ENVIRONMENTS)!r}"
        )
        raise ValueError(msg)
    return _SANDBOX_HOST if cleaned == _ENV_SANDBOX else _PRODUCTION_HOST


class SquareApiCredential(BaseCredentialType):
    """Inject Bearer + mandatory ``Square-Version`` header."""

    slug: ClassVar[str] = "weftlyflow.square_api"
    display_name: ClassVar[str] = "Square API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://developer.squareup.com/docs/build-basics/access-tokens"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="access_token",
            display_name="Access Token",
            type="string",
            required=True,
            description="Square OAuth access token or personal access token.",
            type_options={"password": True},
        ),
        PropertySchema(
            name="api_version",
            display_name="API Version",
            type="string",
            required=True,
            default=_DEFAULT_VERSION,
            description="Mandatory 'Square-Version' header (YYYY-MM-DD).",
        ),
        PropertySchema(
            name="environment",
            display_name="Environment",
            type="string",
            required=True,
            default=_ENV_PRODUCTION,
            description="'sandbox' or 'production'.",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set Bearer auth + mandatory Square-Version header."""
        token = str(creds.get("access_token", "")).strip()
        request.headers["Authorization"] = f"Bearer {token}"
        version = str(creds.get("api_version", "")).strip()
        if version:
            request.headers[_VERSION_HEADER] = version
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /v2/locations`` and report the outcome."""
        token = str(creds.get("access_token") or "").strip()
        if not token:
            return CredentialTestResult(ok=False, message="access_token is empty")
        version = str(creds.get("api_version") or "").strip()
        if not version:
            return CredentialTestResult(ok=False, message="api_version is empty")
        try:
            host = host_from(str(creds.get("environment") or _ENV_PRODUCTION))
        except ValueError as exc:
            return CredentialTestResult(ok=False, message=str(exc))
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    f"https://{host}/v2/locations",
                    headers={
                        "Authorization": f"Bearer {token}",
                        _VERSION_HEADER: version,
                        "Accept": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"square rejected token: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = SquareApiCredential
