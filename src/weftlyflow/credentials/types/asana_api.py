"""Asana credential — Bearer PAT paired with optional ``Asana-Enable`` feature opt-ins.

Asana (https://developers.asana.com/docs) authenticates with a simple
``Authorization: Bearer <personal_access_token>`` header. The
distinctive shape here is the *optional* ``Asana-Enable`` header — a
comma-separated list of feature flags that opt the caller into beta
features or *out* of deprecations (e.g. ``new_user_task_lists,
new_project_templates``). This credential ships the flag list
alongside the PAT so any node reusing it automatically inherits the
tenant's opt-ins.

The self-test calls ``GET /api/1.0/users/me``.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_TEST_URL: str = "https://app.asana.com/api/1.0/users/me"
_TEST_TIMEOUT_SECONDS: float = 10.0
_ENABLE_HEADER: str = "Asana-Enable"


def _normalize_flags(raw: Any) -> str:
    """Return a comma-joined, whitespace-stripped opt-in flag list."""
    if raw is None or raw == "":
        return ""
    if isinstance(raw, str):
        parts = [part.strip() for part in raw.split(",")]
    elif isinstance(raw, (list, tuple)):
        parts = [str(part).strip() for part in raw]
    else:
        msg = "Asana: 'enable_flags' must be a string or list of strings"
        raise ValueError(msg)
    return ",".join(part for part in parts if part)


class AsanaApiCredential(BaseCredentialType):
    """Inject Bearer PAT + optional ``Asana-Enable`` opt-in header."""

    slug: ClassVar[str] = "weftlyflow.asana_api"
    display_name: ClassVar[str] = "Asana API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = "https://developers.asana.com/docs"
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="access_token",
            display_name="Personal Access Token",
            type="string",
            required=True,
            description="Asana PAT or OAuth2 access token.",
            type_options={"password": True},
        ),
        PropertySchema(
            name="enable_flags",
            display_name="Asana-Enable Flags",
            type="string",
            required=False,
            description=(
                "Comma-separated feature opt-ins sent as the "
                "'Asana-Enable' header (e.g. 'new_user_task_lists')."
            ),
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set Bearer auth and the ``Asana-Enable`` header when flags are set."""
        token = str(creds.get("access_token", "")).strip()
        request.headers["Authorization"] = f"Bearer {token}"
        flags = _normalize_flags(creds.get("enable_flags"))
        if flags:
            request.headers[_ENABLE_HEADER] = flags
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /users/me`` and report the outcome."""
        token = str(creds.get("access_token") or "").strip()
        if not token:
            return CredentialTestResult(ok=False, message="access_token is empty")
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        try:
            flags = _normalize_flags(creds.get("enable_flags"))
        except ValueError as exc:
            return CredentialTestResult(ok=False, message=str(exc))
        if flags:
            headers[_ENABLE_HEADER] = flags
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(_TEST_URL, headers=headers)
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"asana rejected token: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = AsanaApiCredential
