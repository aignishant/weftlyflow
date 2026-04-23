"""Plaid API credential — client_id + secret embedded in every request body.

Plaid (https://plaid.com/docs/api/) is the catalog's only integration
that requires **two** credential fields inside the JSON body: each
request must carry both ``client_id`` *and* ``secret`` alongside the
operation-specific payload. This is strictly richer than PostHog's
single-field ``api_key``-in-body convention and therefore warrants its
own credential class.

The credential also carries an ``environment`` field (sandbox /
development / production) because Plaid routes each to a distinct
host. The node reads ``environment`` to pick the base URL; the
credential's :meth:`inject` remains a no-op because all mutation
happens inside the request body which the node assembles.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertyOption, PropertySchema

_HOSTS: dict[str, str] = {
    "sandbox": "https://sandbox.plaid.com",
    "development": "https://development.plaid.com",
    "production": "https://production.plaid.com",
}
_DEFAULT_ENVIRONMENT: str = "sandbox"
_TEST_TIMEOUT_SECONDS: float = 10.0


class PlaidApiCredential(BaseCredentialType):
    """Hold Plaid client_id + secret. Injection is a no-op."""

    slug: ClassVar[str] = "weftlyflow.plaid_api"
    display_name: ClassVar[str] = "Plaid API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://plaid.com/docs/api/"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="client_id",
            display_name="Client ID",
            type="string",
            required=True,
            description="Plaid client_id — embedded in every request body.",
        ),
        PropertySchema(
            name="secret",
            display_name="Secret",
            type="string",
            required=True,
            type_options={"password": True},
            description="Environment-scoped secret — embedded in every request body.",
        ),
        PropertySchema(
            name="environment",
            display_name="Environment",
            type="options",
            required=True,
            default=_DEFAULT_ENVIRONMENT,
            options=[
                PropertyOption(value="sandbox", label="Sandbox"),
                PropertyOption(value="development", label="Development"),
                PropertyOption(value="production", label="Production"),
            ],
            description="Plaid environment — routes to sandbox/development/production host.",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Return ``request`` unchanged — Plaid auth rides inside the body."""
        del creds
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``/categories/get`` (public, requires valid creds) to validate."""
        client_id = str(creds.get("client_id", "")).strip()
        secret = str(creds.get("secret", "")).strip()
        if not client_id or not secret:
            return CredentialTestResult(
                ok=False, message="client_id and secret are required",
            )
        env = str(creds.get("environment") or _DEFAULT_ENVIRONMENT).strip()
        host = _HOSTS.get(env, _HOSTS[_DEFAULT_ENVIRONMENT])
        url = f"{host}/categories/get"
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    url, json={"client_id": client_id, "secret": secret},
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"plaid rejected credentials: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="plaid credentials valid")


TYPE = PlaidApiCredential
