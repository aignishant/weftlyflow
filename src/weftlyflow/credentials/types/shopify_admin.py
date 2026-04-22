"""Shopify Admin API credential — custom header + per-shop subdomain.

Shopify Admin API (https://shopify.dev/docs/api/admin-rest) authenticates
via a single header ``X-Shopify-Access-Token: shpat_...`` issued by a
custom/private app install. Each store is reached at
``https://<shop>.myshopify.com``, so the shop subdomain lives on the
credential and drives base-URL construction on the node side.

The self-test calls ``GET /admin/api/{version}/shop.json`` which every
valid access token can read.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_DEFAULT_VERSION: str = "2024-07"
_TEST_TIMEOUT_SECONDS: float = 10.0


class ShopifyAdminCredential(BaseCredentialType):
    """Inject ``X-Shopify-Access-Token`` on every outbound request."""

    slug: ClassVar[str] = "weftlyflow.shopify_admin"
    display_name: ClassVar[str] = "Shopify Admin"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://shopify.dev/docs/apps/auth/admin-app-access-tokens"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="shop",
            display_name="Shop Subdomain",
            type="string",
            required=True,
            description="'<shop>.myshopify.com' — enter only the '<shop>' part.",
            placeholder="my-store",
        ),
        PropertySchema(
            name="access_token",
            display_name="Access Token",
            type="string",
            required=True,
            description="Admin API access token (starts with 'shpat_').",
            type_options={"password": True},
        ),
        PropertySchema(
            name="api_version",
            display_name="API Version",
            type="string",
            default=_DEFAULT_VERSION,
            description="Admin API version (YYYY-MM).",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set ``X-Shopify-Access-Token`` on ``request``."""
        token = str(creds.get("access_token", "")).strip()
        request.headers["X-Shopify-Access-Token"] = token
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /admin/api/{version}/shop.json`` and report."""
        shop = str(creds.get("shop", "")).strip()
        token = str(creds.get("access_token", "")).strip()
        version = str(creds.get("api_version") or _DEFAULT_VERSION).strip() or _DEFAULT_VERSION
        if not shop or not token:
            return CredentialTestResult(
                ok=False,
                message="shop and access_token are required",
            )
        url = f"https://{shop}.myshopify.com/admin/api/{version}/shop.json"
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    url, headers={"X-Shopify-Access-Token": token},
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"shopify rejected token: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = ShopifyAdminCredential
