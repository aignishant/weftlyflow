"""Credential DTOs — never carry plaintext.

Plaintext lives in :attr:`CredentialUpsertRequest.data` on the way in and
in the decrypted form the node executor sees. It never appears in a
response. :class:`CredentialResponse` and :class:`CredentialSummary` are
the only shapes the API returns.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from weftlyflow.server.schemas.common import WeftlyflowModel


class CredentialCreateRequest(WeftlyflowModel):
    """Body for ``POST /api/v1/credentials``."""

    name: str = Field(min_length=1, max_length=200)
    type: str = Field(min_length=1, max_length=80)
    data: dict[str, Any] = Field(default_factory=dict)


class CredentialUpdateRequest(WeftlyflowModel):
    """Body for ``PUT /api/v1/credentials/{id}``.

    ``data`` replaces the encrypted payload entirely; callers that only
    want to rename should send the existing payload untouched.
    """

    name: str = Field(min_length=1, max_length=200)
    data: dict[str, Any] = Field(default_factory=dict)


class CredentialResponse(WeftlyflowModel):
    """GET ``/credentials/{id}`` response — metadata only, no secrets."""

    id: str
    project_id: str
    name: str
    type: str
    created_at: datetime
    updated_at: datetime


class CredentialSummary(WeftlyflowModel):
    """List-row response — identical to :class:`CredentialResponse` today."""

    id: str
    project_id: str
    name: str
    type: str
    created_at: datetime
    updated_at: datetime


class CredentialTestResponse(WeftlyflowModel):
    """POST ``/credentials/{id}/test`` response."""

    ok: bool
    message: str = ""


class OAuthAuthorizeRequest(WeftlyflowModel):
    """POST ``/credentials/oauth2/authorize-url``.

    Returns the provider's authorization URL plus a ``state`` token that
    the callback handler will verify.
    """

    credential_id: str
    redirect_uri: str
    extra_params: dict[str, str] = Field(default_factory=dict)


class OAuthAuthorizeResponse(WeftlyflowModel):
    """Reply body carrying the redirect URL + opaque ``state``."""

    authorize_url: str
    state: str


class CredentialTypeResponse(WeftlyflowModel):
    """GET ``/api/v1/credential-types`` entry."""

    slug: str
    display_name: str
    generic: bool
    properties: list[dict[str, Any]] = Field(default_factory=list)
