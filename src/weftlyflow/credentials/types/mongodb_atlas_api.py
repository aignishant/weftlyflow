"""MongoDB Atlas Admin API credential — HTTP Digest auth over ``public_key``/``private_key``.

MongoDB Atlas (https://www.mongodb.com/docs/atlas/reference/api-resources-spec/)
is the catalog's first integration to require **HTTP Digest** authentication
(RFC 7616), a challenge/response scheme driven by the client's auth handler
rather than a static header. Every call hits ``cloud.mongodb.com`` with a
``public_key`` (effectively a username) and a ``private_key`` (secret);
the auth handler responds to the 401 challenge with a hashed nonce.

Because Digest credentials cannot be computed until after the server sends
the challenge, :meth:`inject` is a **no-op** — the node is responsible for
passing :class:`httpx.DigestAuth` to its :class:`httpx.AsyncClient`.

Atlas additionally requires the versioned media-type header
``Accept: application/vnd.atlas.YYYY-MM-DD+json`` on every call; that
choice is node-side because version strings evolve independently of the
credential.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_BASE_URL: str = "https://cloud.mongodb.com/api/atlas/v2"
_ACCEPT: str = "application/vnd.atlas.2024-05-30+json"
_TEST_TIMEOUT_SECONDS: float = 10.0


class MongoDbAtlasApiCredential(BaseCredentialType):
    """Hold Atlas ``public_key`` + ``private_key``. Injection is a no-op."""

    slug: ClassVar[str] = "weftlyflow.mongodb_atlas_api"
    display_name: ClassVar[str] = "MongoDB Atlas Admin API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://www.mongodb.com/docs/atlas/reference/api-resources-spec/"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="public_key",
            display_name="Public Key",
            type="string",
            required=True,
            description="Atlas programmatic API public key — used as the Digest username.",
        ),
        PropertySchema(
            name="private_key",
            display_name="Private Key",
            type="string",
            required=True,
            type_options={"password": True},
            description="Atlas programmatic API private key — used as the Digest password.",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Return ``request`` unchanged — Digest auth rides on the client handler."""
        del creds
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /groups`` (lists accessible projects) to validate."""
        public_key = str(creds.get("public_key", "")).strip()
        private_key = str(creds.get("private_key", "")).strip()
        if not public_key or not private_key:
            return CredentialTestResult(
                ok=False, message="public_key and private_key are required",
            )
        try:
            async with httpx.AsyncClient(
                auth=httpx.DigestAuth(public_key, private_key),
                timeout=_TEST_TIMEOUT_SECONDS,
            ) as client:
                response = await client.get(
                    f"{_BASE_URL}/groups", headers={"Accept": _ACCEPT},
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"atlas rejected credentials: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="atlas credentials valid")


TYPE = MongoDbAtlasApiCredential
