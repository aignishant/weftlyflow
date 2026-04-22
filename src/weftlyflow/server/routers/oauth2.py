"""OAuth2 callback endpoint — completes the authorization-code flow.

The browser is redirected here by the OAuth2 provider after the user has
granted consent. We match the ``state`` parameter against the row the
``authorize-url`` endpoint stored, then exchange the code for a token set
and merge the result into the credential payload.

This route is *public* — no bearer token required. The security model is:

* ``state`` is a 32-byte random nonce stored server-side with a 10-minute
  TTL. A leaked / replayed ``state`` is useless after redemption.
* The ``code`` exchange runs with the credential's ``client_secret``; a
  forged callback would still have to produce a valid code for the
  registered client, which only the real provider can do.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status

from weftlyflow.db.repositories.credential_repo import CredentialRepository
from weftlyflow.db.repositories.oauth_state_repo import OAuthStateRepository
from weftlyflow.server.deps import get_credential_cipher, get_db

_HTTP_ERROR_THRESHOLD: int = 400

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from weftlyflow.credentials.cipher import CredentialCipher


router = APIRouter(prefix="/oauth2", tags=["oauth2"])


@router.get(
    "/callback",
    summary="OAuth2 provider redirect target — exchanges code for tokens",
)
async def oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    session: AsyncSession = Depends(get_db),
    cipher: CredentialCipher = Depends(get_credential_cipher),
) -> dict[str, str]:
    """Redeem ``state`` + exchange ``code`` for a token set, stored into the credential."""
    state_row = await OAuthStateRepository(session).consume(state)
    if state_row is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid or expired state",
        )

    repo = CredentialRepository(session)
    entity = await repo.get(state_row.credential_id, project_id=state_row.project_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="credential disappeared mid-flow",
        )

    payload = cipher.decrypt(entity.data_ciphertext)
    token_url = str(payload.get("token_url", "")).strip()
    if not token_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="credential payload missing token_url",
        )

    tokens = await _exchange_code_for_tokens(
        token_url=token_url,
        client_id=str(payload.get("client_id", "")),
        client_secret=str(payload.get("client_secret", "")),
        redirect_uri=state_row.redirect_uri,
        code=code,
    )
    payload["access_token"] = tokens.get("access_token", "")
    refresh = tokens.get("refresh_token")
    if refresh is not None:
        payload["refresh_token"] = refresh
    expires_in = tokens.get("expires_in")
    if isinstance(expires_in, (int, float)):
        payload["expires_at"] = int(datetime.now(UTC).timestamp() + float(expires_in))

    entity.data_ciphertext = cipher.encrypt(payload)
    entity.updated_at = datetime.now(UTC)
    await repo.update(entity)
    return {"status": "ok", "credential_id": entity.id}


async def _exchange_code_for_tokens(
    *,
    token_url: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    code: str,
) -> dict[str, object]:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Accept": "application/json"},
        )
    if resp.status_code >= _HTTP_ERROR_THRESHOLD:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"token exchange failed: {resp.status_code} {resp.text[:200]}",
        )
    body = resp.json()
    if not isinstance(body, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="token endpoint did not return a JSON object",
        )
    return body
