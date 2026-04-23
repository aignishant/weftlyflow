"""NetSuite credential — OAuth 1.0a Token-Based Authentication (HMAC-SHA256).

NetSuite's SuiteTalk REST/SuiteQL APIs authenticate with **OAuth 1.0a**
Token-Based Auth — a distinctly different algorithm from every other
credential in the catalog:

* Five secrets (``account_id``, ``consumer_key``, ``consumer_secret``,
  ``token_id``, ``token_secret``) must all be present.
* The ``Authorization`` header carries the *OAuth 1.0a* scheme with a
  per-request nonce and timestamp.
* The signature is ``HMAC-SHA256`` over a canonical *signature base
  string* of ``<METHOD>&<url-encoded-base-url>&<url-encoded-sorted-params>``.
* The signing key is ``<consumer_secret>&<token_secret>``.
* The ``realm`` parameter of the Authorization header carries the
  uppercased NetSuite account id (dashes replaced with underscores).

This algorithm never appears elsewhere in Weftlyflow — not in the
Bearer family, not in SigV4 — so the signer is isolated here as a pure
``sign_request`` helper reusable by both :meth:`inject` and the
SuiteTalk node.

Reference:
https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/
section_157771733782.html
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from typing import Any, ClassVar
from urllib.parse import quote, urlsplit

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_ALGORITHM: str = "HMAC-SHA256"
_OAUTH_VERSION: str = "1.0"
_TEST_TIMEOUT_SECONDS: float = 10.0


def account_host(account_id: str) -> str:
    """Return the SuiteTalk host for ``account_id``.

    NetSuite account ids are case-insensitive but embedded as lowercase
    with dashes in the host (e.g. ``1234567-sb1`` -> host
    ``1234567-sb1.suitetalk.api.netsuite.com``).
    """
    cleaned = account_id.strip().lower()
    if not cleaned:
        msg = "NetSuite: 'account_id' is required"
        raise ValueError(msg)
    return f"{cleaned}.suitetalk.api.netsuite.com"


def sign_request(
    *,
    method: str,
    url: str,
    query: dict[str, Any] | None,
    account_id: str,
    consumer_key: str,
    consumer_secret: str,
    token_id: str,
    token_secret: str,
    nonce: str | None = None,
    timestamp: str | None = None,
) -> str:
    """Return the ``Authorization`` header for a NetSuite OAuth 1.0a call.

    Builds the signature base string and HMAC-SHA256 signature, then
    serializes the OAuth parameters into the standard
    ``OAuth realm="...", oauth_...="..."`` header form.
    """
    if not (
        account_id and consumer_key and consumer_secret
        and token_id and token_secret
    ):
        msg = "NetSuite: all five OAuth fields are required"
        raise ValueError(msg)
    oauth_nonce = nonce or secrets.token_hex(16)
    oauth_timestamp = timestamp or str(int(time.time()))
    realm = account_id.strip().upper().replace("-", "_")

    oauth_params: dict[str, str] = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": oauth_nonce,
        "oauth_signature_method": _ALGORITHM,
        "oauth_timestamp": oauth_timestamp,
        "oauth_token": token_id,
        "oauth_version": _OAUTH_VERSION,
    }

    all_params: list[tuple[str, str]] = list(oauth_params.items())
    for key, value in (query or {}).items():
        if isinstance(value, (list, tuple)):
            all_params.extend((str(key), str(v)) for v in value)
        else:
            all_params.append(
                (str(key), "" if value is None else str(value)),
            )
    encoded = sorted(
        (_percent(k), _percent(v)) for k, v in all_params
    )
    param_string = "&".join(f"{k}={v}" for k, v in encoded)

    parsed = urlsplit(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    base_string = "&".join(
        [method.upper(), _percent(base_url), _percent(param_string)],
    )
    signing_key = f"{_percent(consumer_secret)}&{_percent(token_secret)}"
    signature = hmac.new(
        signing_key.encode("utf-8"),
        base_string.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    oauth_signature = base64.b64encode(signature).decode("ascii")

    header_params: dict[str, str] = {
        "realm": realm,
        **oauth_params,
        "oauth_signature": oauth_signature,
    }
    return "OAuth " + ", ".join(
        f'{k}="{_percent(v)}"' for k, v in header_params.items()
    )


def _percent(raw: str) -> str:
    return quote(str(raw), safe="~")


class NetSuiteApiCredential(BaseCredentialType):
    """Sign NetSuite requests with OAuth 1.0a Token-Based Auth."""

    slug: ClassVar[str] = "weftlyflow.netsuite_api"
    display_name: ClassVar[str] = "NetSuite API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/"
        "section_157771733782.html"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="account_id",
            display_name="Account ID",
            type="string",
            required=True,
            description="NetSuite account id (e.g. '1234567' or '1234567-sb1').",
        ),
        PropertySchema(
            name="consumer_key",
            display_name="Consumer Key",
            type="string",
            required=True,
            type_options={"password": True},
        ),
        PropertySchema(
            name="consumer_secret",
            display_name="Consumer Secret",
            type="string",
            required=True,
            type_options={"password": True},
        ),
        PropertySchema(
            name="token_id",
            display_name="Token ID",
            type="string",
            required=True,
            type_options={"password": True},
        ),
        PropertySchema(
            name="token_secret",
            display_name="Token Secret",
            type="string",
            required=True,
            type_options={"password": True},
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Sign ``request`` with OAuth 1.0a and set the Authorization header."""
        authorization = sign_request(
            method=request.method,
            url=str(request.url),
            query=dict(request.url.params),
            account_id=str(creds.get("account_id", "")).strip(),
            consumer_key=str(creds.get("consumer_key", "")).strip(),
            consumer_secret=str(creds.get("consumer_secret", "")).strip(),
            token_id=str(creds.get("token_id", "")).strip(),
            token_secret=str(creds.get("token_secret", "")).strip(),
        )
        request.headers["Authorization"] = authorization
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /services/rest/record/v1/`` to validate signing."""
        account_id = str(creds.get("account_id") or "").strip()
        if not account_id:
            return CredentialTestResult(ok=False, message="account_id is empty")
        try:
            host = account_host(account_id)
        except ValueError as exc:
            return CredentialTestResult(ok=False, message=str(exc))
        url = f"https://{host}/services/rest/record/v1/"
        try:
            authorization = sign_request(
                method="GET",
                url=url,
                query={},
                account_id=account_id,
                consumer_key=str(creds.get("consumer_key") or "").strip(),
                consumer_secret=str(creds.get("consumer_secret") or "").strip(),
                token_id=str(creds.get("token_id") or "").strip(),
                token_secret=str(creds.get("token_secret") or "").strip(),
            )
        except ValueError as exc:
            return CredentialTestResult(ok=False, message=str(exc))
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    url,
                    headers={
                        "Authorization": authorization,
                        "Accept": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code >= httpx.codes.BAD_REQUEST:
            return CredentialTestResult(
                ok=False,
                message=f"netsuite rejected signature: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = NetSuiteApiCredential
