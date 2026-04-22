"""Credential resolver — bridges the engine and the DB/cipher layers.

Nodes that consume credentials (starting with :class:`HttpRequestNode`)
never talk to the database directly. They call
:meth:`CredentialResolver.resolve(credential_id, project_id=...)` and get
back ``(credential_type_class, decrypted_payload)``. The resolver wraps
whatever persistence + encryption backend is wired at boot.

In tests we use :class:`InMemoryCredentialResolver` so no engine/cipher is
required. The production implementation lives in
:class:`DatabaseCredentialResolver`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from weftlyflow.domain.errors import (
    CredentialNotFoundError,
    CredentialTypeNotFoundError,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from weftlyflow.credentials.base import BaseCredentialType
    from weftlyflow.credentials.cipher import CredentialCipher
    from weftlyflow.credentials.registry import CredentialTypeRegistry


class CredentialResolver(Protocol):
    """Anything that can hand back a credential by id, project-scoped."""

    async def resolve(
        self,
        credential_id: str,
        *,
        project_id: str,
    ) -> tuple[type[BaseCredentialType], dict[str, Any]]:
        """Return the credential-type class + decrypted payload."""


@dataclass(slots=True)
class InMemoryCredentialResolver:
    """Test-mode resolver backed by plain dicts.

    Attributes:
        types: Slug → credential-type class.
        rows: Credential id → (type slug, plaintext payload, project id).
    """

    types: dict[str, type[BaseCredentialType]]
    rows: dict[str, tuple[str, dict[str, Any], str]]

    async def resolve(
        self,
        credential_id: str,
        *,
        project_id: str,
    ) -> tuple[type[BaseCredentialType], dict[str, Any]]:
        """Return the in-memory entry matching ``(credential_id, project_id)``."""
        row = self.rows.get(credential_id)
        if row is None:
            msg = f"credential {credential_id!r} not found"
            raise CredentialNotFoundError(msg)
        slug, payload, owner_project = row
        if owner_project != project_id:
            msg = f"credential {credential_id!r} not in project {project_id!r}"
            raise CredentialNotFoundError(msg)
        cred_cls = self.types.get(slug)
        if cred_cls is None:
            msg = f"no credential type registered for {slug!r}"
            raise CredentialTypeNotFoundError(msg)
        return cred_cls, dict(payload)


class DatabaseCredentialResolver:
    """Production resolver — reads + decrypts from the ``credentials`` table."""

    __slots__ = ("_cipher", "_session_factory", "_types")

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[Any],
        cipher: CredentialCipher,
        types: CredentialTypeRegistry,
    ) -> None:
        """Bind to the shared session factory, cipher, and type registry."""
        self._session_factory = session_factory
        self._cipher = cipher
        self._types = types

    async def resolve(
        self,
        credential_id: str,
        *,
        project_id: str,
    ) -> tuple[type[BaseCredentialType], dict[str, Any]]:
        """Fetch, scope-check, decrypt, and resolve the credential type."""
        from weftlyflow.db.repositories.credential_repo import (  # noqa: PLC0415
            CredentialRepository,
        )

        async with self._session_factory() as session:
            entity = await CredentialRepository(session).get(
                credential_id, project_id=project_id,
            )
        if entity is None:
            msg = f"credential {credential_id!r} not found"
            raise CredentialNotFoundError(msg)
        cred_cls = self._types.get(entity.type)
        payload = self._cipher.decrypt(entity.data_ciphertext)
        return cred_cls, payload
