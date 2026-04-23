"""1Password Connect secret provider.

Resolves references of the form
``op:vaults/<vault>/items/<item>#<field-label>`` against a self-hosted
**1Password Connect Server**. Connect exposes a thin REST API in front of
a vault the organisation already owns, authenticated by a long-lived
bearer token scoped to a subset of vaults.

Scope of this built-in adapter:

* **Connect only** — the SaaS 1Password API (service-accounts) is a
  separate endpoint with a different auth flow; it belongs in a
  follow-up.
* **Items fetched by UUID path** — the reference path is forwarded to
  Connect unchanged, so the caller must include the ``/vaults/<uuid>/items/<uuid>``
  segments. Name-based lookup would require a list-and-match round-trip
  we intentionally omit.
* **Field lookup by label** — ``#password`` picks the first entry in
  ``item.fields`` whose ``label`` matches (case-sensitive). Concealed,
  string, and OTP field types all surface as ``value`` strings.
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from http import HTTPStatus
from typing import Any

import httpx

from weftlyflow.credentials.external.base import (
    SecretNotFoundError,
    SecretProviderError,
    SecretReference,
)


class OnePasswordAuthError(SecretProviderError):
    """Raised when Connect rejects the configured token (401/403)."""


class _BorrowedClient:
    """Wrap an injected client so ``async with`` does not close it."""

    __slots__ = ("_client",)

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def __aenter__(self) -> httpx.AsyncClient:
        return self._client

    async def __aexit__(self, *_exc: object) -> None:
        return None


class OnePasswordSecretProvider:
    """1Password Connect Server secret provider.

    Example:
        >>> provider = OnePasswordSecretProvider(  # doctest: +SKIP
        ...     connect_url="http://onepassword-connect:8080",
        ...     token="eyJhbGciOi...",
        ... )
        >>> ref = parse_reference("op:vaults/abc/items/xyz#password")
        >>> await provider.get(ref)  # doctest: +SKIP
        '<concealed value>'
    """

    scheme: str = "op"

    __slots__ = ("_connect_url", "_http", "_timeout", "_token")

    def __init__(
        self,
        connect_url: str,
        token: str,
        *,
        timeout_seconds: float = 5.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """Construct a provider bound to a single Connect endpoint.

        Args:
            connect_url: Base URL of the Connect server — e.g.
                ``http://onepassword-connect:8080``. Trailing slashes are
                stripped.
            token: Connect API token, sent as ``Authorization: Bearer <token>``.
            timeout_seconds: Per-request HTTP timeout. Defaults to 5 s.
            http_client: Optional pre-built ``httpx.AsyncClient`` used in tests
                to hook in respx. Production callers should pass ``None``.
        """
        if not connect_url:
            msg = "OnePasswordSecretProvider: connect_url is required"
            raise ValueError(msg)
        if not token:
            msg = "OnePasswordSecretProvider: token is required"
            raise ValueError(msg)
        self._connect_url = connect_url.rstrip("/")
        self._token = token
        self._timeout = timeout_seconds
        self._http = http_client

    async def get(self, reference: SecretReference) -> str:
        """Return the plaintext value of ``reference.field`` on the item.

        Raises:
            SecretProviderError: The reference scheme is wrong, has no
                ``#field`` fragment, or Connect returned an unexpected body
                shape.
            OnePasswordAuthError: Connect responded 401/403.
            SecretNotFoundError: Connect responded 404, or no field on the
                returned item has a label matching ``reference.field``.
        """
        if reference.scheme != self.scheme:
            msg = f"OnePasswordSecretProvider cannot handle scheme {reference.scheme!r}"
            raise SecretProviderError(msg)
        if reference.field is None:
            msg = "op references must include a #field fragment"
            raise SecretProviderError(msg)

        item = await self._read(reference.path)
        fields = item.get("fields")
        if not isinstance(fields, list):
            msg = "1Password item payload did not carry a 'fields' array"
            raise SecretProviderError(msg)

        for entry in fields:
            if not isinstance(entry, dict):
                continue
            if entry.get("label") == reference.field:
                value = entry.get("value")
                if value is None:
                    msg = f"1Password field {reference.field!r} has no value"
                    raise SecretNotFoundError(msg)
                if not isinstance(value, str):
                    msg = f"1Password field {reference.field!r} is not a string"
                    raise SecretProviderError(msg)
                return value

        msg = f"1Password item has no field labelled {reference.field!r}"
        raise SecretNotFoundError(msg)

    async def _read(self, path: str) -> dict[str, Any]:
        url = f"{self._connect_url}/v1/{path.lstrip('/')}"
        headers = {"Authorization": f"Bearer {self._token}"}
        async with self._client() as client:
            resp = await client.get(url, headers=headers, timeout=self._timeout)
        if resp.status_code == HTTPStatus.NOT_FOUND:
            msg = f"1Password item {path!r} not found"
            raise SecretNotFoundError(msg)
        if resp.status_code in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
            msg = f"1Password Connect rejected the configured token ({resp.status_code})"
            raise OnePasswordAuthError(msg)
        if resp.status_code >= HTTPStatus.BAD_REQUEST:
            msg = f"1Password Connect returned {resp.status_code} for {path!r}"
            raise SecretProviderError(msg)
        body = resp.json()
        if not isinstance(body, dict):
            msg = "1Password Connect response was not a JSON object"
            raise SecretProviderError(msg)
        return body

    def _client(self) -> AbstractAsyncContextManager[httpx.AsyncClient]:
        if self._http is not None:
            return _BorrowedClient(self._http)
        return httpx.AsyncClient()
