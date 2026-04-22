"""Pushover API credential — form-body auth (``token`` + ``user``).

Pushover (https://pushover.net/api) is unusual: there is no
``Authorization`` header. Both the app ``token`` and the recipient
``user`` key are sent as form fields inside the
``application/x-www-form-urlencoded`` POST body alongside the message
payload. The credential therefore stores both values and exposes a
helper that merges them into an outgoing form dict.

The self-test calls ``POST /1/users/validate.json`` which validates
the user key against the app token.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_API_BASE_URL: str = "https://api.pushover.net/1"
_VALIDATE_PATH: str = "/users/validate.json"
_TEST_TIMEOUT_SECONDS: float = 10.0


def auth_form_fields(creds: dict[str, Any]) -> dict[str, str]:
    """Return the ``token``/``user`` pair as form fields."""
    token = str(creds.get("app_token", "")).strip()
    user = str(creds.get("user_key", "")).strip()
    return {"token": token, "user": user}


class PushoverApiCredential(BaseCredentialType):
    """Store the app token + user key; inject is a no-op at the HTTP layer."""

    slug: ClassVar[str] = "weftlyflow.pushover_api"
    display_name: ClassVar[str] = "Pushover API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = "https://pushover.net/api"
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="app_token",
            display_name="Application Token",
            type="string",
            required=True,
            description="API token for the Pushover application.",
            type_options={"password": True},
        ),
        PropertySchema(
            name="user_key",
            display_name="User Key",
            type="string",
            required=True,
            description="User or group key that receives messages.",
            type_options={"password": True},
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Pushover carries credentials in the form body — headers untouched."""
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """POST to ``/users/validate.json`` and report the outcome."""
        fields = auth_form_fields(creds)
        if not fields["token"]:
            return CredentialTestResult(ok=False, message="app_token is empty")
        if not fields["user"]:
            return CredentialTestResult(ok=False, message="user_key is empty")
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    f"{_API_BASE_URL}{_VALIDATE_PATH}",
                    data=fields,
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.status_code != httpx.codes.OK:
            errors = (
                payload.get("errors") if isinstance(payload, dict) else None
            )
            detail = f": {errors}" if errors else ""
            return CredentialTestResult(
                ok=False,
                message=f"pushover rejected key: HTTP {response.status_code}{detail}",
            )
        if isinstance(payload, dict) and payload.get("status") != 1:
            return CredentialTestResult(
                ok=False,
                message=f"pushover returned status={payload.get('status')!r}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = PushoverApiCredential
