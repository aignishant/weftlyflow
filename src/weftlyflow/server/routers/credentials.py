"""Credentials CRUD + test + OAuth2 authorize.

Encryption happens here (the cipher is carried on ``app.state``). Routers
that need decrypted secrets — the credential ``test`` endpoint, the HTTP
Request node — call through :func:`weftlyflow.credentials.base.BaseCredentialType`
methods with the plaintext dict.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from weftlyflow.auth.constants import (
    SCOPE_CREDENTIAL_READ,
    SCOPE_CREDENTIAL_WRITE,
)
from weftlyflow.credentials.cipher import random_nonce
from weftlyflow.db.entities.credential import CredentialEntity
from weftlyflow.db.entities.oauth_state import OAuthStateEntity
from weftlyflow.db.repositories.credential_repo import CredentialRepository
from weftlyflow.db.repositories.oauth_state_repo import OAuthStateRepository
from weftlyflow.domain.errors import CredentialTypeNotFoundError
from weftlyflow.domain.ids import new_credential_id
from weftlyflow.server.deps import (
    get_credential_cipher,
    get_credential_types,
    get_current_project,
    get_db,
    require_scope,
)
from weftlyflow.server.mappers.credentials import (
    credential_to_response,
    credential_to_summary,
    credential_type_to_response,
)
from weftlyflow.server.schemas.credentials import (
    CredentialCreateRequest,
    CredentialResponse,
    CredentialSummary,
    CredentialTestResponse,
    CredentialTypeResponse,
    CredentialUpdateRequest,
    OAuthAuthorizeRequest,
    OAuthAuthorizeResponse,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from weftlyflow.credentials.cipher import CredentialCipher
    from weftlyflow.credentials.registry import CredentialTypeRegistry


router = APIRouter(prefix="/api/v1/credentials", tags=["credentials"])

_OAUTH_STATE_TTL: timedelta = timedelta(minutes=10)


@router.get(
    "",
    response_model=list[CredentialSummary],
    dependencies=[Depends(require_scope(SCOPE_CREDENTIAL_READ))],
    summary="List credentials in the current project",
)
async def list_credentials(
    type_slug: str | None = Query(default=None, alias="type"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    project_id: str = Depends(get_current_project),
    session: AsyncSession = Depends(get_db),
) -> list[CredentialSummary]:
    """Return metadata-only summaries — no secrets ever leave the server."""
    rows = await CredentialRepository(session).list(
        project_id=project_id,
        type_slug=type_slug,
        limit=limit,
        offset=offset,
    )
    return [credential_to_summary(row) for row in rows]


@router.post(
    "",
    response_model=CredentialResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_scope(SCOPE_CREDENTIAL_WRITE))],
    summary="Create a credential (server encrypts on write)",
)
async def create_credential(
    body: CredentialCreateRequest,
    project_id: str = Depends(get_current_project),
    session: AsyncSession = Depends(get_db),
    cipher: CredentialCipher = Depends(get_credential_cipher),
    types: CredentialTypeRegistry = Depends(get_credential_types),
) -> CredentialResponse:
    """Persist a new credential. ``body.data`` is encrypted before storage."""
    try:
        types.get(body.type)
    except CredentialTypeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc),
        ) from exc
    entity = CredentialEntity(
        id=new_credential_id(),
        project_id=project_id,
        name=body.name,
        type=body.type,
        data_ciphertext=cipher.encrypt(body.data),
    )
    saved = await CredentialRepository(session).create(entity)
    return credential_to_response(saved)


@router.get(
    "/{credential_id}",
    response_model=CredentialResponse,
    dependencies=[Depends(require_scope(SCOPE_CREDENTIAL_READ))],
    summary="Fetch credential metadata (never plaintext)",
)
async def get_credential(
    credential_id: str,
    project_id: str = Depends(get_current_project),
    session: AsyncSession = Depends(get_db),
) -> CredentialResponse:
    """Return metadata or 404."""
    entity = await CredentialRepository(session).get(credential_id, project_id=project_id)
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="credential not found")
    return credential_to_response(entity)


@router.put(
    "/{credential_id}",
    response_model=CredentialResponse,
    dependencies=[Depends(require_scope(SCOPE_CREDENTIAL_WRITE))],
    summary="Update a credential's name and payload",
)
async def update_credential(
    credential_id: str,
    body: CredentialUpdateRequest,
    project_id: str = Depends(get_current_project),
    session: AsyncSession = Depends(get_db),
    cipher: CredentialCipher = Depends(get_credential_cipher),
) -> CredentialResponse:
    """Replace the credential payload entirely (server encrypts)."""
    repo = CredentialRepository(session)
    entity = await repo.get(credential_id, project_id=project_id)
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="credential not found")
    entity.name = body.name
    entity.data_ciphertext = cipher.encrypt(body.data)
    entity.updated_at = datetime.now(UTC)
    updated = await repo.update(entity)
    return credential_to_response(updated)


@router.delete(
    "/{credential_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_scope(SCOPE_CREDENTIAL_WRITE))],
    summary="Delete a credential",
)
async def delete_credential(
    credential_id: str,
    project_id: str = Depends(get_current_project),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Remove the credential row."""
    deleted = await CredentialRepository(session).delete(credential_id, project_id=project_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="credential not found")


@router.post(
    "/{credential_id}/test",
    response_model=CredentialTestResponse,
    dependencies=[Depends(require_scope(SCOPE_CREDENTIAL_READ))],
    summary="Test a credential by invoking its credential-type :meth:`test`",
)
async def test_credential(
    credential_id: str,
    project_id: str = Depends(get_current_project),
    session: AsyncSession = Depends(get_db),
    cipher: CredentialCipher = Depends(get_credential_cipher),
    types: CredentialTypeRegistry = Depends(get_credential_types),
) -> CredentialTestResponse:
    """Decrypt + delegate to the credential type's self-test method."""
    entity = await CredentialRepository(session).get(credential_id, project_id=project_id)
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="credential not found")
    cred_cls = types.get(entity.type)
    result = await cred_cls().test(cipher.decrypt(entity.data_ciphertext))
    return CredentialTestResponse(ok=result.ok, message=result.message)


@router.post(
    "/oauth2/authorize-url",
    response_model=OAuthAuthorizeResponse,
    dependencies=[Depends(require_scope(SCOPE_CREDENTIAL_WRITE))],
    summary="Build the provider's authorization URL + persist the CSRF state",
)
async def oauth_authorize_url(
    body: OAuthAuthorizeRequest,
    project_id: str = Depends(get_current_project),
    session: AsyncSession = Depends(get_db),
    cipher: CredentialCipher = Depends(get_credential_cipher),
) -> OAuthAuthorizeResponse:
    """Generate a redirect URL for the OAuth2 authorization-code flow.

    The credential row must already exist (created empty, then updated after
    the callback writes tokens back). We read the provider URLs + client
    metadata from the decrypted payload.
    """
    repo = CredentialRepository(session)
    entity = await repo.get(body.credential_id, project_id=project_id)
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="credential not found")
    payload = cipher.decrypt(entity.data_ciphertext)

    authorization_url = str(payload.get("authorization_url", "")).strip()
    if not authorization_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="credential payload missing authorization_url",
        )

    state = random_nonce()
    await OAuthStateRepository(session).create(
        OAuthStateEntity(
            state=state,
            credential_id=entity.id,
            project_id=project_id,
            redirect_uri=body.redirect_uri,
            expires_at=datetime.now(UTC) + _OAUTH_STATE_TTL,
        ),
    )

    params: dict[str, str] = {
        "response_type": "code",
        "client_id": str(payload.get("client_id", "")),
        "redirect_uri": body.redirect_uri,
        "state": state,
    }
    scope = str(payload.get("scope", "")).strip()
    if scope:
        params["scope"] = scope
    params.update(body.extra_params)
    url = f"{authorization_url}?{urlencode(params)}"
    return OAuthAuthorizeResponse(authorize_url=url, state=state)


credential_types_router = APIRouter(prefix="/api/v1/credential-types", tags=["credential-types"])


@credential_types_router.get(
    "",
    response_model=list[CredentialTypeResponse],
    summary="List every registered credential type",
)
async def list_credential_types(
    types: CredentialTypeRegistry = Depends(get_credential_types),
    _request: Request = None,  # type: ignore[assignment]
) -> list[CredentialTypeResponse]:
    """Return the registered credential-type catalog for the editor."""
    del _request
    return [credential_type_to_response(cls) for cls in types.catalog()]
