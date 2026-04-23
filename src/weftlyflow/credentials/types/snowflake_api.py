"""Snowflake SQL API credential — JWT/OAuth Bearer + token-type declaration header.

Snowflake's SQL API (https://docs.snowflake.com/en/developer-guide/sql-api/index)
authenticates with ``Authorization: Bearer <token>`` but requires a
sibling ``X-Snowflake-Authorization-Token-Type`` header that declares
whether the Bearer token is a ``KEYPAIR_JWT`` (signed with the
account's RSA keypair) or an ``OAUTH`` access token from a Snowflake
security-integration flow. The token-type header is the distinctive
shape here — other Bearer providers never require it.

The credential also carries the Snowflake account identifier (used to
derive the per-account host ``<account>.snowflakecomputing.com``) so
nodes stay host-agnostic.

The self-test calls the ``GET /api/v2/statements`` listing endpoint,
which returns 200 even with zero statements.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertyOption, PropertySchema

_TOKEN_TYPE_HEADER: str = "X-Snowflake-Authorization-Token-Type"
_VALID_TOKEN_TYPES: frozenset[str] = frozenset({"KEYPAIR_JWT", "OAUTH"})
_TEST_TIMEOUT_SECONDS: float = 10.0


def account_host_from(account: str) -> str:
    """Return ``https://<account>.snowflakecomputing.com`` for ``account``.

    Accepts either a bare account locator (``xy12345``) or a fully
    qualified account identifier with region (``xy12345.us-east-1``).
    """
    cleaned = account.strip().rstrip("/")
    if not cleaned:
        msg = "Snowflake: 'account' is required"
        raise ValueError(msg)
    if "://" in cleaned:
        return cleaned
    if cleaned.endswith(".snowflakecomputing.com"):
        return f"https://{cleaned}"
    return f"https://{cleaned}.snowflakecomputing.com"


class SnowflakeApiCredential(BaseCredentialType):
    """Inject Bearer + token-type header for Snowflake's SQL API."""

    slug: ClassVar[str] = "weftlyflow.snowflake_api"
    display_name: ClassVar[str] = "Snowflake SQL API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://docs.snowflake.com/en/developer-guide/sql-api/index"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="account",
            display_name="Account Identifier",
            type="string",
            required=True,
            description="Account locator or identifier (e.g. 'xy12345.us-east-1').",
        ),
        PropertySchema(
            name="token",
            display_name="Bearer Token",
            type="string",
            required=True,
            description="Signed JWT or OAuth access token.",
            type_options={"password": True},
        ),
        PropertySchema(
            name="token_type",
            display_name="Token Type",
            type="options",
            required=True,
            default="KEYPAIR_JWT",
            options=[
                PropertyOption(value="KEYPAIR_JWT", label="Keypair JWT"),
                PropertyOption(value="OAUTH", label="OAuth"),
            ],
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set Bearer auth and the Snowflake token-type declaration header."""
        token = str(creds.get("token", "")).strip()
        token_type = _validated_token_type(creds.get("token_type"))
        request.headers["Authorization"] = f"Bearer {token}"
        request.headers[_TOKEN_TYPE_HEADER] = token_type
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /api/v2/statements`` and report the outcome."""
        token = str(creds.get("token") or "").strip()
        if not token:
            return CredentialTestResult(ok=False, message="token is empty")
        try:
            token_type = _validated_token_type(creds.get("token_type"))
        except ValueError as exc:
            return CredentialTestResult(ok=False, message=str(exc))
        try:
            base = account_host_from(str(creds.get("account") or ""))
        except ValueError as exc:
            return CredentialTestResult(ok=False, message=str(exc))
        headers = {
            "Authorization": f"Bearer {token}",
            _TOKEN_TYPE_HEADER: token_type,
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    f"{base}/api/v2/statements", headers=headers,
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"snowflake rejected token: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


def _validated_token_type(raw: Any) -> str:
    value = str(raw or "").strip().upper()
    if value not in _VALID_TOKEN_TYPES:
        msg = (
            "Snowflake: 'token_type' must be one of "
            f"{sorted(_VALID_TOKEN_TYPES)!r}"
        )
        raise ValueError(msg)
    return value


TYPE = SnowflakeApiCredential
