"""Cloudinary credential — SHA-1 signed body + HTTP Basic auth fallback.

Cloudinary (https://cloudinary.com/documentation/authentication_signatures)
uses two authentication surfaces:

* **Admin API** (``/v1_1/{cloud_name}/resources/...``) accepts HTTP Basic
  with ``api_key:api_secret``. :meth:`inject` uses this path.
* **Upload API** (``/v1_1/{cloud_name}/{resource_type}/upload|destroy``)
  requires a **SHA-1 signature** derived from the request body:

    1. Collect every body parameter **except** ``api_key``, ``file``,
       ``resource_type``, ``cloud_name`` and ``signature`` itself.
    2. Sort keys alphabetically.
    3. Join as ``key1=value1&key2=value2&...`` (standard URL form, but
       **without** percent-encoding).
    4. Concatenate the ``api_secret`` directly onto the end (no separator).
    5. Take ``sha1(...)`` and hex-encode.
    6. Submit as the ``signature`` body field alongside ``api_key`` and
       ``timestamp``.

The node invokes :func:`sign_params` for upload/destroy and relies on
the Basic auth injected here for list/get operations.
"""

from __future__ import annotations

import base64
import hashlib
from typing import Any, ClassVar, Final

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_API_BASE_URL: Final[str] = "https://api.cloudinary.com"
_TEST_TIMEOUT_SECONDS: Final[float] = 10.0
_EXCLUDED_FROM_SIGNATURE: Final[frozenset[str]] = frozenset(
    {"api_key", "file", "resource_type", "cloud_name", "signature"},
)


def sign_params(params: dict[str, Any], api_secret: str) -> str:
    """Return ``sha1(sorted(params) + api_secret)`` as a hex string.

    Skips keys in :data:`_EXCLUDED_FROM_SIGNATURE` and any value that
    coerces to an empty string — Cloudinary ignores empty fields and
    signing them would desync the server-side hash.
    """
    pairs: list[str] = []
    for key in sorted(params):
        if key in _EXCLUDED_FROM_SIGNATURE:
            continue
        value = params[key]
        if value is None:
            continue
        text = str(value)
        if not text:
            continue
        pairs.append(f"{key}={text}")
    signing_input = "&".join(pairs) + api_secret
    return hashlib.sha1(signing_input.encode("utf-8")).hexdigest()


def basic_auth_header(api_key: str, api_secret: str) -> str:
    """Return the ``Basic <b64(key:secret)>`` header value."""
    token = base64.b64encode(f"{api_key}:{api_secret}".encode()).decode("ascii")
    return f"Basic {token}"


class CloudinaryApiCredential(BaseCredentialType):
    """Hold Cloudinary cloud/key/secret and attach HTTP Basic auth."""

    slug: ClassVar[str] = "weftlyflow.cloudinary_api"
    display_name: ClassVar[str] = "Cloudinary API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://cloudinary.com/documentation/authentication_signatures"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="cloud_name",
            display_name="Cloud Name",
            type="string",
            required=True,
            description="Cloudinary account cloud name — the tenant segment in every URL.",
        ),
        PropertySchema(
            name="api_key",
            display_name="API Key",
            type="string",
            required=True,
            description="Cloudinary API key (sent as the Basic-auth username).",
        ),
        PropertySchema(
            name="api_secret",
            display_name="API Secret",
            type="string",
            required=True,
            type_options={"password": True},
            description="Cloudinary API secret — Basic-auth password and signing key.",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set ``Authorization: Basic <b64(api_key:api_secret)>`` on ``request``."""
        api_key = str(creds.get("api_key", "")).strip()
        api_secret = str(creds.get("api_secret", "")).strip()
        request.headers["Authorization"] = basic_auth_header(api_key, api_secret)
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /v1_1/{cloud_name}/resources/image?max_results=1``."""
        cloud_name = str(creds.get("cloud_name") or "").strip()
        api_key = str(creds.get("api_key") or "").strip()
        api_secret = str(creds.get("api_secret") or "").strip()
        if not cloud_name or not api_key or not api_secret:
            return CredentialTestResult(
                ok=False, message="cloud_name, api_key and api_secret are required",
            )
        url = f"{_API_BASE_URL}/v1_1/{cloud_name}/resources/image"
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    url,
                    params={"max_results": "1"},
                    headers={
                        "Authorization": basic_auth_header(api_key, api_secret),
                        "Accept": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"cloudinary rejected credentials: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="cloudinary credentials valid")


TYPE = CloudinaryApiCredential
