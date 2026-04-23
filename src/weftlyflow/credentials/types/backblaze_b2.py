"""Backblaze B2 credential — HTTP Basic → session token + tenant apiUrl.

Backblaze B2 Native
(https://www.backblaze.com/apidocs/b2-authorize-account) introduces a
shape unique in the catalog: a single call to ``b2_authorize_account``
with HTTP Basic (``keyId:applicationKey``) returns **both** the session
``authorizationToken`` **and** the per-tenant ``apiUrl`` / ``downloadUrl``
that the caller must use as the base URL for every subsequent B2
request. There is no standard ``/oauth2/token`` grant_type form body
— the endpoint is a bespoke authorize-and-discover call.

This is materially different from:

* PayPal / Plaid (static OAuth2 token endpoints with a known host).
* AWS SigV4 (no runtime token exchange; signs each request).
* Azure SharedKey (HMAC signing, no runtime token).
* GCP service-account (JWT Grant, static token host).

``inject()`` is a no-op — the node calls :func:`fetch_session` once per
execution and threads the returned ``(token, api_url)`` pair through
dispatch.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, ClassVar, Final

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_AUTHORIZE_HOST: Final[str] = "https://api.backblazeb2.com"
_AUTHORIZE_PATH: Final[str] = "/b2api/v3/b2_authorize_account"
_TEST_TIMEOUT_SECONDS: Final[float] = 15.0


@dataclass(frozen=True, slots=True)
class B2Session:
    """Authorized session bundle returned by ``b2_authorize_account``.

    Attributes:
        authorization_token: Short-lived bearer — attach as ``Authorization``.
        api_url: Base URL for every non-upload API call (tenant-specific).
        download_url: Base URL for ``b2_download_*`` endpoints.
        account_id: Populated by B2 for logging + audit trails.
    """

    authorization_token: str
    api_url: str
    download_url: str
    account_id: str


def basic_auth_header(key_id: str, application_key: str) -> str:
    """Return ``Basic <base64(key_id:application_key)>``."""
    raw = f"{key_id}:{application_key}".encode()
    return "Basic " + base64.b64encode(raw).decode("ascii")


def authorize_host() -> str:
    """Return the fixed host for the ``b2_authorize_account`` call."""
    return _AUTHORIZE_HOST


async def fetch_session(
    client: httpx.AsyncClient,
    creds: dict[str, Any],
) -> B2Session:
    """Exchange ``key_id:application_key`` for a :class:`B2Session`.

    Args:
        client: An ``httpx.AsyncClient`` whose ``base_url`` points at
            :data:`_AUTHORIZE_HOST`.
        creds: The decrypted credential payload — must include
            ``key_id`` and ``application_key``.

    Returns:
        A :class:`B2Session` carrying the bearer token and the
        tenant-specific API / download URLs.

    Raises:
        ValueError: On missing fields or malformed B2 responses.
    """
    key_id = str(creds.get("key_id") or "").strip()
    application_key = str(creds.get("application_key") or "").strip()
    if not key_id or not application_key:
        msg = "Backblaze B2: key_id and application_key are required"
        raise ValueError(msg)
    response = await client.get(
        _AUTHORIZE_PATH,
        headers={
            "Authorization": basic_auth_header(key_id, application_key),
            "Accept": "application/json",
        },
    )
    if response.status_code != httpx.codes.OK:
        msg = (
            f"Backblaze B2 authorize rejected credentials: "
            f"HTTP {response.status_code}"
        )
        raise ValueError(msg)
    try:
        payload = response.json()
    except ValueError as exc:
        msg = "Backblaze B2 authorize returned non-JSON body"
        raise ValueError(msg) from exc
    return _session_from_payload(payload)


def _session_from_payload(payload: Any) -> B2Session:
    if not isinstance(payload, dict):
        msg = "Backblaze B2 authorize payload was not an object"
        raise ValueError(msg)
    token = payload.get("authorizationToken")
    account_id = payload.get("accountId")
    api_info = payload.get("apiInfo")
    storage_api = (
        api_info.get("storageApi") if isinstance(api_info, dict) else None
    )
    if not isinstance(storage_api, dict):
        msg = "Backblaze B2 authorize omitted 'apiInfo.storageApi'"
        raise ValueError(msg)
    api_url = storage_api.get("apiUrl")
    download_url = storage_api.get("downloadUrl")
    if (
        not isinstance(token, str)
        or not isinstance(api_url, str)
        or not isinstance(download_url, str)
        or not isinstance(account_id, str)
    ):
        msg = "Backblaze B2 authorize response is missing required fields"
        raise ValueError(msg)
    return B2Session(
        authorization_token=token,
        api_url=api_url.rstrip("/"),
        download_url=download_url.rstrip("/"),
        account_id=account_id,
    )


class BackblazeB2Credential(BaseCredentialType):
    """Store B2 keyId + applicationKey — sessions are fetched at runtime."""

    slug: ClassVar[str] = "weftlyflow.backblaze_b2"
    display_name: ClassVar[str] = "Backblaze B2"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://www.backblaze.com/apidocs/b2-authorize-account"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="key_id",
            display_name="Key ID",
            type="string",
            required=True,
            description="B2 application key ID — the username half of Basic auth.",
        ),
        PropertySchema(
            name="application_key",
            display_name="Application Key",
            type="string",
            required=True,
            type_options={"password": True},
            description="B2 application key secret — the password half of Basic auth.",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """No-op — the node fetches a session via :func:`fetch_session`."""
        del creds
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``b2_authorize_account`` and report the outcome."""
        try:
            async with httpx.AsyncClient(
                base_url=_AUTHORIZE_HOST,
                timeout=_TEST_TIMEOUT_SECONDS,
            ) as client:
                await fetch_session(client, creds)
        except (httpx.HTTPError, ValueError) as exc:
            return CredentialTestResult(ok=False, message=str(exc))
        return CredentialTestResult(ok=True, message="backblaze b2 credentials valid")


TYPE = BackblazeB2Credential
