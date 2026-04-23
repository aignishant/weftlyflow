"""HashiCorp Vault KV v2 secret provider.

Resolves references of the form ``vault:<mount>/data/<path>#<field>``
against Vault's HTTP API, returning the plaintext value of ``<field>``.

Scope of this built-in adapter:

* **KV v2 only** — ``/v1/<mount>/data/<path>`` endpoints. KV v1 and
  dynamic backends (database, PKI, transit) are out of scope.
* **Token auth only** — the client is expected to carry a long-lived or
  externally-rotated Vault token. AppRole / Kubernetes auth belong in a
  separate adapter because they require a login round-trip plus renewal.
* **No caching** — each resolve is one HTTP round-trip. Vault's own
  response cache on the server side is usually enough; a client-side
  cache needs a TTL policy that is application-specific.

The reference path is passed through to Vault unchanged, so the caller is
responsible for including the ``/data/`` segment that KV v2 requires:

.. code-block:: text

    vault:secret/data/slack#bot_token
           └── mount ──┘└── field
              └── path ──┘
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


class VaultAuthError(SecretProviderError):
    """Raised when Vault rejects the configured token (401/403)."""


class _BorrowedClient:
    """Wrap an injected client so ``async with`` does not close it."""

    __slots__ = ("_client",)

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def __aenter__(self) -> httpx.AsyncClient:
        return self._client

    async def __aexit__(self, *_exc: object) -> None:
        return None


class VaultSecretProvider:
    """KV v2 secret provider for HashiCorp Vault.

    Example:
        >>> provider = VaultSecretProvider(  # doctest: +SKIP
        ...     address="https://vault.example.com:8200",
        ...     token="hvs.CAESIJ...",
        ... )
        >>> await provider.get(parse_reference("vault:secret/data/slack#bot_token"))
        'xoxb-...'
    """

    scheme: str = "vault"

    __slots__ = ("_address", "_http", "_namespace", "_timeout", "_token")

    def __init__(
        self,
        address: str,
        token: str,
        *,
        namespace: str = "",
        timeout_seconds: float = 5.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """Construct a provider bound to a single Vault cluster.

        Args:
            address: Base URL of the Vault server, e.g. ``https://vault:8200``.
                Trailing slashes are stripped.
            token: Vault token passed via the ``X-Vault-Token`` header.
            namespace: Optional Vault Enterprise namespace sent as
                ``X-Vault-Namespace``.
            timeout_seconds: Per-request HTTP timeout. Defaults to 5 s — Vault
                lookups should be fast, and we would rather fail workflows
                than block on a slow network.
            http_client: Optional pre-built ``httpx.AsyncClient`` used in tests
                to hook in respx. Production callers should pass ``None``.
        """
        if not address:
            msg = "VaultSecretProvider: address is required"
            raise ValueError(msg)
        if not token:
            msg = "VaultSecretProvider: token is required"
            raise ValueError(msg)
        self._address = address.rstrip("/")
        self._token = token
        self._namespace = namespace
        self._timeout = timeout_seconds
        self._http = http_client

    async def get(self, reference: SecretReference) -> str:
        """Return the plaintext secret for ``reference``.

        Raises:
            SecretProviderError: The reference scheme is wrong, has no
                ``#field`` fragment (mandatory for KV v2), or Vault returned
                an unexpected body shape.
            VaultAuthError: Vault responded 401/403.
            SecretNotFoundError: Vault responded 404 or the requested field
                is absent from the returned payload.
        """
        if reference.scheme != self.scheme:
            msg = f"VaultSecretProvider cannot handle scheme {reference.scheme!r}"
            raise SecretProviderError(msg)
        if reference.field is None:
            msg = "vault references must include a #field fragment"
            raise SecretProviderError(msg)

        payload = await self._read(reference.path)
        try:
            data = payload["data"]["data"]
        except (KeyError, TypeError) as exc:
            msg = "Vault response did not carry a KV v2 data.data envelope"
            raise SecretProviderError(msg) from exc

        if reference.field not in data:
            msg = f"Vault secret has no field {reference.field!r}"
            raise SecretNotFoundError(msg)
        value = data[reference.field]
        if not isinstance(value, str):
            msg = f"Vault field {reference.field!r} is not a string"
            raise SecretProviderError(msg)
        return value

    async def _read(self, path: str) -> dict[str, Any]:
        url = f"{self._address}/v1/{path.lstrip('/')}"
        headers = {"X-Vault-Token": self._token}
        if self._namespace:
            headers["X-Vault-Namespace"] = self._namespace
        async with self._client() as client:
            resp = await client.get(url, headers=headers, timeout=self._timeout)
        if resp.status_code == HTTPStatus.NOT_FOUND:
            msg = f"Vault secret {path!r} not found"
            raise SecretNotFoundError(msg)
        if resp.status_code in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
            msg = f"Vault rejected the configured token ({resp.status_code})"
            raise VaultAuthError(msg)
        if resp.status_code >= HTTPStatus.BAD_REQUEST:
            msg = f"Vault returned {resp.status_code} for {path!r}"
            raise SecretProviderError(msg)
        body = resp.json()
        if not isinstance(body, dict):
            msg = "Vault response was not a JSON object"
            raise SecretProviderError(msg)
        return body

    def _client(self) -> AbstractAsyncContextManager[httpx.AsyncClient]:
        if self._http is not None:
            return _BorrowedClient(self._http)
        return httpx.AsyncClient()
