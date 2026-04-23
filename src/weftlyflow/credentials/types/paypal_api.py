"""PayPal REST credential — OAuth2 Client Credentials with runtime token fetch.

PayPal (https://developer.paypal.com/api/rest/authentication/) does NOT
issue long-lived bearer tokens. Instead, every API session begins with
an OAuth2 Client Credentials grant: the credential exchanges
``client_id:client_secret`` (HTTP Basic) and ``grant_type=client_credentials``
(form body) at ``/v1/oauth2/token`` for a short-lived access token.

This is the first credential in the catalog that **fetches its bearer
at runtime** — the credential stores no access token, only the
client id, the client secret, and the environment (sandbox vs live).
The node is expected to call :func:`fetch_access_token` once at the
start of execution and re-use the returned token across the dispatch
loop. ``inject()`` is therefore a no-op fallback: the node attaches
the Bearer header itself once it has obtained the token.

Other distinctive PayPal shapes the node enforces:

* ``PayPal-Request-Id`` — per-write idempotency key for safe retries.
* ``PayPal-Auth-Assertion`` — JWT-style impersonation header for
  Connect-style multi-merchant calls (not implemented in the node).

The self-test fetches a token and reports success or the OAuth2
error envelope.
"""

from __future__ import annotations

import base64
from typing import Any, ClassVar, Final

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_PRODUCTION_HOST: Final[str] = "api-m.paypal.com"
_SANDBOX_HOST: Final[str] = "api-m.sandbox.paypal.com"
_ENV_SANDBOX: Final[str] = "sandbox"
_ENV_LIVE: Final[str] = "live"
_VALID_ENVIRONMENTS: Final[frozenset[str]] = frozenset({_ENV_SANDBOX, _ENV_LIVE})
_TOKEN_PATH: Final[str] = "/v1/oauth2/token"
_GRANT_TYPE: Final[str] = "client_credentials"
_TEST_TIMEOUT_SECONDS: Final[float] = 10.0


def host_from(environment: str) -> str:
    """Return the PayPal host for ``environment``."""
    cleaned = environment.strip().lower()
    if cleaned not in _VALID_ENVIRONMENTS:
        msg = (
            f"PayPal: 'environment' must be one of "
            f"{sorted(_VALID_ENVIRONMENTS)!r}"
        )
        raise ValueError(msg)
    return _SANDBOX_HOST if cleaned == _ENV_SANDBOX else _PRODUCTION_HOST


def _basic_header(client_id: str, client_secret: str) -> str:
    """Return ``Basic <base64(client_id:client_secret)>``."""
    raw = f"{client_id}:{client_secret}".encode()
    return "Basic " + base64.b64encode(raw).decode("ascii")


async def fetch_access_token(
    client: httpx.AsyncClient,
    creds: dict[str, Any],
) -> str:
    """Exchange ``client_credentials`` for a short-lived access token.

    Args:
        client: An ``httpx.AsyncClient`` whose ``base_url`` already points at
            the right PayPal host (sandbox or live).
        creds: The decrypted credential payload — must contain ``client_id``
            and ``client_secret``.

    Returns:
        The bearer token string.

    Raises:
        ValueError: If the credential is missing fields or PayPal returned
            a non-200 / malformed response.
    """
    client_id = str(creds.get("client_id") or "").strip()
    client_secret = str(creds.get("client_secret") or "").strip()
    if not client_id or not client_secret:
        msg = "PayPal: client_id and client_secret are required"
        raise ValueError(msg)
    response = await client.post(
        _TOKEN_PATH,
        headers={
            "Authorization": _basic_header(client_id, client_secret),
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={"grant_type": _GRANT_TYPE},
    )
    if response.status_code != httpx.codes.OK:
        msg = f"PayPal token endpoint rejected credentials: HTTP {response.status_code}"
        raise ValueError(msg)
    try:
        payload = response.json()
    except ValueError as exc:
        msg = "PayPal token endpoint returned non-JSON body"
        raise ValueError(msg) from exc
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token:
        msg = "PayPal token endpoint omitted 'access_token'"
        raise ValueError(msg)
    return token


class PayPalApiCredential(BaseCredentialType):
    """Store ``client_id`` + ``client_secret`` — token is fetched at runtime."""

    slug: ClassVar[str] = "weftlyflow.paypal_api"
    display_name: ClassVar[str] = "PayPal REST"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://developer.paypal.com/api/rest/authentication/"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="client_id",
            display_name="Client ID",
            type="string",
            required=True,
            description="PayPal REST app client id.",
        ),
        PropertySchema(
            name="client_secret",
            display_name="Client Secret",
            type="string",
            required=True,
            description="PayPal REST app secret.",
            type_options={"password": True},
        ),
        PropertySchema(
            name="environment",
            display_name="Environment",
            type="string",
            required=True,
            default=_ENV_LIVE,
            description="'sandbox' or 'live'.",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """No-op — PayPal tokens are fetched at runtime by the node."""
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Fetch a token and report the outcome."""
        client_id = str(creds.get("client_id") or "").strip()
        client_secret = str(creds.get("client_secret") or "").strip()
        if not client_id or not client_secret:
            return CredentialTestResult(
                ok=False,
                message="client_id and client_secret are required",
            )
        try:
            host = host_from(str(creds.get("environment") or _ENV_LIVE))
        except ValueError as exc:
            return CredentialTestResult(ok=False, message=str(exc))
        try:
            async with httpx.AsyncClient(
                base_url=f"https://{host}",
                timeout=_TEST_TIMEOUT_SECONDS,
            ) as client:
                await fetch_access_token(client, creds)
        except (httpx.HTTPError, ValueError) as exc:
            return CredentialTestResult(ok=False, message=str(exc))
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = PayPalApiCredential
